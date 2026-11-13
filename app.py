"""UI web screener saham IDX. Jalankan: streamlit run app.py"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from idx_screener import data
from idx_screener.screener import PRESETS, build_table, score, screen
from idx_screener.tickers import SECTORS, UNIVERSE

st.set_page_config(page_title="Screener Saham IDX", layout="wide")
st.title("Screener Saham IDX")


@st.cache_data(ttl=60 * 60, show_spinner="Mengambil data harga...")
def load_prices(codes: tuple[str, ...], period: str):
    return data.fetch_prices(list(codes), period=period)


@st.cache_data(ttl=60 * 60 * 12, show_spinner="Mengambil data fundamental...")
def load_fundamentals(codes: tuple[str, ...]):
    return data.fetch_fundamentals(list(codes))


with st.sidebar:
    if st.button("🔄 Perbarui data", type="primary", width="stretch",
                 help="Ambil ulang harga & fundamental terbaru dari Yahoo Finance"):
        data.clear_cache()
        st.cache_data.clear()
        st.session_state["refreshed"] = True
        st.rerun()
    fetched_slot = st.empty()
    st.header("Universe")
    custom = st.text_area("Kode saham (opsional, pisah koma)", placeholder="BBCA, BBRI, TLKM")
    sectors = st.multiselect("Sektor", SECTORS)
    with_fund = st.checkbox("Sertakan fundamental (PER, PBV, ROE, dividen)", value=True)
    period = st.selectbox("Periode data", ["1y", "2y", "5y"], index=1)

    st.header("Strategi")
    preset = st.selectbox("Preset", ["(tanpa preset)"] + list(PRESETS),
                          format_func=lambda k: k if k not in PRESETS else f"{k} — {PRESETS[k]['desc']}")

    st.header("Filter cepat")
    rsi_rng = st.slider("RSI(14)", 0, 100, (0, 100))
    min_value = st.number_input("Nilai transaksi rata-rata 20H minimal (Rp miliar)", 0.0, value=1.0, step=1.0)
    trend = st.multiselect("Kondisi tren", ["above_ma20", "above_ma50", "above_ma200", "uptrend",
                                             "golden_cross", "macd_cross_up", "new_high_20d"])
    if with_fund:
        max_per = st.number_input("PER maksimal (0 = abaikan)", 0.0, value=0.0)
        max_pbv = st.number_input("PBV maksimal (0 = abaikan)", 0.0, value=0.0)
        min_roe = st.number_input("ROE minimal % (0 = abaikan)", 0.0, value=0.0)
        min_div = st.number_input("Dividend yield minimal % (0 = abaikan)", 0.0, value=0.0)
    extra = st.text_area("Filter lanjutan (satu per baris)", placeholder="vol_ratio > 2\nchg_1m > 5")

codes = [c.strip().upper().removesuffix(".JK") for c in custom.replace("\n", ",").split(",") if c.strip()]
codes = tuple(codes or UNIVERSE)

prices = load_prices(codes, period)
ts = data.cache_time()
if ts:
    fetched_slot.caption(f"Data diambil: {datetime.fromtimestamp(ts):%d %b %Y %H:%M}")
if st.session_state.pop("refreshed", False):
    st.toast("Data berhasil diperbarui", icon="✅")
if not prices:
    st.error("Gagal mengambil data harga. Periksa koneksi internet.")
    st.stop()
fund = load_fundamentals(tuple(prices)) if with_fund else None
table = build_table(prices, fund)
table["score"] = score(table)

filters: list[str] = []
sort, asc = "score", False
if preset in PRESETS:
    cfg = PRESETS[preset]
    if cfg.get("needs_fundamentals") and not with_fund:
        st.warning("Preset ini butuh data fundamental — aktifkan centang fundamental.")
    else:
        filters += cfg["filters"]
        sort, asc = cfg["sort"], cfg["ascending"]
if rsi_rng != (0, 100):
    filters.append(f"rsi14 >= {rsi_rng[0]} and rsi14 <= {rsi_rng[1]}")
if min_value > 0:
    filters.append(f"value_avg20 >= {min_value * 1e9}")
filters += trend
if with_fund:
    if max_per:
        filters.append(f"per > 0 and per <= {max_per}")
    if max_pbv:
        filters.append(f"pbv > 0 and pbv <= {max_pbv}")
    if min_roe:
        filters.append(f"roe >= {min_roe}")
    if min_div:
        filters.append(f"div_yield >= {min_div}")
filters += [l for l in extra.splitlines() if l.strip()]

try:
    result = screen(table, filters, sort=sort, ascending=asc, sector=sectors)
except ValueError as e:
    st.error(str(e))
    st.stop()

last_date = pd.to_datetime(table["last_date"]).max().date()
c1, c2, c3 = st.columns(3)
c1.metric("Lolos filter", f"{len(result)} / {len(table)}")
c2.metric("Data per", str(last_date))
c3.metric("Urut", f"{sort} {'↑' if asc else '↓'}")
if filters:
    st.caption("Filter: " + "  •  ".join(filters))

cols = ["name", "sector", "close", "chg_1d", "chg_1w", "chg_1m", "chg_3m", "rsi14", "vol_ratio",
        "value_avg20", "from_high_52w", "uptrend", "per", "pbv", "roe", "der", "div_yield",
        "market_cap", "score"]
show = result[[c for c in cols if c in result.columns]].copy()
for c in ("value_avg20", "market_cap"):
    if c in show:
        show[c] = show[c] / 1e9
st.dataframe(
    show,
    width="stretch",
    height=560,
    column_config={
        "name": "Nama", "sector": "Sektor",
        "close": st.column_config.NumberColumn("Harga", format="%d"),
        "chg_1d": st.column_config.NumberColumn("%1H", format="%.2f"),
        "chg_1w": st.column_config.NumberColumn("%1M", format="%.2f"),
        "chg_1m": st.column_config.NumberColumn("%1B", format="%.2f"),
        "chg_3m": st.column_config.NumberColumn("%3B", format="%.2f"),
        "rsi14": st.column_config.NumberColumn("RSI", format="%.1f"),
        "vol_ratio": st.column_config.NumberColumn("Vol x", format="%.2f"),
        "value_avg20": st.column_config.NumberColumn("Nilai 20H (M)", format="%.1f"),
        "from_high_52w": st.column_config.NumberColumn("dr High52W %", format="%.1f"),
        "per": st.column_config.NumberColumn("PER", format="%.2f"),
        "pbv": st.column_config.NumberColumn("PBV", format="%.2f"),
        "roe": st.column_config.NumberColumn("ROE %", format="%.1f"),
        "der": st.column_config.NumberColumn("DER x", format="%.2f"),
        "div_yield": st.column_config.NumberColumn("Div %", format="%.2f"),
        "market_cap": st.column_config.NumberColumn("MCap (M)", format="%,.0f"),
        "score": st.column_config.ProgressColumn("Skor", min_value=0, max_value=100, format="%.0f"),
    },
)
st.download_button("Unduh CSV", result.drop(columns=["last_date"]).to_csv().encode(),
                   "screener_idx.csv", "text/csv")

if not result.empty:
    st.subheader("Grafik")
    pick = st.selectbox("Pilih saham", list(result.index))
    df = prices[pick].copy()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()
    st.line_chart(df[["Close", "MA20", "MA50", "MA200"]].iloc[-252:])
    st.bar_chart(df["Volume"].iloc[-120:])

st.caption("Data dari Yahoo Finance (bisa tertunda ±15 menit / EOD). Bukan rekomendasi jual/beli.")
