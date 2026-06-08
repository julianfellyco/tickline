#!/usr/bin/env python3
"""Playwright smoke test — proves browser automation works in tickline.

Loads the simple board (static file), waits for the category cards to
render, expands the first category, and confirms the company chips appear.
This is the difference from raw `chrome --screenshot`: Playwright can
*interact* (click, wait for dynamic content), which is what E2E needs.

    python scripts/pw_smoke.py
"""

from __future__ import annotations

import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
URL = (ROOT / "web" / "simple" / "index.html").as_uri()


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 1000})
        page.goto(URL)

        page.wait_for_selector(".card", timeout=10000)
        cards = page.locator(".card").count()

        # interact: expand the first category, confirm the company chips load
        page.locator(".card").first.click()
        page.wait_for_selector(".card.open .stk-chip", timeout=5000)
        chips = page.locator(".card.open .stk-chip").count()

        # interact further: open a company briefing modal
        page.locator(".card.open .stk-chip").first.click()
        page.wait_for_selector(".modal-overlay:not([hidden])", timeout=5000)
        has_modal = page.locator(".modal .md-head h2").count() > 0

        page.screenshot(path="/tmp/pw_smoke.png")
        browser.close()

    assert cards >= 10, f"expected category cards, got {cards}"
    assert chips >= 1, f"expected company chips, got {chips}"
    assert has_modal, "company briefing modal did not open"
    print(f"playwright OK · {cards} category cards · {chips} chips · modal opened ✓")
    print("screenshot -> /tmp/pw_smoke.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
