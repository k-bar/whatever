from fastapi import APIRouter

from app import busyareas

router = APIRouter(tags=["map"])


@router.get("/busyareas")
def busy_areas():
    """GeoJSON outlines of Warsaw's busiest social areas (see app/busyareas)."""
    return busyareas.load()
