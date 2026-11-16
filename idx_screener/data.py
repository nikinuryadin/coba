"""Pengambilan data harga & fundamental dari Yahoo Finance (via yfinance), dengan cache lokal."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from .tickers import from_yahoo, to_yahoo

log = logging.getLogger(__name__)

CACHE_DIR = Path(".cache")
PRICE_TTL = 60 * 60 * 4        # 4 jam
FUNDAMENTAL_TTL = 60 * 60 * 24  # 24 jam


def _yf():
    try:
        import yfinance as yf
    except ImportError as e:  # pragma: no cover
        raise SystemExit("yfinance belum terpasang. Jalankan: pip install -r requirements.txt") from e
    return yf


def clear_cache() -> int:
    """Hapus semua cache harga & fundamental di disk. Mengembalikan jumlah file yang dihapus."""
    n = 0
    if CACHE_DIR.exists():
        for f in CACHE_DIR.rglob("*"):
            if f.is_file() and f.suffix in {".pkl", ".json"}:
                f.unlink(missing_ok=True)
                n += 1
    return n


def cache_time() -> float | None:
    """Waktu (epoch) file cache harga terbaru, atau None bila belum ada."""
    files = list(CACHE_DIR.glob("prices_v2_*.pkl")) if CACHE_DIR.exists() else []
    return max((f.stat().st_mtime for f in files), default=None)


def _fresh(path: Path, ttl: int) -> bool:
    return path.exists() and time.time() - path.stat().st_mtime < ttl


def fetch_prices(
    codes: list[str],
    period: str = "2y",
    use_cache: bool = True,
    chunk_size: int = 50,
) -> dict[str, pd.DataFrame]:
    """Unduh OHLCV harian. Mengembalikan {kode: DataFrame[Open, High, Low, Close, Volume]}."""
    CACHE_DIR.mkdir(exist_ok=True)
    digest = hashlib.md5(",".join(sorted(c.upper() for c in codes)).encode()).hexdigest()[:10]
    key = f"prices_v2_{period}_{digest}.pkl"
    cache = CACHE_DIR / key
    if use_cache and _fresh(cache, PRICE_TTL):
        return pd.read_pickle(cache)

    yf = _yf()
    result: dict[str, pd.DataFrame] = {}
    symbols = [to_yahoo(c) for c in codes]
    for i in range(0, len(symbols), chunk_size):
        batch = symbols[i : i + chunk_size]
        raw = yf.download(
            batch,
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            actions=True,
            threads=True,
            progress=False,
        )
        if raw is None or raw.empty:
            continue
        for sym in batch:
            try:
                df = raw[sym] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                continue
            cols = [c for c in ("Open", "High", "Low", "Close", "Volume", "Dividends") if c in df]
            df = df[cols].dropna(subset=["Close"])
            if not df.empty:
                result[from_yahoo(sym)] = df
    if use_cache and result:
        pd.to_pickle(result, cache)
    missing = set(c.upper() for c in codes) - set(result)
    if missing:
        log.warning("Tidak ada data harga untuk: %s", ", ".join(sorted(missing)))
    return result


def _num(v) -> float:
    try:
        f = float(v)
        return f if np.isfinite(f) else np.nan
    except (TypeError, ValueError):
        return np.nan


def parse_info(info: dict) -> dict:
    """Ambil metrik fundamental penting dari Ticker.info dan normalisasi satuannya (persen)."""
    pct = lambda k: _num(info.get(k)) * 100  # noqa: E731  (fraksi -> persen)

    # yfinance >= 0.2.54 memberi dividendYield dalam PERSEN (3.5 = 3,5%).
    # trailingAnnualDividendYield tidak dipakai: untuk emiten berlaporan USD
    # dividen (USD) dibagi harga (IDR) sehingga hasilnya ~0.
    div = _num(info.get("dividendYield"))
    return {
        "name": info.get("shortName") or info.get("longName"),
        "market_cap": _num(info.get("marketCap")),
        "per": _num(info.get("trailingPE")),
        "forward_per": _num(info.get("forwardPE")),
        "pbv": _num(info.get("priceToBook")),
        "eps": _num(info.get("trailingEps")),
        "bvps": _num(info.get("bookValue")),
        "roe": pct("returnOnEquity"),
        "roa": pct("returnOnAssets"),
        "npm": pct("profitMargins"),
        "der": _num(info.get("debtToEquity")) / 100,  # Yahoo memberi dalam persen
        "div_yield": div,
        "payout": pct("payoutRatio"),
        "rev_growth": pct("revenueGrowth"),
        "eps_growth": pct("earningsGrowth"),
        "beta": _num(info.get("beta")),
        "fin_currency": (info.get("financialCurrency") or "IDR").upper(),
    }


def fetch_fundamentals(
    codes: list[str], use_cache: bool = True, workers: int = 8
) -> pd.DataFrame:
    """Ambil fundamental per emiten (paralel). Hasil di-cache per emiten selama 24 jam."""
    yf = _yf()
    fdir = CACHE_DIR / "fundamentals_v2"
    fdir.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict] = {}
    todo = []
    for c in codes:
        p = fdir / f"{c.upper()}.json"
        if use_cache and _fresh(p, FUNDAMENTAL_TTL):
            rows[c.upper()] = json.loads(p.read_text())
        else:
            todo.append(c.upper())

    def work(code: str) -> tuple[str, dict]:
        for attempt in range(3):
            try:
                info = yf.Ticker(to_yahoo(code)).info or {}
                return code, parse_info(info)
            except Exception as e:  # jaringan / rate limit
                log.debug("info %s gagal (%s), coba lagi", code, e)
                time.sleep(1.5 * (attempt + 1))
        return code, {}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in as_completed([ex.submit(work, c) for c in todo]):
            code, data = fut.result()
            rows[code] = data
            if data:
                (fdir / f"{code}.json").write_text(json.dumps(data))
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "code"
    if "fin_currency" in df:
        currencies = {c for c in df["fin_currency"].dropna().unique() if c != "IDR"}
        rates = {c: fetch_fx_rate(c, use_cache) for c in currencies}
        df["fx_to_idr"] = df["fin_currency"].map(lambda c: 1.0 if c == "IDR" else rates.get(c, np.nan))
    return df


def fetch_fx_rate(currency: str, use_cache: bool = True) -> float:
    """Kurs 1 unit `currency` dalam rupiah (mis. USD -> ~16.000)."""
    CACHE_DIR.mkdir(exist_ok=True)
    p = CACHE_DIR / f"fx_{currency}.json"
    if use_cache and _fresh(p, FUNDAMENTAL_TTL):
        return json.loads(p.read_text())["rate"]
    try:
        hist = _yf().Ticker(f"{currency}IDR=X").history(period="5d")
        rate = float(hist["Close"].dropna().iloc[-1])
    except Exception as e:
        log.warning("Kurs %s/IDR gagal diambil (%s); PBV emiten berlaporan %s dikosongkan", currency, e, currency)
        return np.nan
    p.write_text(json.dumps({"rate": rate}))
    return rate

