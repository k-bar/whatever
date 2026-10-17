"""Event titles and descriptions in Polish and English, translated offline and stored in Postgres.

Every event gets `events.i18n`:
    {"orig": "pl", "for": "<title>\\n<lead>", "pl": {"title", "lead"}, "en": {"title", "lead"}}
`for` is the text the translation was made from, so an event whose title or description changes
upstream is translated again. Identical texts (hundreds of sport classes called "Zumba") are
translated once: every text goes through the `text_translations` cache first.

The API serves `?lang=en|pl` from this (app/routers/events.py). Runs at the end of every ingest
(app/ingest/run.py) and on its own:

    python -m app.translate [--limit 3000]

Free and offline: the OPUS-MT Polish->English model from Argos Translate (CTranslate2 format), run with
ctranslate2 + sentencepiece. No API key, no rate limit, nothing leaves the box. deploy/deploy.sh downloads
the model to settings.translation_model_dir; without it this step is skipped. Sources are Polish, so only
pl->en is translated; the rare English original is kept as-is in both languages.
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Event, TextTranslation

BATCH = 32  # texts per translate_batch call: titles are short, descriptions are capped at ~300 characters

POLISH_LETTERS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
ENGLISH_WORDS = re.compile(r"\b(the|and|with|for|of|in|at|on|to|your|our|from)\b", re.I)


def detect_lang(text: str) -> str:
    """'pl' or 'en'. Polish letters decide; otherwise two or more common English words mean English."""
    if POLISH_LETTERS.search(text):
        return "pl"
    return "en" if len(ENGLISH_WORDS.findall(text)) >= 2 else "pl"


class Translator:
    """Polish -> English with the Argos/OPUS-MT model: about 370 MB of RAM, ~30 ms per text on CPU."""

    def __init__(self, model_dir: str | Path):
        import ctranslate2  # heavy native libs: only loaded when translating
        import sentencepiece

        model_dir = Path(model_dir)
        self.model = ctranslate2.Translator(str(model_dir / "model"), device="cpu", compute_type="int8")
        self.sp = sentencepiece.SentencePieceProcessor(model_file=str(model_dir / "sentencepiece.model"))

    def translate(self, texts: list[str]) -> list[str]:
        results = self.model.translate_batch(
            self.sp.encode(texts, out_type=str), beam_size=2, max_decoding_length=512
        )
        return ["".join(r.hypotheses[0]).replace("\u2581", " ").strip() for r in results]


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


def translate_batch(translator, texts: list[str]) -> dict[str, dict]:
    """texts -> {text: {"lang", "pl", "en"}}. Empty outputs are left out (retried next run)."""
    polish = [t for t in texts if detect_lang(t) == "pl"]
    out = {t: {"lang": "en", "pl": t, "en": t} for t in texts if t not in set(polish)}
    for text, english in zip(polish, translator.translate(polish) if polish else [], strict=True):
        if english.strip():
            out[text] = {"lang": "pl", "pl": text, "en": english.strip()}
    return out


def translate_texts(db: Session, translator, texts: set[str]) -> dict[str, TextTranslation]:
    """Look every text up in the cache; translate only the ones it has never seen."""
    keys = {text_key(t): t for t in texts}
    cached = {
        keys[row.key]: row for row in db.scalars(select(TextTranslation).where(TextTranslation.key.in_(keys)))
    }
    missing = sorted(t for t in texts if t not in cached)
    for start in range(0, len(missing), BATCH):
        for text, tr in translate_batch(translator, missing[start : start + BATCH]).items():
            row = TextTranslation(key=text_key(text), orig=tr["lang"], pl=tr["pl"], en=tr["en"])
            db.merge(row)
            cached[text] = row
        db.commit()  # keep what's done if a later batch fails
    return cached


def run(db: Session, limit: int = 3000, translator=None) -> int:
    """Translate up to `limit` pending events. Returns how many got (re)translated."""
    if translator is None:
        if not (Path(settings.translation_model_dir) / "model" / "model.bin").exists():
            print(f"translate: skipped (no model in {settings.translation_model_dir})")
            return 0
        translator = Translator(settings.translation_model_dir)
    events = pending(db, limit)
    texts = {e.title for e in events} | {e.lead for e in events if e.lead}
    done = translate_texts(db, translator, texts)
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
