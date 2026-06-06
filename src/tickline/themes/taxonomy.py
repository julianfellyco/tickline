"""US-market theme graph — the rotation universe.

Comprehensive map of the tradeable momentum/rotation themes in the US
market (mid-2026), grouped by sector. The cross-sectional rel-strength
rank (the backtest-validated signal) ranks themes against each other, so
a broader, more diverse universe = a truer read on where money rotates.

  ALL_THEMES   the full universe the live watchlist ranks.
  AI_THEMES    the original 10 AI legs — the validated-backtest subset,
               kept byte-for-byte so those results stay reproducible.
  GROUPS       display order for the sector buckets.

Each Theme is an equal-weight basket. `etf` gives a clean flow proxy
where a pure-play fund exists. Tickers are liquid US listings; baskets
degrade gracefully when a constituent has short history.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BENCHMARK = "SPY"  # relative-strength yardstick

GROUPS = (
    "AI / Semis",
    "Power / Energy",
    "Materials / Real economy",
    "Frontier tech",
    "Crypto / Fintech",
    "Health / Defense / Financials",
)


@dataclass(frozen=True)
class Theme:
    key: str                       # stable id, e.g. "power_grid"
    label: str                     # human label
    tickers: tuple[str, ...]       # equal-weight basket constituents
    etf: str | None = None         # pure-play ETF for flow proxy, if any
    keywords: tuple[str, ...] = field(default_factory=tuple)  # retail query terms
    group: str = ""                # sector bucket (see GROUPS)

    @property
    def query_terms(self) -> tuple[str, ...]:
        return self.keywords or (self.label,)


ALL_THEMES: tuple[Theme, ...] = (
    # ── AI / Semis ──────────────────────────────────────────────────────────
    Theme("compute_gpu", "AI Compute / GPU", ("NVDA", "AMD"),
          keywords=("Nvidia", "GPU", "AI chip"), group="AI / Semis"),
    Theme("custom_silicon", "Custom silicon / ASIC", ("AVGO", "MRVL", "ALAB", "CRDO"),
          keywords=("custom AI chip", "ASIC accelerator", "Marvell AI", "Astera Labs"),
          group="AI / Semis"),
    Theme("foundry", "Foundry / Fab", ("TSM", "INTC", "GFS"),
          keywords=("TSMC", "chip foundry", "semiconductor fab"), group="AI / Semis"),
    Theme("memory_hbm", "Memory / HBM", ("MU", "WDC", "STX"),
          keywords=("HBM", "memory chip", "Micron", "DRAM"), group="AI / Semis"),
    Theme("networking_optical", "Networking / Optical", ("AVGO", "ANET", "COHR", "LITE", "CIEN"),
          keywords=("AI networking", "optical transceiver", "Broadcom AI"), group="AI / Semis"),
    Theme("semicap", "Semi equipment", ("AMAT", "LRCX", "KLAC", "ASML"),
          keywords=("semiconductor equipment", "wafer fab equipment", "ASML"), group="AI / Semis"),
    Theme("semis_broad", "Semis (broad)", ("NVDA", "AVGO", "AMD", "TSM", "MU", "QCOM"),
          etf="SMH", keywords=("semiconductors", "chip stocks", "SOX index"), group="AI / Semis"),
    Theme("hyperscalers", "Hyperscalers", ("MSFT", "GOOGL", "AMZN", "META"),
          keywords=("hyperscaler capex", "cloud AI", "AI capex"), group="AI / Semis"),
    Theme("ai_software", "AI Software / Apps", ("PLTR", "NOW", "SNOW"),
          etf="IGV", keywords=("Palantir", "AI software", "enterprise AI"), group="AI / Semis"),
    Theme("neoclouds", "Neoclouds / AI infra", ("CRWV", "NBIS", "APLD", "IREN"),
          keywords=("CoreWeave", "Nebius", "AI cloud", "neocloud"), group="AI / Semis"),
    Theme("datacenter_reit", "Data Center REITs", ("EQIX", "DLR"),
          keywords=("data center REIT", "Equinix", "Digital Realty"), group="AI / Semis"),
    Theme("cybersecurity", "Cybersecurity", ("CRWD", "PANW", "ZS", "FTNT"),
          etf="CIBR", keywords=("cybersecurity", "CrowdStrike", "Palo Alto Networks"),
          group="AI / Semis"),

    # ── Power / Energy ──────────────────────────────────────────────────────
    Theme("power_grid", "Power / Grid for AI", ("VST", "CEG", "GEV", "NRG", "ETN", "POWL"),
          keywords=("data center power", "AI electricity demand", "grid"), group="Power / Energy"),
    Theme("nuclear_smr", "Nuclear / SMR", ("OKLO", "SMR", "NNE", "LEU"),
          keywords=("small modular reactor", "nuclear data center", "Oklo"), group="Power / Energy"),
    Theme("uranium", "Uranium", ("CCJ", "UEC", "UUUU", "DNN"),
          etf="URA", keywords=("uranium", "uranium price", "Cameco"), group="Power / Energy"),
    Theme("cooling_thermal", "Cooling / Thermal", ("VRT", "NVT"),
          keywords=("liquid cooling", "data center cooling", "Vertiv"), group="Power / Energy"),
    Theme("natgas_lng", "Natural gas / LNG", ("LNG", "EQT", "AR", "EXE"),
          keywords=("natural gas", "LNG export", "Cheniere"), group="Power / Energy"),
    Theme("oil_gas", "Oil & gas", ("XOM", "CVX", "COP", "EOG", "OXY"),
          etf="XLE", keywords=("oil price", "energy stocks", "crude"), group="Power / Energy"),
    Theme("solar_clean", "Solar / clean energy", ("FSLR", "ENPH", "RUN", "NXT"),
          etf="TAN", keywords=("solar stocks", "clean energy", "First Solar"), group="Power / Energy"),

    # ── Materials / Real economy ────────────────────────────────────────────
    Theme("copper", "Copper / base metals", ("FCX", "SCCO", "TECK"),
          etf="COPX", keywords=("copper price", "Freeport", "copper demand"),
          group="Materials / Real economy"),
    Theme("rare_earth", "Rare earth / critical minerals", ("MP", "TMC", "UAMY"),
          etf="REMX", keywords=("rare earth", "critical minerals", "MP Materials"),
          group="Materials / Real economy"),
    Theme("gold_miners", "Gold miners", ("NEM", "AEM", "GOLD", "WPM"),
          etf="GDX", keywords=("gold price", "gold miners", "gold stocks"),
          group="Materials / Real economy"),
    Theme("silver_miners", "Silver miners", ("PAAS", "AG", "HL"),
          etf="SIL", keywords=("silver price", "silver miners"), group="Materials / Real economy"),
    Theme("steel_metals", "Steel / metals", ("NUE", "STLD", "CLF", "RS"),
          etf="SLX", keywords=("steel stocks", "steel price", "Nucor"),
          group="Materials / Real economy"),
    Theme("industrials_infra", "Industrials / infrastructure", ("CAT", "DE", "PWR", "URI", "ETN"),
          etf="XLI", keywords=("industrials", "infrastructure buildout", "Caterpillar"),
          group="Materials / Real economy"),
    Theme("defense", "Defense / aerospace", ("LMT", "RTX", "NOC", "GD", "LHX"),
          etf="ITA", keywords=("defense stocks", "defense spending", "aerospace"),
          group="Materials / Real economy"),
    Theme("homebuilders", "Homebuilders", ("DHI", "LEN", "PHM", "NVR"),
          etf="XHB", keywords=("homebuilders", "housing market", "home construction"),
          group="Materials / Real economy"),

    # ── Frontier tech ───────────────────────────────────────────────────────
    Theme("quantum", "Quantum computing", ("IONQ", "RGTI", "QBTS", "QUBT"),
          keywords=("quantum computing", "IonQ", "Rigetti"), group="Frontier tech"),
    Theme("robotics_physical", "Humanoid / physical AI", ("TSLA", "SERV"),
          keywords=("humanoid robot", "physical AI", "Optimus"), group="Frontier tech"),
    Theme("space", "Space / satellites", ("RKLB", "LUNR", "ASTS", "RDW"),
          etf="UFO", keywords=("space stocks", "satellite", "Rocket Lab"), group="Frontier tech"),

    # ── Crypto / Fintech ────────────────────────────────────────────────────
    Theme("crypto_equities", "Crypto equities", ("COIN", "MSTR", "HOOD"),
          keywords=("Coinbase", "bitcoin treasury", "crypto stocks"), group="Crypto / Fintech"),
    Theme("bitcoin_miners", "Bitcoin miners", ("MARA", "RIOT", "CLSK", "WULF"),
          etf="WGMI", keywords=("bitcoin miners", "crypto mining", "hashrate"),
          group="Crypto / Fintech"),
    Theme("fintech_payments", "Fintech / payments", ("V", "MA", "PYPL", "AFRM"),
          keywords=("fintech", "payments", "Visa", "buy now pay later"), group="Crypto / Fintech"),

    # ── Health / Defense / Financials ───────────────────────────────────────
    Theme("obesity_glp1", "Obesity / GLP-1", ("LLY", "NVO", "VKTX", "HIMS"),
          keywords=("GLP-1", "weight loss drug", "Eli Lilly", "obesity")
          , group="Health / Defense / Financials"),
    Theme("biotech", "Biotech", ("VRTX", "REGN", "MRNA", "ALNY"),
          etf="XBI", keywords=("biotech stocks", "biotech rally"),
          group="Health / Defense / Financials"),
    Theme("pharma", "Pharma", ("JNJ", "MRK", "PFE", "ABBV"),
          keywords=("pharma stocks", "drug pricing"), group="Health / Defense / Financials"),
    Theme("big_banks", "Big banks", ("JPM", "BAC", "WFC", "GS", "MS"),
          etf="XLF", keywords=("bank stocks", "big banks", "financials"),
          group="Health / Defense / Financials"),
)

# Validated-backtest subset — the original 10 AI legs (do not change tickers).
_AI_KEYS = (
    "compute_gpu", "foundry", "memory_hbm", "networking_optical", "power_grid",
    "cooling_thermal", "datacenter_reit", "hyperscalers", "ai_software", "semis_broad",
)
AI_THEMES: tuple[Theme, ...] = tuple(t for t in ALL_THEMES if t.key in _AI_KEYS)


def all_tickers(themes: tuple[Theme, ...] = ALL_THEMES) -> list[str]:
    """Every distinct symbol the universe needs to fetch (incl. benchmark)."""
    seen: dict[str, None] = {}
    for theme in themes:
        for t in theme.tickers:
            seen.setdefault(t, None)
        if theme.etf:
            seen.setdefault(theme.etf, None)
    seen.setdefault(BENCHMARK, None)
    return list(seen)


def themes_in_group(group: str) -> tuple[Theme, ...]:
    return tuple(t for t in ALL_THEMES if t.group == group)


def theme_by_key(key: str) -> Theme:
    for theme in ALL_THEMES:
        if theme.key == key:
            return theme
    raise KeyError(f"unknown theme: {key}")
