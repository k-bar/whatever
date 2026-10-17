import json
from types import SimpleNamespace

from app import translate
from app.models import Event, Source


class FakeClaude:
    """Stands in for anthropic.Anthropic: "translates" by prefixing EN:, and counts the texts it was sent."""

    def __init__(self):
        self.sent: list[str] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        items = json.loads(kw["messages"][0]["content"].split("\n\n")[-1])
        self.sent += [it["text"] for it in items]
        out = [{"i": it["i"], "lang": "pl", "pl": it["text"], "en": f"EN:{it['text']}"} for it in items]
        return SimpleNamespace(
            stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps({"items": out}))]
        )


def place(db, title: str, lead: str | None = None) -> Event:
    source = db.query(Source).filter_by(slug="test").one_or_none() or Source(slug="test", name="Test")
    event = Event(source=source, external_key=title + (lead or ""), kind="place", title=title, lead=lead)
    db.add(event)
    db.commit()
    return event


def test_events_get_both_languages_and_repeated_texts_are_sent_once(db):
    claude = FakeClaude()
    a = place(db, "Zumba", "Zajęcia dla dorosłych")
    b = place(db, "Zumba")
    assert translate.run(db, client=claude) == 2
    assert sorted(claude.sent) == ["Zajęcia dla dorosłych", "Zumba"]  # "Zumba" asked for once
    db.refresh(a)
    db.refresh(b)
    assert a.i18n["orig"] == "pl"
    assert a.i18n["en"] == {"title": "EN:Zumba", "lead": "EN:Zajęcia dla dorosłych"}
    assert b.i18n["pl"] == {"title": "Zumba", "lead": None}
    assert translate.run(db, client=claude) == 0  # nothing pending any more


def test_changed_title_is_translated_again(db):
    claude = FakeClaude()
    e = place(db, "Joga w parku")
    translate.run(db, client=claude)
    e.title = "Joga nad Wisłą"
    db.commit()
    assert translate.run(db, client=claude) == 1
    db.refresh(e)
    assert e.i18n["en"]["title"] == "EN:Joga nad Wisłą"


def test_api_serves_the_requested_language_with_the_original(db, client):
    place(db, "Toaleta publiczna", "Czynna całą dobę")
    translate.run(db, client=FakeClaude())
    en = client.get("/places?lang=en").json()["features"][0]["properties"]
    assert en["title"] == "EN:Toaleta publiczna"
    assert en["lead"] == "EN:Czynna całą dobę"
    assert en["translated"] is True
    assert en["original"] == {"lang": "pl", "title": "Toaleta publiczna", "lead": "Czynna całą dobę"}
    pl = client.get("/places?lang=pl").json()["features"][0]["properties"]
    assert pl["title"] == "Toaleta publiczna" and pl["translated"] is False
    plain = client.get("/places").json()["features"][0]["properties"]
    assert plain["title"] == "Toaleta publiczna" and "translated" not in plain


def test_skipped_without_an_api_key(db, monkeypatch):
    monkeypatch.setattr(translate.settings, "anthropic_api_key", None)
    place(db, "Kino plenerowe")
    assert translate.run(db) == 0
