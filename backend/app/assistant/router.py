import json
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.assistant import answers, nlu
from app.db import get_db
from app.routers.events import WARSAW

router = APIRouter(tags=["assistant"])


class AssistantIn(BaseModel):
    q: str = Field(..., min_length=1, max_length=300)
    lang: str = Field("pl", pattern="^(pl|en)$")
    lat: float | None = Field(None, ge=52.0, le=52.5)
    lng: float | None = Field(None, ge=20.7, le=21.4)
    context: dict | None = None  # the previous reply's `context`


@router.post("/assistant")
def ask(body: AssistantIn, db: Session = Depends(get_db)):
    """Answer a question in plain words (see app/assistant)."""
    now = datetime.now(WARSAW).replace(tzinfo=None)
    parsed = nlu.merge(nlu.understand(body.q, now), body.context)
    here = (body.lng, body.lat) if body.lat is not None and body.lng is not None else None
    if parsed.near and here is None and parsed.intent not in ("amenity_toilets", "amenity_aed"):
        parsed.near = False  # no position: "near me" can't narrow anything
    ctx = body.context or {}
    offset = ctx.get("offset", 0) + answers.SHOWN if parsed.more and ctx.get("intent") == parsed.intent else 0
    text, results = answers.answer(db, parsed, body.lang, here, offset)
    area = parsed.areas[0] if len(parsed.areas) == 1 else None
    return {
        "answer": text,
        "results": results,
        "intent": parsed.intent,
        "understood": answers.describe(parsed, body.lang),
        "area": {
            "type": "Feature",
            "properties": {"name": area.name, "kind": area.kind},
            "geometry": json.loads(area.geometry),
        }
        if area
        else None,  # fmt: skip
        "context": parsed.context() | {"offset": offset},
    }
