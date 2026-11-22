"""Nearby healthcare facilities from OpenStreetMap (Overpass API) and place search (Nominatim).

Privacy: the user's coordinates are rounded to ~110 m before being sent to OpenStreetMap
servers, are never stored in our database, and are not logged. Distances are computed here
from the precise coordinates.
"""
from __future__ import annotations

import gzip
import json
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any

import numpy as np
import requests

from app.config import get_settings

log = logging.getLogger("healthai.places")

KINDS = {
    "hospital": '["amenity"="hospital"]',
    "clinic": '["amenity"~"^(clinic|doctors)$"]',
    "pharmacy": '["amenity"="pharmacy"]',
}

_cache: dict[tuple, tuple[float, list[dict]]] = {}
_CACHE_TTL = 3600  # facilities change rarely; also eases load on volunteer-run servers
_nominatim_lock = threading.Lock()
_nominatim_last = 0.0


class PlacesUnavailable(RuntimeError):
    pass


# ----------------------------------------------------------------- local extract (instant search)
# Built by ml/build_places.py (India, OpenStreetMap). Public Overpass servers often take 20–30 s or
# fail; inside the extract's coverage we search locally in milliseconds and never contact them.
LOCAL_FILE = Path(__file__).resolve().parents[1] / "data" / "osm_health_in.json.gz"
_local: dict | None = None
_local_lock = threading.Lock()


def local_index() -> dict | None:
    global _local
    if _local is None and LOCAL_FILE.exists():
        with _local_lock:
            if _local is None:
                with gzip.open(LOCAL_FILE, "rt", encoding="utf-8") as f:
                    doc = json.load(f)
                els = doc["elements"]
                _local = {
                    "elements": els,
                    "lat": np.radians(np.array([e["lat"] for e in els])),
                    "lon": np.radians(np.array([e["lon"] for e in els])),
                    "kind": np.array([_kind(e["tags"]) for e in els]),
                    "bbox": doc["bbox"],
                    "generated_at": doc.get("generated_at"),
                }
                log.info("local facility index: %d places (%s)", len(els), doc.get("generated_at"))
    return _local


def _local_search(idx: dict, lat: float, lon: float, radius_km: float, kinds: list[str]) -> list[dict] | None:
    b = idx["bbox"]
    if not (b[0] - 0.3 <= lat <= b[2] + 0.3 and b[1] - 0.3 <= lon <= b[3] + 0.3):
        return None  # outside coverage → live Overpass
    p1, l1 = math.radians(lat), math.radians(lon)
    a = np.sin((idx["lat"] - p1) / 2) ** 2 + math.cos(p1) * np.cos(idx["lat"]) * np.sin((idx["lon"] - l1) / 2) ** 2
    d = 2 * 6371.0088 * np.arcsin(np.sqrt(a))
    sel = np.flatnonzero((d <= radius_km) & np.isin(idx["kind"], kinds))
    sel = sel[np.argsort(d[sel])][:200]
    return [idx["elements"][i] for i in sel]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _query(lat: float, lon: float, radius_m: int, kinds: list[str]) -> str:
    parts = []
    for k in kinds:
        f = KINDS[k]
        parts.append(f"nwr{f}(around:{radius_m},{lat},{lon});")
    return f"[out:json][timeout:25];({''.join(parts)});out center tags 200;"


def _address(tags: dict) -> str | None:
    if tags.get("addr:full"):
        return tags["addr:full"]
    bits = [
        " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x),
        tags.get("addr:suburb") or tags.get("addr:neighbourhood"),
        tags.get("addr:city") or tags.get("addr:district"),
        tags.get("addr:postcode"),
    ]
    s = ", ".join(b for b in bits if b)
    return s or None


def _kind(tags: dict) -> str:
    a = tags.get("amenity")
    if a == "hospital":
        return "hospital"
    if a == "pharmacy":
        return "pharmacy"
    return "clinic"


OVERALL_TIMEOUT = 25  # seconds the user waits at most


def _one_overpass(url: str, q: str) -> list[dict]:
    s = get_settings()
    r = requests.post(url, data={"data": q}, headers={"User-Agent": s.osm_user_agent}, timeout=OVERALL_TIMEOUT)
    if r.status_code in (429, 502, 503, 504):
        raise requests.HTTPError(f"{r.status_code} from {url}")
    r.raise_for_status()
    return r.json().get("elements", [])


def _fetch_overpass(q: str) -> list[dict]:
    """Query all configured public Overpass servers in parallel; the first good answer wins.
    Public servers are often overloaded, so racing them keeps worst-case latency bounded."""
    urls = get_settings().overpass_urls
    pool = ThreadPoolExecutor(max_workers=len(urls))
    futures = {pool.submit(_one_overpass, u, q): u for u in urls}
    errors = []
    try:
        for fut in as_completed(futures, timeout=OVERALL_TIMEOUT + 2):
            try:
                return fut.result()
            except (requests.RequestException, ValueError) as e:
                errors.append(f"{futures[fut]}: {e}")
                log.warning("Overpass %s failed: %s", futures[fut], e)
    except FuturesTimeout:
        errors.append("overall timeout")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    raise PlacesUnavailable("; ".join(errors))


def nearby(lat: float, lon: float, radius_km: float, kinds: list[str]) -> list[dict[str, Any]]:
    radius_m = int(radius_km * 1000)
    qlat, qlon = round(lat, 3), round(lon, 3)  # ~110 m precision sent to third parties
    key = (qlat, qlon, radius_m, tuple(sorted(kinds)))
    now = time.time()
    hit = _cache.get(key)
    idx = local_index()
    local = _local_search(idx, lat, lon, radius_km, kinds) if idx else None
    if local is not None:
        elements = local
    elif hit and now - hit[0] < _CACHE_TTL:
        elements = hit[1]
    else:
        elements = _fetch_overpass(_query(qlat, qlon, radius_m, kinds))
        _cache[key] = (now, elements)
        if len(_cache) > 500:
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
                _cache.pop(k, None)

    out = []
    for el in elements:
        tags = el.get("tags", {})
        plat = el.get("lat") or el.get("center", {}).get("lat")
        plon = el.get("lon") or el.get("center", {}).get("lon")
        if plat is None or plon is None:
            continue
        dist = haversine_km(lat, lon, plat, plon)
        if dist > radius_km * 1.05:
            continue
        name = tags.get("name") or tags.get("name:en") or tags.get("operator")
        out.append(
            {
                "id": f"{el['type']}/{el['id']}",
                "name": name,
                "name_en": tags.get("name:en"),
                "kind": _kind(tags),
                "lat": plat,
                "lon": plon,
                "distance_km": round(dist, 2),
                "address": _address(tags),
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "website": tags.get("website") or tags.get("contact:website"),
                "emergency": tags.get("emergency") == "yes",
                "opening_hours": tags.get("opening_hours"),
                "operator": tags.get("operator"),
                "directions_url": f"https://www.google.com/maps/dir/?api=1&destination={plat},{plon}",
                "osm_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
            }
        )
    out.sort(key=lambda d: d["distance_km"])
    return out


def geocode(q: str, language: str = "en") -> list[dict]:
    """Place search (Nominatim). Usage policy: max 1 request/second, identifying User-Agent."""
    global _nominatim_last
    s = get_settings()
    with _nominatim_lock:
        wait = 1.0 - (time.time() - _nominatim_last)
        if wait > 0:
            time.sleep(wait)
        _nominatim_last = time.time()
    try:
        r = requests.get(
            s.nominatim_url,
            params={"q": q, "format": "jsonv2", "limit": 5, "countrycodes": "in", "accept-language": f"{language},en"},
            headers={"User-Agent": s.osm_user_agent},
            timeout=15,
        )
        r.raise_for_status()
        rows = r.json()
    except (requests.RequestException, ValueError) as e:
        raise PlacesUnavailable(str(e))
    return [{"name": x.get("display_name"), "lat": float(x["lat"]), "lon": float(x["lon"])} for x in rows]
