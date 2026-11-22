"""Download India's healthcare facilities from OpenStreetMap once, for instant local search.

Public Overpass servers often take 20–30 s or fail under load, so the hospital finder searches this
local extract instead and only calls Overpass for places outside its coverage.

Output: backend/app/data/osm_health_in.json.gz — {"generated_at", "source", "license", "bbox",
"elements": [{"type","id","lat","lon","tags"}]} with only the tags the app shows.
Data © OpenStreetMap contributors, ODbL 1.0. Re-run periodically (e.g. monthly) to refresh.
"""
import gzip
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "osm_health_in.json.gz"
SERVERS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
QUERY = """[out:json][timeout:900];
area["ISO3166-1"="IN"][admin_level=2]->.in;
nwr["amenity"~"^(hospital|clinic|doctors|pharmacy)$"](area.in);
out center tags;"""
KEEP = ("name", "name:en", "amenity", "healthcare", "emergency", "phone", "contact:phone", "website",
        "contact:website", "opening_hours", "operator", "addr:full", "addr:housenumber", "addr:street",
        "addr:suburb", "addr:neighbourhood", "addr:city", "addr:district", "addr:postcode")
UA = "HealthAssistAI/1.0 (one-time healthcare facility extract; low volume)"


def fetch() -> list[dict]:
    for url in SERVERS:
        for attempt in range(2):
            t = time.time()
            try:
                print(f"querying {url} (attempt {attempt + 1}) …", flush=True)
                r = requests.post(url, data={"data": QUERY}, headers={"User-Agent": UA}, timeout=1000)
                r.raise_for_status()
                els = r.json()["elements"]
                print(f"  {len(els)} elements in {time.time() - t:.0f}s", flush=True)
                if len(els) > 1000:
                    return els
            except Exception as e:  # try the next attempt / server
                print(f"  failed after {time.time() - t:.0f}s: {e}", flush=True)
            time.sleep(10)
    sys.exit("all Overpass servers failed (try --tiles)")


def fetch_tiles(step: float = 2.0) -> list[dict]:
    """Fallback: query India's bounding box in step°×step° tiles (small queries public servers accept).
    Tiles are filtered to India afterwards by the country area, so sea/neighbour tiles return little."""
    els: dict[tuple, dict] = {}
    tiles = [(la, lo) for la in [6.0 + i * step for i in range(int(32 / step))] for lo in [68.0 + j * step for j in range(int(30 / step))]]
    for n, (la, lo) in enumerate(tiles, 1):
        q = (f'[out:json][timeout:180];area["ISO3166-1"="IN"][admin_level=2]->.in;'
             f'nwr["amenity"~"^(hospital|clinic|doctors|pharmacy)$"]({la},{lo},{la + step},{lo + step})(area.in);out center tags;')
        for attempt in range(6):
            url = SERVERS[(n + attempt) % len(SERVERS)]
            try:
                r = requests.post(url, data={"data": q}, headers={"User-Agent": UA}, timeout=200)
                r.raise_for_status()
                got = r.json()["elements"]
                for e in got:
                    els[(e["type"], e["id"])] = e
                print(f"tile {n}/{len(tiles)} ({la},{lo}): {len(got)} via {url.split('/')[2]} — total {len(els)}", flush=True)
                break
            except Exception as e:
                print(f"tile {n} attempt {attempt + 1} failed ({url.split('/')[2]}): {str(e)[:80]}", flush=True)
                time.sleep(5)
        else:
            sys.exit(f"tile {n} failed on all servers")
        time.sleep(1)
    return list(els.values())


def main() -> None:
    out = []
    raw = fetch_tiles() if "--tiles" in sys.argv else fetch()
    for el in raw:
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = {k: v for k, v in el.get("tags", {}).items() if k in KEEP or k.startswith("name:")}
        out.append({"type": el["type"], "id": el["id"], "lat": round(lat, 6), "lon": round(lon, 6), "tags": tags})
    lats, lons = [e["lat"] for e in out], [e["lon"] for e in out]
    doc = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "OpenStreetMap via Overpass API",
        "license": "© OpenStreetMap contributors, ODbL 1.0",
        "bbox": [min(lats), min(lons), max(lats), max(lons)],
        "counts": {k: sum(e["tags"].get("amenity") == k for e in out) for k in ("hospital", "clinic", "doctors", "pharmacy")},
        "elements": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB): {doc['counts']}")


if __name__ == "__main__":
    main()
