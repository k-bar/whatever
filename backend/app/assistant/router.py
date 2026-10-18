import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.assistant import answers, nlu
from app.db import get_db
from app.routers.events import WARSAW

router = APIRouter(tags=["assistant"])

# Short questions in either language: count words that only one of the two languages uses. Place names
# ("Śródmieście") carry Polish letters in English questions too, so letters alone don't decide.
EN_WORDS = set(
    "what whats what's where when which who is are the a an and in at on for with this next near me my "
    "tonight today tomorrow morning afternoon evening night weekend now open free cheap show find any "
    "concert concerts gig gigs event events things thing do go going can i want something more else "
    "museum museums gallery galleries bar bars pub pubs club clubs food restaurant restaurants cafe "
    "toilet toilets running yoga kids family party parties sport sports cinema movie movies".split()
)
PL_WORDS = set(
    "co gdzie kiedy który która jest są w we na z ze i a dla koło blisko obok mnie moje dziś dzisiaj "
    "jutro pojutrze rano wieczorem wieczór noc nocą teraz otwarte darmowe tanio pokaż znajdź jakieś coś "
    "więcej jeszcze też koncert koncerty wydarzenia wystawa wystawy muzeum muzea knajpy bary jedzenie "
    "restauracje kawiarnie toalety bieganie joga dzieci impreza imprezy kino filmy".split()
)


def question_lang(q: str, fallback: str) -> str:
    """Answer in the language the question is written in; the UI language when it can't tell."""
    words = re.findall(r"[\w']+", q.lower())
    en, pl = sum(w in EN_WORDS for w in words), sum(w in PL_WORDS for w in words)
    if en > pl:
        return "en"
    if pl > en:
        return "pl"
    return fallback


class AssistantIn(BaseModel):
    q: str = Field(..., min_length=1, max_length=300)
    lang: str = Field("pl", pattern="^(pl|en)$")  # the UI language; the question's own language wins
    lat: float | None = Field(None, ge=52.0, le=52.5)
    lng: float | None = Field(None, ge=20.7, le=21.4)
    context: dict | None = None  # the previous reply's `context`


@router.post("/assistant")
def ask(body: AssistantIn, db: Session = Depends(get_db)):
    """Answer a question in plain words (see app/assistant)."""
    now = datetime.now(WARSAW).replace(tzinfo=None)
    lang = question_lang(body.q, body.lang)
    parsed = nlu.merge(nlu.understand(body.q, now), body.context)
    here = (body.lng, body.lat) if body.lat is not None and body.lng is not None else None
    if parsed.near and here is None and parsed.intent not in ("amenity_toilets", "amenity_aed"):
        parsed.near = False  # no position: "near me" can't narrow anything
    ctx = body.context or {}
    offset = ctx.get("offset", 0) + answers.SHOWN if parsed.more and ctx.get("intent") == parsed.intent else 0
    text, results = answers.answer(db, parsed, lang, here, offset)
    area = parsed.areas[0] if len(parsed.areas) == 1 else None
    return {
        "answer": text,
        "results": results,
        "intent": parsed.intent,
        "understood": answers.describe(parsed, lang),
        "lang": lang,
        "area": {
            "type": "Feature",
            "properties": {"name": area.name, "kind": area.kind},
            "geometry": json.loads(area.geometry),
        }
        if area
        else None,  # fmt: skip
        "context": parsed.context() | {"offset": offset},
    }
