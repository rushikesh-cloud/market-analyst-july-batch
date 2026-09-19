"""NSE equity input normalization without relabeling stored legacy symbols."""

import re

_PATTERN = re.compile(r"[A-Z0-9]+(?:[&-][A-Z0-9]+)*(?:\.NS)?", re.ASCII)
TICKER_ERROR = "Enter an NSE equity ticker, such as RELIANCE.NS or M&M."


def normalize_nse_ticker(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(TICKER_ERROR)
    symbol = value.strip().upper()
    if not _PATTERN.fullmatch(symbol):
        raise ValueError(TICKER_ERROR)
    canonical = symbol if symbol.endswith('.NS') else symbol + '.NS'
    if len(canonical) > 40:
        raise ValueError('The canonical NSE ticker must be at most 40 characters.')
    return canonical


def is_canonical_nse_ticker(value: str) -> bool:
    try:
        return value == normalize_nse_ticker(value)
    except ValueError:
        return False
