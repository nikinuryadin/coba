import numpy as np
import pandas as pd
import pytest

from idx_screener.data import parse_info
from idx_screener.indicators import compute_technicals, rsi, tick_size
from idx_screener.screener import PRESETS, apply_filters, build_table, needs_fundamentals, score, screen


def make_ohlcv(closes, volume=1_000_000):
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    vol = volume if np.ndim(volume) else np.full(len(c), volume)
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": vol})


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert rsi(up).iloc[-1] == pytest.approx(100)
    down = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert rsi(down).iloc[-1] == pytest.approx(0)
    rng = np.random.default_rng(0)
    noisy = pd.Series(1000 + rng.normal(0, 10, 300).cumsum())
    r = rsi(noisy).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_tick_size():
    assert tick_size(150) == 1
    assert tick_size(300) == 2
    assert tick_size(1500) == 5
    assert tick_size(4500) == 10
    assert tick_size(9000) == 25


def test_uptrend_and_golden_cross():
    closes = np.r_[np.linspace(2000, 1000, 250), np.linspace(1000, 2500, 120)]
    t = compute_technicals(make_ohlcv(closes))
    assert t["uptrend"] or t["above_ma200"]
    assert t["rsi14"] > 70
    # MA50 harus sudah melewati MA200 di suatu titik
    df = make_ohlcv(closes)
    ma50 = df.Close.rolling(50).mean(); ma200 = df.Close.rolling(200).mean()
    assert (ma50 > ma200).iloc[-1]


def test_volume_spike_and_breakout():
    closes = np.r_[np.full(60, 1000.0), [1100.0]]
    vol = np.r_[np.full(60, 1e6), [5e6]]
    t = compute_technicals(make_ohlcv(closes, vol))
    assert t["vol_ratio"] > 4
    assert t["new_high_20d"]
    assert t["chg_1d"] == pytest.approx(10)
    assert t["value"] == pytest.approx(1100 * 5e6)


def sample_table():
    prices = {
        "UPP": make_ohlcv(np.linspace(1000, 2000, 300), 5e6),
        "DWN": make_ohlcv(np.linspace(2000, 800, 300), 5e6),
        "FLT": make_ohlcv(1000 + np.sin(np.arange(300) / 5) * 20, 1e5),
    }
    fund = pd.DataFrame(
        {"per": [8.0, -3.0, 20.0], "pbv": [1.0, 0.5, 3.0], "roe": [18.0, -5.0, 10.0],
         "eps": [250.0, -50.0, 50.0], "bvps": [2000.0, 1600.0, 333.0], "div_yield": [4.0, 0, 1.0]},
        index=pd.Index(["UPP", "DWN", "FLT"], name="code"),
    )
    return build_table(prices, fund, sectors={"UPP": "Keuangan", "DWN": "Energi"})


def test_build_and_screen():
    t = sample_table()
    assert set(t.index) == {"UPP", "DWN", "FLT"}
    assert t.loc["FLT", "sector"] == "Lainnya"
    # PER dihitung ulang dari harga terkini / EPS
    assert t.loc["UPP", "per"] == pytest.approx(2000 / 250)
    assert t.loc["DWN", "per"] == pytest.approx(-3.0)  # EPS negatif -> pakai nilai asli
    res = screen(t, ["above_ma200", "per > 0"], sort="roe")
    assert list(res.index) == ["UPP"]
    assert list(screen(t, sector=["energi"]).index) == ["DWN"]
    assert screen(t, ["rsi14 < 30"]).index.tolist() == ["DWN"]


def test_score_range():
    t = sample_table()
    s = score(t)
    assert s.between(0, 100).all()
    assert s["UPP"] > s["DWN"]


def test_bad_filter_message():
    with pytest.raises(ValueError, match="Kolom tersedia"):
        apply_filters(sample_table(), ["tidak_ada > 1"])


def test_all_presets_run():
    t = sample_table()
    for col in ["forward_per", "roa", "npm", "der", "payout", "rev_growth", "eps_growth"]:
        t[col] = 10.0
    t["der"] = 0.5
    for name, cfg in PRESETS.items():
        screen(t, cfg["filters"], sort=cfg["sort"], ascending=cfg["ascending"])


def test_needs_fundamentals():
    assert needs_fundamentals(["per < 10"])
    assert not needs_fundamentals(["rsi14 < 30", "uptrend"])
    assert needs_fundamentals([], sort="div_yield")


def test_parse_info_units():
    d = parse_info({"trailingPE": 9.5, "returnOnEquity": 0.21, "debtToEquity": 45.0,
                    "trailingAnnualDividendYield": 0.052, "shortName": "Bank X"})
    assert d["roe"] == pytest.approx(21)
    assert d["der"] == pytest.approx(0.45)
    assert d["div_yield"] == pytest.approx(5.2)
    d2 = parse_info({"dividendYield": 3.5})
    assert d2["div_yield"] == pytest.approx(3.5)
    assert np.isnan(parse_info({})["per"])
