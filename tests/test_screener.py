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
                    "dividendYield": 5.2, "shortName": "Bank X", "financialCurrency": "usd"})
    assert d["roe"] == pytest.approx(21)
    assert d["der"] == pytest.approx(0.45)
    assert d["fin_currency"] == "USD"
    # dividendYield dari yfinance baru sudah persen: 0.83 artinya 0,83%, bukan 83%
    assert parse_info({"dividendYield": 0.83})["div_yield"] == pytest.approx(0.83)
    # trailingAnnualDividendYield (salah mata uang untuk emiten USD) tidak dipakai
    assert np.isnan(parse_info({"trailingAnnualDividendYield": 0.0000028})["div_yield"])
    assert np.isnan(parse_info({})["per"])
    assert parse_info({})["fin_currency"] == "IDR"


def test_usd_reporter_pbv_converted_to_idr():
    """Regresi: ADRO/ITMG/PGAS dll. dulu PBV-nya ribuan karena BVPS dalam USD."""
    prices = {"USDCO": make_ohlcv(np.full(260, 2480.0)), "IDRCO": make_ohlcv(np.full(260, 1000.0))}
    fund = pd.DataFrame(
        {"bvps": [0.175, 800.0], "eps": [396.0, 100.0], "pbv": [14171.0, 1.3], "per": [6.3, 10.0],
         "div_yield": [np.nan, 4.0], "fx_to_idr": [16000.0, 1.0]},
        index=pd.Index(["USDCO", "IDRCO"], name="code"),
    )
    t = build_table(prices, fund)
    assert t.loc["USDCO", "pbv"] == pytest.approx(2480 / (0.175 * 16000))  # ~0.89
    assert t.loc["USDCO", "per"] == pytest.approx(2480 / 396)  # EPS sudah IDR -> tidak dikonversi
    assert t.loc["IDRCO", "pbv"] == pytest.approx(1.25)


def test_usd_reporter_without_fx_has_no_pbv():
    prices = {"USDCO": make_ohlcv(np.full(30, 2480.0))}
    fund = pd.DataFrame({"bvps": [0.175], "pbv": [14171.0], "fx_to_idr": [np.nan]},
                        index=pd.Index(["USDCO"], name="code"))
    assert np.isnan(build_table(prices, fund).loc["USDCO", "pbv"])


def test_dividend_from_history_and_sanity_cap():
    a = make_ohlcv(np.full(300, 1000.0)); a["Dividends"] = 0.0
    a.iloc[-100, a.columns.get_loc("Dividends")] = 50.0   # dalam 1 tahun
    a.iloc[-290, a.columns.get_loc("Dividends")] = 999.0  # > 1 tahun lalu, diabaikan
    b = make_ohlcv(np.full(300, 1000.0)); b["Dividends"] = 0.0
    fund = pd.DataFrame({"div_yield": [1.0, 83.0]}, index=pd.Index(["A", "B"], name="code"))
    t = build_table({"A": a, "B": b}, fund)
    assert t.loc["A", "div_yield"] == pytest.approx(5.0)  # 50/1000, dari riwayat dividen
    assert np.isnan(t.loc["B", "div_yield"])  # 83% tidak masuk akal -> dikosongkan


def test_clear_cache(tmp_path, monkeypatch):
    from idx_screener import data
    monkeypatch.setattr(data, "CACHE_DIR", tmp_path)
    assert data.cache_time() is None
    (tmp_path / "prices_v2_2y_abc.pkl").write_bytes(b"x")
    (tmp_path / "fundamentals_v2").mkdir()
    (tmp_path / "fundamentals_v2" / "BBCA.json").write_text("{}")
    assert data.cache_time() is not None
    assert data.clear_cache() == 2
    assert data.cache_time() is None


def test_round_to_tick():
    from idx_screener.indicators import round_to_tick
    assert round_to_tick(1003.7) == 1000       # fraksi 5
    assert round_to_tick(1003.7, up=True) == 1005
    assert round_to_tick(4987) == 4980         # fraksi 10
    assert round_to_tick(5012) == 5000         # fraksi 25
    assert round_to_tick(137.6) == 137         # fraksi 1
    assert np.isnan(round_to_tick(-5))


def test_stop_and_target_valid_ticks():
    from idx_screener.indicators import tick_size
    rng = np.random.default_rng(3)
    closes = 3000 + rng.normal(0, 40, 120).cumsum()
    t = compute_technicals(make_ohlcv(closes))
    assert t["stop"] < t["close"] < t["target"]
    assert t["stop"] % tick_size(t["stop"]) == 0
    assert t["target"] % tick_size(t["target"]) == 0
    # target kira-kira 2x jarak stop (selisih karena pembulatan fraksi)
    assert (t["target"] - t["close"]) == pytest.approx(2 * (t["close"] - t["stop"]), abs=tick_size(t["target"]))


def test_cmf_accumulation_vs_distribution():
    n = 60
    idx = pd.bdate_range("2025-01-01", periods=n)
    c = pd.Series(np.linspace(1000, 1050, n), index=idx)
    # tutup dekat high setiap hari -> akumulasi
    acc = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.97, "Close": c * 1.008, "Volume": 1e6})
    t = compute_technicals(acc)
    assert t["cmf20"] > 0.5 and t["accumulation"] and not t["distribution"]
    # tutup dekat low, harga turun -> distribusi
    c2 = pd.Series(np.linspace(1050, 1000, n), index=idx)
    dist = pd.DataFrame({"Open": c2, "High": c2 * 1.03, "Low": c2 * 0.99, "Close": c2 * 0.992, "Volume": 1e6})
    t2 = compute_technicals(dist)
    assert t2["cmf20"] < -0.5 and t2["distribution"]


def test_daytrade_stop_tighter_than_swing():
    from idx_screener.indicators import tick_size
    rng = np.random.default_rng(5)
    t = compute_technicals(make_ohlcv(800 + rng.normal(0, 15, 120).cumsum()))
    assert t["stop"] < t["stop_dt"] < t["close"] < t["target_dt"]
    assert t["stop_dt"] % tick_size(t["stop_dt"]) == 0
    assert abs(t["stop_dt_pct"]) < abs(t["stop_pct"])
