# modules/data/city_coords_tr.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, Tuple
import requests

LatLon = Tuple[float, float]

# 81 il plaka -> il adı
PLATE_TO_PROVINCE_TR: dict[int, str] = {
    1: "Adana",
    2: "Adıyaman",
    3: "Afyonkarahisar",
    4: "Ağrı",
    5: "Amasya",
    6: "Ankara",
    7: "Antalya",
    8: "Artvin",
    9: "Aydın",
    10: "Balıkesir",
    11: "Bilecik",
    12: "Bingöl",
    13: "Bitlis",
    14: "Bolu",
    15: "Burdur",
    16: "Bursa",
    17: "Çanakkale",
    18: "Çankırı",
    19: "Çorum",
    20: "Denizli",
    21: "Diyarbakır",
    22: "Edirne",
    23: "Elazığ",
    24: "Erzincan",
    25: "Erzurum",
    26: "Eskişehir",
    27: "Gaziantep",
    28: "Giresun",
    29: "Gümüşhane",
    30: "Hakkâri",
    31: "Hatay",
    32: "Isparta",
    33: "Mersin",
    34: "İstanbul",
    35: "İzmir",
    36: "Kars",
    37: "Kastamonu",
    38: "Kayseri",
    39: "Kırklareli",
    40: "Kırşehir",
    41: "Kocaeli",
    42: "Konya",
    43: "Kütahya",
    44: "Malatya",
    45: "Manisa",
    46: "Kahramanmaraş",
    47: "Mardin",
    48: "Muğla",
    49: "Muş",
    50: "Nevşehir",
    51: "Niğde",
    52: "Ordu",
    53: "Rize",
    54: "Sakarya",
    55: "Samsun",
    56: "Siirt",
    57: "Sinop",
    58: "Sivas",
    59: "Tekirdağ",
    60: "Tokat",
    61: "Trabzon",
    62: "Tunceli",
    63: "Şanlıurfa",
    64: "Uşak",
    65: "Van",
    66: "Yozgat",
    67: "Zonguldak",
    68: "Aksaray",
    69: "Bayburt",
    70: "Karaman",
    71: "Kırıkkale",
    72: "Batman",
    73: "Şırnak",
    74: "Bartın",
    75: "Ardahan",
    76: "Iğdır",
    77: "Yalova",
    78: "Karabük",
    79: "Kilis",
    80: "Osmaniye",
    81: "Düzce",
}

# Gist RAW (ilçe lat/lon)
# Not: GitHub gist "raw" URL formatı genelde böyledir.
ILCELER_JSON_URL = (
    "https://gist.githubusercontent.com/mebaysan/"
    "b9f3cc1ad9c1f4294a0a7c7a7be9ec62/raw/ilceler.json"
)

DATA_DIR = Path(__file__).resolve().parent
ILCELER_JSON_PATH = DATA_DIR / "ilceler.json"


def _ensure_ilceler_json(path: Path = ILCELER_JSON_PATH, url: str = ILCELER_JSON_URL) -> None:
    """
    ilceler.json dosyası yoksa indirir.
    """
    if path.exists() and path.stat().st_size > 100_000:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    path.write_bytes(r.content)


def build_tr_location_dicts(
    normalize_fn: Callable[[str], str],
    *,
    ilceler_json_path: Path = ILCELER_JSON_PATH,
    auto_download: bool = True,
) -> tuple[
    Dict[str, LatLon],                 # CITY_COORDS_TR
    Dict[str, Dict[str, LatLon]],      # DISTRICT_COORDS_TR
    Dict[str, LatLon],                 # CITY_COORDS_TR_NORM
    Dict[str, Dict[str, LatLon]],      # DISTRICT_COORDS_TR_NORM
]:
    """
    81 il + tüm ilçe koordinat sözlüklerini üretir.

    CITY_COORDS_TR: İl -> (lat, lon)  (ilçelerin ortalaması)
    DISTRICT_COORDS_TR: İl -> İlçe -> (lat, lon)
    *_NORM: normalize_fn ile normalize edilmiş anahtarlar (hızlı eşleşme için)
    """
    if auto_download:
        _ensure_ilceler_json(ilceler_json_path)

    data = json.loads(ilceler_json_path.read_text(encoding="utf-8"))

    district_coords: Dict[str, Dict[str, LatLon]] = {}
    accum: Dict[str, list[LatLon]] = {}

    for rec in data:
        plaka = int(rec["il_plaka"])
        il = PLATE_TO_PROVINCE_TR.get(plaka)
        if not il:
            # bilinmeyen plaka -> atla
            continue

        ilce = str(rec["ilce_adi"]).strip()
        lat = float(rec["lat"])
        lon = float(rec["lon"])

        district_coords.setdefault(il, {})[ilce] = (lat, lon)
        accum.setdefault(il, []).append((lat, lon))

    # 81 ili garantiye al: hiç ilçe gelmeyen olursa None bırakma (pratikte gelmeli)
    city_coords: Dict[str, LatLon] = {}
    for plaka, il in PLATE_TO_PROVINCE_TR.items():
        pts = accum.get(il) or []
        if not pts:
            # çok uç durumda: (0,0) vermek yerine hata üretmek daha güvenli
            # ama prod'da patlamasın diye Türkiye merkezine yakın bir fallback:
            city_coords[il] = (39.0, 35.0)
            continue
        city_coords[il] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    # Normalize indexler
    city_coords_norm: Dict[str, LatLon] = {}
    for il, ll in city_coords.items():
        city_coords_norm[normalize_fn(il)] = ll

    district_coords_norm: Dict[str, Dict[str, LatLon]] = {}
    for il, dmap in district_coords.items():
        iln = normalize_fn(il)
        district_coords_norm.setdefault(iln, {})
        for ilce, ll in dmap.items():
            district_coords_norm[iln][normalize_fn(ilce)] = ll

    return city_coords, district_coords, city_coords_norm, district_coords_norm
