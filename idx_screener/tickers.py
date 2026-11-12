"""Daftar emiten IDX (likuid, mayoritas anggota LQ45/IDX80/Kompas100) beserta sektornya.

Kode di sini TANPA akhiran ".JK"; akhiran ditambahkan saat mengambil data dari Yahoo Finance.
Silakan tambah/kurangi sesuai kebutuhan, atau berikan daftar sendiri lewat --tickers / --tickers-file.
"""

UNIVERSE: dict[str, str] = {
    # Keuangan
    "BBCA": "Keuangan", "BBRI": "Keuangan", "BMRI": "Keuangan", "BBNI": "Keuangan",
    "BRIS": "Keuangan", "BBTN": "Keuangan", "ARTO": "Keuangan", "BNGA": "Keuangan",
    "NISP": "Keuangan", "BDMN": "Keuangan", "PNBN": "Keuangan", "BTPS": "Keuangan",
    "BJBR": "Keuangan", "BJTM": "Keuangan", "SRTG": "Keuangan",
    # Infrastruktur & Telekomunikasi
    "TLKM": "Infrastruktur", "ISAT": "Infrastruktur", "EXCL": "Infrastruktur",
    "TOWR": "Infrastruktur", "TBIG": "Infrastruktur", "MTEL": "Infrastruktur",
    "JSMR": "Infrastruktur", "PGAS": "Infrastruktur", "WIKA": "Infrastruktur",
    "PTPP": "Infrastruktur", "ADHI": "Infrastruktur",
    # Energi
    "ADRO": "Energi", "PTBA": "Energi", "ITMG": "Energi", "INDY": "Energi",
    "HRUM": "Energi", "BUMI": "Energi", "MEDC": "Energi", "AKRA": "Energi",
    "ELSA": "Energi", "AADI": "Energi", "DSSA": "Energi", "BREN": "Energi",
    "PGEO": "Energi", "CUAN": "Energi", "RAJA": "Energi",
    # Barang Baku
    "ANTM": "Barang Baku", "INCO": "Barang Baku", "MDKA": "Barang Baku",
    "TINS": "Barang Baku", "NCKL": "Barang Baku", "MBMA": "Barang Baku",
    "AMMN": "Barang Baku", "BRMS": "Barang Baku", "SMGR": "Barang Baku",
    "INTP": "Barang Baku", "INKP": "Barang Baku", "TKIM": "Barang Baku",
    "BRPT": "Barang Baku", "TPIA": "Barang Baku", "ESSA": "Barang Baku",
    "AVIA": "Barang Baku",
    # Konsumen Primer
    "UNVR": "Konsumen Primer", "ICBP": "Konsumen Primer", "INDF": "Konsumen Primer",
    "MYOR": "Konsumen Primer", "CPIN": "Konsumen Primer", "JPFA": "Konsumen Primer",
    "GGRM": "Konsumen Primer", "HMSP": "Konsumen Primer", "AMRT": "Konsumen Primer",
    "AALI": "Konsumen Primer", "LSIP": "Konsumen Primer", "DSNG": "Konsumen Primer",
    "SIDO": "Konsumen Primer", "ULTJ": "Konsumen Primer", "CMRY": "Konsumen Primer",
    # Konsumen Non-Primer
    "ACES": "Konsumen Non-Primer", "MAPI": "Konsumen Non-Primer",
    "MAPA": "Konsumen Non-Primer", "ERAA": "Konsumen Non-Primer",
    "LPPF": "Konsumen Non-Primer", "AUTO": "Konsumen Non-Primer",
    "SCMA": "Konsumen Non-Primer", "MNCN": "Konsumen Non-Primer",
    "MSIN": "Konsumen Non-Primer",
    # Kesehatan
    "KLBF": "Kesehatan", "MIKA": "Kesehatan", "HEAL": "Kesehatan",
    "SILO": "Kesehatan", "PRDA": "Kesehatan",
    # Perindustrian
    "ASII": "Perindustrian", "UNTR": "Perindustrian", "ARNA": "Perindustrian",
    # Properti
    "BSDE": "Properti", "CTRA": "Properti", "PWON": "Properti",
    "SMRA": "Properti", "ASRI": "Properti", "PANI": "Properti",
    # Teknologi
    "GOTO": "Teknologi", "BUKA": "Teknologi", "EMTK": "Teknologi",
    "MTDL": "Teknologi", "DCII": "Teknologi", "WIFI": "Teknologi",
    # Transportasi & Logistik
    "ASSA": "Transportasi", "BIRD": "Transportasi", "SMDR": "Transportasi",
    "TMAS": "Transportasi",
}

SECTORS = sorted(set(UNIVERSE.values()))


def to_yahoo(code: str) -> str:
    code = code.strip().upper()
    return code if code.endswith(".JK") else f"{code}.JK"


def from_yahoo(symbol: str) -> str:
    return symbol.upper().removesuffix(".JK")
