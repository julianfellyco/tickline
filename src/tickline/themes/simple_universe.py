"""Simple-board universe — the curated stocks behind each ETF category.

Shared single source of truth so both the board builder (build_simple.py)
and the backtest (run_trend_backtest.py) draw the same list, instead of
one script importing the other.

Keyed by the category's ETF ticker (matches build_simple's THEMES). Lists
are hand-curated major liquid US names — broad, but not the whole market,
and they drift over time (no automatic index membership).
"""

from __future__ import annotations

STOCKS: dict[str, list[str]] = {
    "SMH":  ["NVDA", "AVGO", "AMD", "TSM", "MU", "QCOM", "TXN", "AMAT", "LRCX", "KLAC",
             "ADI", "MRVL", "MCHP", "NXPI", "ON", "SMCI", "ASML", "ARM", "ALAB", "CRDO", "ENTG", "MPWR"],
    "IGV":  ["MSFT", "CRM", "NOW", "PLTR", "SNOW", "ORCL", "ADBE", "INTU", "PANW", "CRWD",
             "DDOG", "TEAM", "WDAY", "NET", "SHOP", "HUBS", "MDB", "APP"],
    "QQQ":  ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "NFLX", "COST",
             "PEP", "CSCO", "AMD", "INTC", "QCOM", "TXN", "AMAT", "ADBE"],
    "CIBR": ["CRWD", "PANW", "ZS", "FTNT", "NET", "S", "OKTA", "CYBR", "TENB", "QLYS",
             "RPD", "VRNS", "GEN", "AKAM"],
    "BOTZ": ["NVDA", "ISRG", "TSLA", "PATH", "TER", "ROK", "EMR", "ZBRA", "IRBT", "SERV", "NDSN"],
    "IBIT": ["COIN", "MSTR", "MARA", "RIOT", "HOOD", "CLSK", "WULF", "CIFR", "BITF", "HUT",
             "IREN", "CORZ"],
    "URA":  ["CCJ", "OKLO", "SMR", "LEU", "UEC", "UUUU", "DNN", "NNE", "NXE", "BWXT", "GEV"],
    "TAN":  ["FSLR", "ENPH", "RUN", "NXT", "SEDG", "ARRY", "SHLS", "CSIQ", "JKS", "MAXN", "NOVA"],
    "XLE":  ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "OXY", "WMB", "KMI", "HAL",
             "DVN", "FANG", "HES", "BKR", "OKE"],
    "GDX":  ["NEM", "AEM", "GOLD", "WPM", "FNV", "KGC", "AU", "GFI", "RGLD", "AGI", "BTG", "HMY", "OR"],
    "SIL":  ["PAAS", "AG", "HL", "WPM", "FNV", "CDE", "SVM", "EXK", "MAG", "FSM", "SILV", "GATO"],
    "COPX": ["FCX", "SCCO", "TECK", "BHP", "RIO", "VALE", "ERO", "HBM", "TGB", "IVN"],
    "ITA":  ["LMT", "RTX", "NOC", "GD", "BA", "LHX", "HII", "TXT", "LDOS", "HWM", "AXON",
             "KTOS", "TDG", "HEI"],
    "UFO":  ["RKLB", "LUNR", "ASTS", "RDW", "PL", "BKSY", "SPCE", "ASTR", "VSAT"],
    "XBI":  ["VRTX", "REGN", "MRNA", "GILD", "AMGN", "BIIB", "ALNY", "INCY", "NBIX", "SRPT",
             "EXAS", "NTLA", "BNTX", "ARGX"],
    "XLF":  ["JPM", "BAC", "WFC", "GS", "MS", "C", "USB", "PNC", "TFC", "SCHW", "AXP", "COF", "BK"],
    "XHB":  ["DHI", "LEN", "PHM", "NVR", "TOL", "KBH", "MTH", "TPH", "BLDR", "BLD", "MAS", "SHW"],
    "XLU":  ["NEE", "SO", "DUK", "CEG", "VST", "AEP", "D", "EXC", "SRE", "XEL", "ED", "PEG", "ETR", "WEC"],
}


def all_company_tickers() -> list[str]:
    """Every distinct company across all categories."""
    return sorted({s for syms in STOCKS.values() for s in syms})
