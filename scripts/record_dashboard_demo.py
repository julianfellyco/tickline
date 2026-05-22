#!/usr/bin/env python3
"""Record a dashboard demo video.

Boots streamlit locally, drives the dashboard with Playwright,
captures a WebM video of the full tour, then exits. Convert to
MP4/GIF with ffmpeg afterwards.

Usage:
    python scripts/record_dashboard_demo.py
    # → assets/demo/dashboard.webm
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "assets" / "demo"
DEMO_DIR.mkdir(parents=True, exist_ok=True)

# Wipe previous recordings so the filename is predictable
for f in DEMO_DIR.glob("*.webm"):
    f.unlink()

PAGES = [
    ("Overview",     2500),
    ("Backtest",     2500),
    ("Walk-forward", 2500),
    ("Portfolio",    2500),
    ("Consensus",    2500),
    ("Paper ledger", 2500),
]

VIEWPORT = {"width": 1440, "height": 900}
URL = "http://localhost:8770/"


def boot_streamlit() -> subprocess.Popen:
    """Start streamlit in the background."""
    print(">> booting streamlit on :8770 ...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "dashboard" / "app.py"),
         "--server.port", "8770", "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # wait for server up
    import socket
    for _ in range(40):
        time.sleep(0.5)
        try:
            with socket.create_connection(("localhost", 8770), timeout=0.5):
                print("   streamlit ready")
                time.sleep(2)  # give it another beat to render
                return proc
        except OSError:
            continue
    proc.terminate()
    raise RuntimeError("streamlit failed to start")


def record(proc: subprocess.Popen) -> Path:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(DEMO_DIR),
            record_video_size=VIEWPORT,
            color_scheme="dark",
        )
        page = context.new_page()
        print(">> opening dashboard ...")
        page.goto(URL, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(2500)

        for label, dwell_ms in PAGES:
            print(f">> {label}")
            try:
                # Streamlit radio labels render as plain text; click by label
                page.get_by_text(label, exact=True).first.click(timeout=8000)
                page.wait_for_timeout(800)
                # if there's a "RUN" button on the page, click it
                run_btn = page.locator("button:has-text('RUN'), button:has-text('ANALYZE')")
                if run_btn.count() > 0:
                    try:
                        run_btn.first.click(timeout=2000)
                        page.wait_for_timeout(2400)
                    except Exception:
                        pass
                # scroll down a bit to show charts
                page.mouse.wheel(0, 400)
                page.wait_for_timeout(dwell_ms)
            except Exception as e:
                print(f"   skipped ({e!s})")

        # back to Overview to bookend
        try:
            page.get_by_text("Overview", exact=True).first.click(timeout=4000)
            page.wait_for_timeout(2000)
        except Exception:
            pass

        page.close()
        context.close()  # finalizes the video
        browser.close()

    # newest webm in DEMO_DIR
    webms = sorted(DEMO_DIR.glob("*.webm"), key=lambda p: p.stat().st_mtime)
    return webms[-1]


def convert(webm_path: Path) -> tuple[Path, Path]:
    mp4_path = DEMO_DIR / "dashboard.mp4"
    gif_path = DEMO_DIR / "dashboard.gif"

    # MP4: H.264, reasonable quality + small size
    print(">> webm → mp4 ...")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(webm_path),
        "-vf", "fps=24,scale=1280:-2:flags=lanczos",
        "-c:v", "libx264", "-preset", "slow", "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(mp4_path),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # GIF via two-pass palette for quality at reasonable size
    print(">> webm → gif (two-pass palette) ...")
    palette = DEMO_DIR / "_palette.png"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(webm_path),
        "-vf", "fps=12,scale=900:-2:flags=lanczos,palettegen=stats_mode=diff",
        str(palette),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(webm_path), "-i", str(palette),
        "-lavfi", "fps=12,scale=900:-2:flags=lanczos[v];[v][1:v]paletteuse=dither=bayer:bayer_scale=5",
        str(gif_path),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    palette.unlink()

    # rename webm to canonical name
    canonical_webm = DEMO_DIR / "dashboard.webm"
    if webm_path != canonical_webm:
        shutil.move(str(webm_path), str(canonical_webm))
    return mp4_path, gif_path


def main() -> int:
    proc = boot_streamlit()
    try:
        webm = record(proc)
        mp4, gif = convert(webm)
        canonical_webm = DEMO_DIR / "dashboard.webm"
        print(f"\n>> done")
        for label, p in [("webm", canonical_webm), ("mp4", mp4), ("gif", gif)]:
            if p.exists():
                print(f"   {label}   {p.relative_to(ROOT)}   {p.stat().st_size // 1024} KB")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
