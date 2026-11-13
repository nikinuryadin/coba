# Screener Saham IDX

Screener saham Bursa Efek Indonesia (IDX) berbasis Python — data dari Yahoo Finance (`yfinance`).
Tersedia sebagai **CLI** dan **web UI (Streamlit)**.

## Instalasi cepat (Windows)

1. Pasang Python 3.10+ dari https://www.python.org/downloads/ (centang **Add Python to PATH**).
2. Unduh repo ini (tombol **Code → Download ZIP**) lalu ekstrak.
3. Klik dua kali **`install.bat`** (sekali saja, beberapa menit).
4. Klik dua kali **`jalankan.bat`** — screener terbuka di browser (`http://localhost:8501`).
   Biarkan jendela hitamnya terbuka; tutup untuk berhenti.

## Instalasi manual

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Web UI

```bash
streamlit run app.py
```

Sidebar berisi pilihan universe/sektor, preset strategi, filter cepat (RSI, likuiditas, tren,
PER, PBV, ROE, dividen) dan filter lanjutan bebas. Hasil bisa diunduh CSV, dan ada grafik
harga + MA20/50/200 per saham.

## CLI

```bash
python -m idx_screener --list-presets            # daftar strategi
python -m idx_screener --list-columns            # kolom yang bisa difilter
python -m idx_screener --preset momentum
python -m idx_screener --preset value --sector Keuangan
python -m idx_screener -f "rsi14 < 30" -f "above_ma200" -f "value_avg20 > 5e9" --sort rsi14 --asc
python -m idx_screener -t BBCA,BBRI,BMRI,BBNI -c close,per,pbv,roe,div_yield --sort pbv --asc
python -m idx_screener --preset dividend --csv dividen.csv
```

Filter memakai sintaks `pandas.query`: `and`, `or`, `not`, `==`, `<`, `>`, dan kolom boolean
bisa langsung dipakai (mis. `uptrend`, `golden_cross`). Beberapa `-f` digabung dengan AND.

### Preset

| Preset | Kriteria |
|---|---|
| `value` | PER 0–12, PBV < 1,5, ROE > 10%, nilai transaksi rata-rata > Rp5 M |
| `dividend` | Dividend yield > 5%, payout < 90%, ROE > 8% |
| `quality` | ROE > 15%, DER < 1x, NPM > 10%, PER 0–25 |
| `garp` | EPS growth > 15%, PER 0–20, ROE > 12%, di atas MA50 |
| `momentum` | Harga > MA20 > MA50 > MA200, RSI 50–70, < 10% dari high 52 minggu |
| `oversold` | RSI < 30 tapi masih di atas MA200 |
| `rebound` | RSI < 30 |
| `breakout` | High 20 hari baru + volume > 1,5x rata-rata |
| `volume_spike` | Volume > 2x rata-rata 20 hari |
| `golden_cross` | MA50 memotong ke atas MA200 dalam 5 hari terakhir |
| `macd_bullish` | MACD cross ke atas signal, harga > MA50 |

### Kolom utama

- **Teknikal**: `close`, `chg_1d/1w/1m/3m/6m/1y` (%), `rsi14`, `ma5/20/50/200`, `macd`, `macd_hist`,
  `atr_pct`, `vol_ratio` (volume hari ini / rata-rata 20H), `value_avg20` (nilai transaksi rata-rata, Rp),
  `from_high_52w`, `from_low_52w` (%), `volatility_1y`, `tick` (fraksi harga), `lot_value` (harga 1 lot)
- **Boolean**: `above_ma20/50/200`, `uptrend`, `golden_cross`, `death_cross`, `macd_cross_up/down`,
  `ma20_cross_up`, `new_high_20d`
- **Fundamental**: `per`, `pbv`, `roe`, `roa`, `npm`, `der` (x), `div_yield`, `payout`, `rev_growth`,
  `eps_growth` (%), `market_cap`, `earnings_yield`
- **Skor**: `score` 0–100 (rata-rata peringkat persentil earnings yield, PBV, ROE, momentum 1B & 6B)

PER dan PBV dihitung ulang dari harga penutupan terakhir ÷ EPS/BVPS agar selalu mutakhir.

## Universe

Default ±100 saham likuid (LQ45/IDX80/Kompas100) di `idx_screener/tickers.py`. Ganti dengan
`--tickers` atau `--tickers-file daftar.txt` (satu kode per baris, tanpa `.JK`).

## Catatan

- Data Yahoo Finance bersifat EOD/tertunda dan fundamental kadang kosong/terlambat untuk emiten IDX.
  Verifikasi dengan laporan keuangan resmi (idx.co.id) sebelum mengambil keputusan.
- Cache disimpan di `.cache/` (harga 4 jam, fundamental 24 jam). Pakai `--no-cache` untuk menyegarkan.
- Bukan rekomendasi jual/beli.

## Tes

```bash
pytest -q
```
