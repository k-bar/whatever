import json

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import busyareas
from app.db import get_db
from app.models import AirStation, TouristRoute, WeatherStation

router = APIRouter(tags=["map"])


@router.get("/busyareas")
def busy_areas():
    """GeoJSON outlines of Warsaw's busiest social areas (see app/busyareas)."""
    return busyareas.load()


def point(id_: str, lng: float, lat: float, props: dict) -> dict:
    return {
        "type": "Feature",
        "id": id_,
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "properties": props,
    }


@router.get("/conditions")
def conditions(db: Session = Depends(get_db)):
    """Latest weather and air quality per station (refreshed every 10 minutes): two FeatureCollections."""
    weather = [
        point(
            s.name,
            s.lng,
            s.lat,
            {
                "name": s.name,
                "measured_at": s.measured_at.isoformat() if s.measured_at else None,
                "temp_air": s.temp_air,
                "temp_road": s.temp_road,
                "humidity": s.humidity,
                "wind_speed": s.wind_speed,
                "wind_dir": s.wind_dir,
                "precipitation": s.precipitation,
            },
        )
        for s in db.scalars(select(WeatherStation).order_by(WeatherStation.name))
    ]
    air = [
        point(
            s.name,
            s.lng,
            s.lat,
            {
                "name": s.name,
                "station": s.station,
                "district": s.district,
                "street": s.street,
                "index": s.index_name,
                "recommendation": s.recommendation,
                "params": s.params,
                "measured_at": s.measured_at.isoformat() if s.measured_at else None,
            },
        )
        for s in db.scalars(select(AirStation).order_by(AirStation.name))
    ]
    return {
        "weather": {"type": "FeatureCollection", "features": weather},
        "air": {"type": "FeatureCollection", "features": air},
    }


@router.get("/routes")
def routes(db: Session = Depends(get_db)):
    """Tourist routes as GeoJSON LineStrings, with their points of interest."""
    rows = db.execute(select(TouristRoute, func.ST_AsGeoJSON(TouristRoute.path)).order_by(TouristRoute.title))
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": r.id,
                "geometry": json.loads(geometry),
                "properties": {
                    "title": r.title,
                    "length_km": r.length_km,
                    "description": r.description,
                    "points": r.points,
                },
            }
            for r, geometry in rows
        ],
    }
