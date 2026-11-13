"""CLI screener saham IDX.

Contoh:
    python -m idx_screener --preset momentum
    python -m idx_screener --filter "rsi14 < 30" --filter "per < 10" --sort rsi14 --asc
    python -m idx_screener --preset value --sector Keuangan --csv hasil.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from . import data
from .formatting import DEFAULT_COLUMNS, format_table
from .screener import PRESETS, build_table, needs_fundamentals, score, screen
from .tickers import SECTORS, UNIVERSE


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="idx_screener", description="Screener saham Bursa Efek Indonesia")
    p.add_argument("-p", "--preset", choices=sorted(PRESETS), help="Strategi siap pakai")
    p.add_argument("-f", "--filter", action="append", default=[],
                   help='Kondisi filter, bisa berulang. Contoh: -f "rsi14 < 30" -f "per < 10"')
    p.add_argument("-s", "--sort", help="Kolom pengurutan (default: dari preset atau 'score')")
    p.add_argument("--asc", action="store_true", help="Urutkan menaik")
    p.add_argument("--sector", action="append", help=f"Filter sektor. Pilihan: {', '.join(SECTORS)}")
    p.add_argument("-t", "--tickers", help="Daftar kode dipisah koma, mis. BBCA,BBRI,TLKM")
    p.add_argument("--tickers-file", type=Path, help="File berisi satu kode per baris")
    p.add_argument("-n", "--limit", type=int, default=30, help="Jumlah baris ditampilkan (default 30)")
    p.add_argument("-c", "--columns", help="Kolom tampilan dipisah koma")
    p.add_argument("--period", default="2y", help="Periode data harga (default 2y)")
    p.add_argument("--fundamentals", choices=["auto", "yes", "no"], default="auto",
                   help="Ambil data fundamental (lebih lambat). Default: auto sesuai filter")
    p.add_argument("--no-cache", action="store_true", help="Abaikan cache lokal")
    p.add_argument("--csv", type=Path, help="Simpan hasil lengkap ke CSV")
    p.add_argument("--list-presets", action="store_true", help="Tampilkan daftar preset")
    p.add_argument("--list-columns", action="store_true", help="Tampilkan kolom yang bisa difilter")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


COLUMN_DOCS = """\
Teknikal : close, chg_1d, chg_1w, chg_1m, chg_3m, chg_6m, chg_1y (persen)
           volume, vol_avg20, vol_ratio, value, value_avg20 (Rp nilai transaksi)
           ma5, ma20, ma50, ma200, rsi14, macd, macd_signal, macd_hist, atr14, atr_pct,
           bb_upper, bb_lower, high_52w, low_52w, from_high_52w, from_low_52w (persen),
           volatility_1y, tick, tick_pct, lot_value, dist_ma20 (persen dari MA20)
Trading  : stop (harga - 1.5xATR, dibulatkan fraksi), stop_pct, target (2R)
Bandar*  : cmf20 (Chaikin Money Flow), obv_up, accumulation, distribution
           *proksi dari harga & volume, BUKAN broker summary / data asing
Boolean  : above_ma20, above_ma50, above_ma200, uptrend, golden_cross, death_cross,
           macd_cross_up, macd_cross_down, ma20_cross_up, new_high_20d
Fundamen : per, forward_per, pbv, eps, bvps, roe, roa, npm, der (x), div_yield,
           payout, rev_growth, eps_growth (persen), beta, market_cap, earnings_yield
Lainnya  : sector, score (0-100)
Contoh   : -f "rsi14 < 30 and above_ma200" -f "value_avg20 > 5e9" -f "sector == 'Energi'"
"""


def load_codes(args) -> list[str]:
    if args.tickers:
        return [c.strip().upper().removesuffix(".JK") for c in args.tickers.split(",") if c.strip()]
    if args.tickers_file:
        lines = args.tickers_file.read_text().splitlines()
        return [l.strip().upper().removesuffix(".JK") for l in lines if l.strip() and not l.startswith("#")]
    return list(UNIVERSE)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s: %(message)s")

    if args.list_presets:
        for name, cfg in PRESETS.items():
            print(f"{name:14} {cfg['desc']}\n{'':14} {' AND '.join(cfg['filters'])}")
        return 0
    if args.list_columns:
        print(COLUMN_DOCS)
        return 0

    filters = list(args.filter)
    sort, ascending = args.sort, args.asc
    preset_fund = False
    preset_cols = None
    if args.preset:
        cfg = PRESETS[args.preset]
        filters = cfg["filters"] + filters
        if not sort:
            sort, ascending = cfg["sort"], cfg["ascending"]
        preset_fund = cfg.get("needs_fundamentals", False)
        preset_cols = cfg.get("columns")
    sort = sort or "score"

    codes = load_codes(args)
    use_cache = not args.no_cache
    print(f"Mengambil data harga {len(codes)} emiten...", file=sys.stderr)
    prices = data.fetch_prices(codes, period=args.period, use_cache=use_cache)
    if not prices:
        print("Gagal mengambil data harga. Periksa koneksi internet.", file=sys.stderr)
        return 1

    want_fund = args.fundamentals == "yes" or (
        args.fundamentals == "auto"
        and (preset_fund or needs_fundamentals(filters, sort) or sort == "score")
    )
    fund = None
    if want_fund:
        print("Mengambil data fundamental (pertama kali agak lama)...", file=sys.stderr)
        fund = data.fetch_fundamentals(list(prices), use_cache=use_cache)

    table = build_table(prices, fund)
    table["score"] = score(table)

    try:
        result = screen(table, filters, sort=sort, ascending=ascending, sector=args.sector)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2

    last_date = pd.to_datetime(table["last_date"]).max().date()
    print(f"\nData per {last_date} | {len(result)} dari {len(table)} emiten lolos filter")
    if filters:
        print("Filter: " + " AND ".join(filters))
    print(f"Urut   : {sort} ({'naik' if ascending else 'turun'})\n")

    if args.columns:
        columns = args.columns.split(",")
    elif preset_cols:
        columns = ["sector"] + list(preset_cols)
    else:
        columns = DEFAULT_COLUMNS + ["score"]
    if sort not in columns:
        columns.append(sort)
    if result.empty:
        print("Tidak ada saham yang memenuhi kriteria.")
    else:
        with pd.option_context("display.max_rows", None, "display.width", 200,
                               "display.max_columns", None):
            print(format_table(result.head(args.limit), columns).to_string())

    if args.csv:
        result.drop(columns=["last_date"], errors="ignore").round(4).to_csv(args.csv)
        print(f"\nHasil disimpan ke {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
