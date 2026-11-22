"""Hospital finder: /api/hospitals, /api/geocode"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.deps import get_current_user
from app.models import User
from app.services import places

router = APIRouter(prefix="/api", tags=["hospitals"])


@router.get("/hospitals")
async def hospitals(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    radius_km: float = Query(5, ge=0.5, le=25),
    kinds: list[Literal["hospital", "clinic", "pharmacy"]] = Query(default=["hospital", "clinic"]),
    _: User = Depends(get_current_user),
):
    try:
        results = await run_in_threadpool(places.nearby, lat, lon, radius_km, list(kinds))
    except places.PlacesUnavailable:
        raise HTTPException(503, detail={"code": "places_unavailable"})
    return {
        "results": results,
        "count": len(results),
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "note": "Facility data comes from OpenStreetMap and may be incomplete or out of date. Call ahead to confirm services and hours.",
    }


@router.get("/geocode")
async def geocode(q: str = Query(min_length=2, max_length=200), lang: str = "en", _: User = Depends(get_current_user)):
    try:
        return {"results": await run_in_threadpool(places.geocode, q, lang)}
    except places.PlacesUnavailable:
        raise HTTPException(503, detail={"code": "places_unavailable"})
