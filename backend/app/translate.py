"""Event titles and descriptions in Polish and English, translated by Claude and stored in Postgres.

Every event gets `events.i18n`:
    {"orig": "pl", "for": "<title>\\n<lead>", "pl": {"title", "lead"}, "en": {"title", "lead"}}
`for` is the text the translation was made from, so an event whose title or description changes
upstream is translated again. Identical texts (hundreds of sport classes called "Zumba") are
translated once: every text goes through the `text_translations` cache first.

The API serves `?lang=en|pl` from this (app/routers/events.py). Runs at the end of every ingest
(app/ingest/run.py) and on its own:

    python -m app.translate [--limit 3000]

Needs ANTHROPIC_API_KEY (ANTHROPIC_API_KEY_SECRET_ARN on AWS); without it this step is skipped.
"""

import argparse
import hashlib
import json
import sys

import anthropic
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Event, TextTranslation

MODEL = "claude-opus-5-5"
BATCH = 40  # texts per request: titles are short, descriptions are capped at ~300 characters

INSTRUCTIONS = """You translate listings for syrenka.me, a map of events and places in Warsaw.

For every item in the JSON list below, detect its language and return it in both Polish ("pl") and \
English ("en"). One of the two is usually the original: return the original unchanged.

- Translate naturally and concisely, the way a local events guide would phrase it. Never add information.
- Keep proper names as they are: venues, people, bands, street names, and titles of works in quotes \
(„...”, "..."). "Koncert „God save the Queen”" becomes "Concert „God save the Queen”".
- Keep numbers, dates, times, emoji and punctuation.
- "lang" is the detected original language as an ISO 639-1 code ("pl", "en", ...).
- Return exactly one result per item, with the same "i"."""

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "lang": {"type": "string"},
                    "pl": {"type": "string"},
                    "en": {"type": "string"},
                },
                "required": ["i", "lang", "pl", "en"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def source_text(event: Event) -> str:
    """What a translation is made from; matches the SQL in pending()."""
    return f"{event.title}\n{event.lead or ''}"


def pending(db: Session, limit: int) -> list[Event]:
    """Active events never translated, or whose title/description changed since."""
    made_from = func.concat(Event.title, "\n", func.coalesce(Event.lead, ""))
    stmt = (
        select(Event)
        .where(Event.is_active, or_(Event.i18n.is_(None), Event.i18n["for"].astext != made_from))
        .order_by(Event.id)
        .limit(limit)
    )
    return list(db.scalars(stmt))


def translate_batch(client: anthropic.Anthropic, texts: list[str]) -> dict[str, dict]:
    """texts -> {text: {"lang", "pl", "en"}}. Texts Claude declines or skips are left out (retried next run)."""
    items = json.dumps([{"i": i, "text": t} for i, t in enumerate(texts)], ensure_ascii=False)
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # a declined batch is re-run on Anthropic's recommended fallback model
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": f"{INSTRUCTIONS}\n\n{items}"}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        print(f"translate: batch of {len(texts)} skipped ({response.stop_reason})", file=sys.stderr)
        return {}
    text = next(b.text for b in response.content if b.type == "text")
    out = {}
    for item in json.loads(text)["items"]:
        i = item["i"]
        if 0 <= i < len(texts) and item["pl"].strip() and item["en"].strip():
            out[texts[i]] = {
                "lang": item["lang"][:8].lower(),
                "pl": item["pl"].strip(),
                "en": item["en"].strip(),
            }
    return out


def translate_texts(db: Session, client: anthropic.Anthropic, texts: set[str]) -> dict[str, TextTranslation]:
    """Look every text up in the cache; ask Claude only for the ones it has never seen."""
    keys = {text_key(t): t for t in texts}
    cached = {
        keys[row.key]: row for row in db.scalars(select(TextTranslation).where(TextTranslation.key.in_(keys)))
    }
    missing = sorted(t for t in texts if t not in cached)
    for start in range(0, len(missing), BATCH):
        for text, tr in translate_batch(client, missing[start : start + BATCH]).items():
            row = TextTranslation(key=text_key(text), orig=tr["lang"], pl=tr["pl"], en=tr["en"])
            db.merge(row)
            cached[text] = row
        db.commit()  # keep what's done if a later batch fails
    return cached


def run(db: Session, limit: int = 3000, client: anthropic.Anthropic | None = None) -> int:
    """Translate up to `limit` pending events. Returns how many got (re)translated."""
    if client is None:
        if not settings.anthropic_api_key:
            print("translate: skipped (no ANTHROPIC_API_KEY)")
            return 0
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    events = pending(db, limit)
    texts = {e.title for e in events} | {e.lead for e in events if e.lead}
    done = translate_texts(db, client, texts)
    n = 0
    for e in events:
        title, lead = done.get(e.title), done.get(e.lead) if e.lead else None
        if title is None or (e.lead and lead is None):
            continue  # try again next run
        e.i18n = {
            "orig": title.orig,
            "for": source_text(e),
            **{
                lang: {"title": getattr(title, lang), "lead": getattr(lead, lang) if lead else None}
                for lang in ("pl", "en")
            },
        }
        n += 1
    db.commit()
    print(f"translate: {n} of {len(events)} events, {len(texts)} distinct texts")
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3000, help="max events per run")
    args = ap.parse_args(argv)
    with SessionLocal() as db:
        run(db, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
