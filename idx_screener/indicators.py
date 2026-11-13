"""Indikator teknikal murni berbasis pandas (tanpa dependensi TA eksternal)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI metode Wilder."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    # Tidak ada penurunan sama sekali -> RSI 100
    out = out.where(avg_loss != 0, 100.0)
    return out.where(avg_gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, sig, line - sig


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def pct_change_over(close: pd.Series, n: int) -> float:
    if len(close) <= n:
        return np.nan
    prev = close.iloc[-n - 1]
    return (close.iloc[-1] / prev - 1) * 100 if prev else np.nan


def tick_size(price: float) -> int:
    """Fraksi harga IDX untuk saham reguler."""
    if price < 200:
        return 1
    if price < 500:
        return 2
    if price < 2000:
        return 5
    if price < 5000:
        return 10
    return 25


def round_to_tick(price: float, up: bool = False) -> float:
    """Bulatkan harga ke fraksi harga IDX yang valid (ke bawah, atau ke atas bila up=True)."""
    if not np.isfinite(price) or price <= 0:
        return np.nan
    t = tick_size(price)
    q = price / t
    return float((np.ceil(q - 1e-9) if up else np.floor(q + 1e-9)) * t)


def cmf(high, low, close, volume, n: int = 20) -> pd.Series:
    """Chaikin Money Flow: >0 tekanan beli (akumulasi), <0 tekanan jual (distribusi)."""
    rng = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / rng
    mfv = mfm.fillna(0) * volume
    return mfv.rolling(n, min_periods=n).sum() / volume.rolling(n, min_periods=n).sum()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    return (np.sign(close.diff()).fillna(0) * volume).cumsum()


def _last(s: pd.Series) -> float:
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else np.nan


def _crossed_up(a: pd.Series, b: pd.Series, lookback: int) -> bool:
    """True jika a memotong ke atas b dalam `lookback` bar terakhir."""
    diff = (a - b).dropna()
    if len(diff) < 2:
        return False
    recent = diff.iloc[-(lookback + 1):]
    above = recent > 0
    return bool(above.iloc[-1] and (~above.iloc[:-1]).any())


def _crossed_down(a: pd.Series, b: pd.Series, lookback: int) -> bool:
    return _crossed_up(b, a, lookback)


def compute_technicals(df: pd.DataFrame, cross_lookback: int = 5) -> dict:
    """Hitung ringkasan teknikal dari OHLCV harian (kolom: Open, High, Low, Close, Volume)."""
    df = df.dropna(subset=["Close"])
    if len(df) < 2:
        return {}
    close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"].fillna(0)

    ma5, ma20, ma50, ma200 = sma(close, 5), sma(close, 20), sma(close, 50), sma(close, 200)
    r = rsi(close, 14)
    m_line, m_sig, m_hist = macd(close)
    a = atr(high, low, close, 14)
    value = close * vol  # nilai transaksi (Rp)

    last = float(close.iloc[-1])
    win = close.iloc[-252:]
    hi52, lo52 = float(high.iloc[-252:].max()), float(low.iloc[-252:].min())
    vol20 = _last(sma(vol, 20))
    bb_mid, bb_std = sma(close, 20), close.rolling(20, min_periods=20).std()

    out = {
        "close": last,
        "chg_1d": pct_change_over(close, 1),
        "chg_1w": pct_change_over(close, 5),
        "chg_1m": pct_change_over(close, 21),
        "chg_3m": pct_change_over(close, 63),
        "chg_6m": pct_change_over(close, 126),
        "chg_1y": pct_change_over(close, 252),
        "volume": float(vol.iloc[-1]),
        "vol_avg20": vol20,
        "vol_ratio": float(vol.iloc[-1]) / vol20 if vol20 else np.nan,
        "value": float(value.iloc[-1]),
        "value_avg20": _last(sma(value, 20)),
        "ma5": _last(ma5),
        "ma20": _last(ma20),
        "ma50": _last(ma50),
        "ma200": _last(ma200),
        "rsi14": _last(r),
        "macd": _last(m_line),
        "macd_signal": _last(m_sig),
        "macd_hist": _last(m_hist),
        "atr14": _last(a),
        "atr_pct": _last(a) / last * 100 if last else np.nan,
        "bb_upper": _last(bb_mid + 2 * bb_std),
        "bb_lower": _last(bb_mid - 2 * bb_std),
        "high_52w": hi52,
        "low_52w": lo52,
        "from_high_52w": (last / hi52 - 1) * 100 if hi52 else np.nan,
        "from_low_52w": (last / lo52 - 1) * 100 if lo52 else np.nan,
        "volatility_1y": float(win.pct_change().std() * np.sqrt(252) * 100) if len(win) > 20 else np.nan,
        "tick": tick_size(last),
        "lot_value": last * 100,  # 1 lot = 100 lembar
        "golden_cross": _crossed_up(ma50, ma200, cross_lookback),
        "death_cross": _crossed_down(ma50, ma200, cross_lookback),
        "macd_cross_up": _crossed_up(m_line, m_sig, cross_lookback),
        "macd_cross_down": _crossed_down(m_line, m_sig, cross_lookback),
        "ma20_cross_up": _crossed_up(close, ma20, cross_lookback),
        "new_high_20d": bool(len(close) > 20 and last >= close.iloc[-21:-1].max()),
        "bars": len(df),
    }
    # --- Rencana trading berbasis ATR (stop 1,5x ATR, target 2R), dibulatkan ke fraksi harga
    a_last = out["atr14"]
    stop = round_to_tick(last - 1.5 * a_last) if np.isfinite(a_last) else np.nan
    risk = last - stop if np.isfinite(stop) else np.nan
    out["stop"] = stop
    out["stop_pct"] = (stop / last - 1) * 100 if np.isfinite(stop) else np.nan
    out["target"] = round_to_tick(last + 2 * risk, up=True) if np.isfinite(risk) and risk > 0 else np.nan
    out["tick_pct"] = out["tick"] / last * 100 if last else np.nan
    out["dist_ma20"] = (last / out["ma20"] - 1) * 100 if out["ma20"] else np.nan
    # --- Proksi akumulasi/distribusi dari harga & volume (BUKAN data broker summary)
    c = cmf(high, low, close, vol, 20)
    o = obv(close, vol)
    o_ma = sma(o, 20)
    out["cmf20"] = _last(c)
    out["obv_up"] = bool(len(o_ma.dropna()) and o.iloc[-1] > o_ma.iloc[-1])
    out["accumulation"] = bool(
        np.isfinite(out["cmf20"]) and out["cmf20"] > 0.1 and out["obv_up"]
    )
    out["distribution"] = bool(
        np.isfinite(out["cmf20"]) and out["cmf20"] < -0.1 and not out["obv_up"]
    )
    if "Dividends" in df:
        since = df.index[-1] - pd.Timedelta(days=365)
        div_ttm = float(df.loc[df.index > since, "Dividends"].fillna(0).sum())
        out["div_ttm"] = div_ttm
        out["div_yield_hist"] = div_ttm / last * 100 if last else np.nan
    out["above_ma20"] = bool(last > out["ma20"]) if not np.isnan(out["ma20"]) else False
    out["above_ma50"] = bool(last > out["ma50"]) if not np.isnan(out["ma50"]) else False
    out["above_ma200"] = bool(last > out["ma200"]) if not np.isnan(out["ma200"]) else False
    out["uptrend"] = bool(
        not np.isnan(out["ma200"]) and last > out["ma20"] > out["ma50"] > out["ma200"]
    )
    return out
