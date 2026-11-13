"""Inti screener: menggabungkan teknikal + fundamental lalu memfilter dengan ekspresi."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .indicators import compute_technicals
from .tickers import UNIVERSE

# Preset strategi. Ekspresi memakai sintaks pandas.DataFrame.query
# (and/or/not, ==, <, >, kolom boolean langsung dipakai).
PRESETS: dict[str, dict] = {
    "value": {
        "desc": "Saham murah: PER & PBV rendah, ROE layak, likuid",
        "filters": ["per > 0", "per < 12", "pbv < 1.5", "roe > 10", "value_avg20 > 5e9"],
        "sort": "per",
        "ascending": True,
        "needs_fundamentals": True,
    },
    "dividend": {
        "desc": "Dividend yield tinggi dan payout berkelanjutan",
        "filters": ["div_yield > 5", "payout < 90", "roe > 8", "value_avg20 > 2e9"],
        "sort": "div_yield",
        "ascending": False,
        "needs_fundamentals": True,
    },
    "quality": {
        "desc": "Kualitas: ROE tinggi, utang rendah, margin sehat",
        "filters": ["roe > 15", "der < 1", "npm > 10", "per > 0", "per < 25"],
        "sort": "roe",
        "ascending": False,
        "needs_fundamentals": True,
    },
    "momentum": {
        "desc": "Uptrend kuat: MA tersusun naik, RSI 50-70, dekat high 52 minggu",
        "filters": ["uptrend", "rsi14 >= 50", "rsi14 <= 70", "from_high_52w > -10",
                    "value_avg20 > 5e9"],
        "sort": "chg_3m",
        "ascending": False,
    },
    "oversold": {
        "desc": "Jenuh jual: RSI < 30 di atas MA200 (koreksi dalam tren naik)",
        "filters": ["rsi14 < 30", "above_ma200", "value_avg20 > 2e9"],
        "sort": "rsi14",
        "ascending": True,
    },
    "rebound": {
        "desc": "Jenuh jual umum: RSI < 30, likuid",
        "filters": ["rsi14 < 30", "value_avg20 > 2e9"],
        "sort": "rsi14",
        "ascending": True,
    },
    "breakout": {
        "desc": "Breakout: high 20 hari baru dengan lonjakan volume",
        "filters": ["new_high_20d", "vol_ratio > 1.5", "chg_1d > 0", "value_avg20 > 2e9"],
        "sort": "vol_ratio",
        "ascending": False,
    },
    "volume_spike": {
        "desc": "Volume hari ini > 2x rata-rata 20 hari",
        "filters": ["vol_ratio > 2", "value > 1e9"],
        "sort": "vol_ratio",
        "ascending": False,
    },
    "golden_cross": {
        "desc": "MA50 baru memotong ke atas MA200 (5 hari terakhir)",
        "filters": ["golden_cross"],
        "sort": "value_avg20",
        "ascending": False,
    },
    "daytrade": {
        "desc": "Watchlist daytrade: sangat likuid, gerak harian lebar, volume naik, tick kecil",
        "filters": ["value_avg20 > 50e9", "atr_pct >= 2.5", "vol_ratio >= 1.2", "tick_pct <= 1"],
        "sort": "vol_ratio",
        "ascending": False,
        "columns": ["close", "chg_1d", "atr_pct", "vol_ratio", "value_avg20", "tick_pct",
                    "rsi14", "cmf20", "stop_dt", "stop_dt_pct", "target_dt"],
    },
    "swing": {
        "desc": "Swing pullback: tren naik (MA20 > MA50, di atas MA50), harga dekat MA20, RSI 40-60",
        "filters": ["above_ma50", "ma20 > ma50", "dist_ma20 >= -3", "dist_ma20 <= 3",
                    "rsi14 >= 40", "rsi14 <= 60", "value_avg20 > 10e9"],
        "sort": "chg_3m",
        "ascending": False,
        "columns": ["close", "chg_1w", "chg_3m", "rsi14", "dist_ma20", "cmf20", "value_avg20",
                    "stop", "stop_pct", "target"],
    },
    "akumulasi": {
        "desc": "Indikasi akumulasi kuat: CMF > 0.2, OBV naik, harga 1 bulan belum lari",
        "filters": ["accumulation", "cmf20 > 0.2", "chg_1m < 10", "value_avg20 > 5e9"],
        "sort": "cmf20",
        "ascending": False,
        "columns": ["close", "chg_1m", "cmf20", "obv_up", "vol_ratio", "value_avg20", "rsi14",
                    "stop", "stop_pct", "target"],
    },
    "macd_bullish": {
        "desc": "MACD baru cross ke atas signal, harga di atas MA50",
        "filters": ["macd_cross_up", "above_ma50", "value_avg20 > 2e9"],
        "sort": "macd_hist",
        "ascending": False,
    },
    "garp": {
        "desc": "Growth at reasonable price: laba tumbuh, PER wajar, tren naik",
        "filters": ["eps_growth > 15", "per > 0", "per < 20", "roe > 12", "above_ma50"],
        "sort": "eps_growth",
        "ascending": False,
        "needs_fundamentals": True,
    },
}

FUNDAMENTAL_COLS = {
    "per", "forward_per", "pbv", "eps", "bvps", "roe", "roa", "npm", "der",
    "div_yield", "payout", "rev_growth", "eps_growth", "beta", "market_cap",
}


def build_table(
    prices: dict[str, pd.DataFrame],
    fundamentals: pd.DataFrame | None = None,
    sectors: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Bangun tabel metrik: satu baris per emiten."""
    sectors = sectors or UNIVERSE
    rows = {}
    for code, df in prices.items():
        t = compute_technicals(df)
        if t:
            t["sector"] = sectors.get(code, "Lainnya")
            t["last_date"] = df.index[-1]
            rows[code] = t
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index.name = "code"
    if fundamentals is not None and not fundamentals.empty:
        table = table.join(fundamentals, how="left")
        _normalize_valuation(table)
    return table


MAX_PLAUSIBLE_DIV_YIELD = 30.0  # di atas ini hampir pasti data salah


def _normalize_valuation(table: pd.DataFrame) -> None:
    """Hitung ulang PER/PBV/dividen dari harga terakhir, dalam rupiah.

    Emiten berlaporan USD (ADRO, ITMG, PGAS, AMMN, dll.) diberi nilai buku per saham
    oleh Yahoo dalam USD, padahal harganya dalam IDR -> dikonversi dengan kurs.
    """
    close = table["close"]
    fx = table["fx_to_idr"] if "fx_to_idr" in table else pd.Series(1.0, index=table.index)
    foreign = fx.ne(1.0)

    if "bvps" in table:
        bvps = table["bvps"] * fx  # NaN bila kurs tak tersedia
        table["bvps"] = bvps
        pbv_live = close / bvps.where(bvps > 0)
        # priceToBook Yahoo untuk emiten berlaporan asing juga salah mata uang -> jangan dipakai
        table["pbv"] = pbv_live.fillna(table["pbv"].where(~foreign))
    if "eps" in table:
        eps = table["eps"]
        # EPS Yahoo biasanya sudah dalam IDR; konversi hanya bila jelas masih mata uang asing
        looks_foreign = foreign & (close / eps.abs() > 2000)
        eps = eps.where(~looks_foreign, eps * fx)
        table["eps"] = eps
        table["per"] = (close / eps.where(eps > 0)).fillna(table["per"])
        table["earnings_yield"] = eps / close * 100

    hist = table.get("div_yield_hist")
    if hist is not None:
        base = table["div_yield"] if "div_yield" in table else pd.Series(np.nan, index=table.index)
        table["div_yield"] = hist.where(hist > 0.05, base)
    if "div_yield" in table:
        table["div_yield"] = table["div_yield"].where(table["div_yield"] <= MAX_PLAUSIBLE_DIV_YIELD)


def needs_fundamentals(filters: list[str], sort: str | None = None) -> bool:
    text = " ".join(filters + ([sort] if sort else []))
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))
    return bool(words & (FUNDAMENTAL_COLS | {"earnings_yield", "name"}))


def apply_filters(table: pd.DataFrame, filters: list[str]) -> pd.DataFrame:
    """Terapkan filter (AND). Kolom yang tidak ada akan memunculkan ValueError yang jelas."""
    out = table
    for f in filters:
        f = f.strip()
        if not f:
            continue
        try:
            out = out.query(f, engine="python")
        except Exception as e:
            cols = ", ".join(sorted(table.columns))
            raise ValueError(f"Filter tidak valid: '{f}' ({e}).\nKolom tersedia: {cols}") from e
    return out


def screen(
    table: pd.DataFrame,
    filters: list[str] | None = None,
    sort: str | None = None,
    ascending: bool = False,
    sector: list[str] | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    out = table
    if sector:
        wanted = {s.lower() for s in sector}
        out = out[out["sector"].str.lower().isin(wanted)]
    out = apply_filters(out, filters or [])
    if sort:
        if sort not in out.columns:
            raise ValueError(f"Kolom sort tidak dikenal: {sort}")
        out = out.sort_values(sort, ascending=ascending, na_position="last")
    if limit:
        out = out.head(limit)
    return out


def score(table: pd.DataFrame) -> pd.Series:
    """Skor komposit 0-100 sederhana (percentile rank) gabungan value, kualitas, momentum."""
    parts = []

    def rank(col, higher_better=True):
        if col in table and table[col].notna().any():
            r = table[col].rank(pct=True, ascending=higher_better)
            parts.append(r)

    rank("earnings_yield")
    if "pbv" in table:
        parts.append(table["pbv"].where(table["pbv"] > 0).rank(pct=True, ascending=False))
    rank("roe")
    rank("chg_6m")
    rank("chg_1m")
    if not parts:
        return pd.Series(np.nan, index=table.index)
    return (pd.concat(parts, axis=1).mean(axis=1) * 100).round(1)
