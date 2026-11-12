"""Format angka gaya Indonesia untuk tampilan."""

from __future__ import annotations

import math

import pandas as pd


def rupiah_short(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    for div, suf in ((1e12, "T"), (1e9, "M"), (1e6, "Jt"), (1e3, "Rb")):
        if abs(v) >= div:
            return f"{v / div:,.1f}{suf}"
    return f"{v:,.0f}"


DEFAULT_COLUMNS = [
    "sector", "close", "chg_1d", "chg_1m", "rsi14", "vol_ratio", "value_avg20",
    "per", "pbv", "roe", "div_yield",
]

LABELS = {
    "sector": "Sektor", "close": "Harga", "chg_1d": "%1H", "chg_1w": "%1M", "chg_1m": "%1B",
    "chg_3m": "%3B", "chg_6m": "%6B", "chg_1y": "%1T", "rsi14": "RSI", "vol_ratio": "VolX",
    "value": "Nilai", "value_avg20": "NilaiRata20", "per": "PER", "pbv": "PBV", "roe": "ROE%",
    "div_yield": "Div%", "market_cap": "MCap", "der": "DER", "npm": "NPM%", "score": "Skor",
}

MONEY_COLS = {"value", "value_avg20", "market_cap", "vol_avg20", "volume", "lot_value"}


def format_table(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    cols = [c for c in columns if c in df.columns]
    out = df[cols].copy()
    for c in cols:
        s = out[c]
        if c in MONEY_COLS:
            out[c] = s.map(rupiah_short)
        elif c == "close":
            out[c] = s.map(lambda v: f"{v:,.0f}")
        elif pd.api.types.is_bool_dtype(s):
            out[c] = s.map({True: "ya", False: "-"})
        elif pd.api.types.is_float_dtype(s):
            out[c] = s.map(lambda v: "-" if pd.isna(v) else f"{v:,.2f}")
    return out.rename(columns=LABELS)
