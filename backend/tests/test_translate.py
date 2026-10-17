from app import translate
from app.models import Event, Source


class FakeTranslator:
    """Stands in for translate.Translator: "translates" by prefixing EN:, and counts the texts it was sent."""

    def __init__(self):
        self.sent: list[str] = []

    def translate(self, texts: list[str]) -> list[str]:
        self.sent += texts
        return [f"EN:{t}" for t in texts]


def place(db, title: str, lead: str | None = None) -> Event:
    source = db.query(Source).filter_by(slug="test").one_or_none() or Source(slug="test", name="Test")
    event = Event(source=source, external_key=title + (lead or ""), kind="place", title=title, lead=lead)
    db.add(event)
    db.commit()
    return event


def test_events_get_both_languages_and_repeated_texts_are_sent_once(db):
    fake = FakeTranslator()
    a = place(db, "Zumba", "Zajęcia dla dorosłych")
    b = place(db, "Zumba")
    assert translate.run(db, translator=fake) == 2
    assert sorted(fake.sent) == ["Zajęcia dla dorosłych", "Zumba"]  # "Zumba" asked for once
    db.refresh(a)
    db.refresh(b)
    assert a.i18n["orig"] == "pl"
    assert a.i18n["en"] == {"title": "EN:Zumba", "lead": "EN:Zajęcia dla dorosłych"}
    assert b.i18n["pl"] == {"title": "Zumba", "lead": None}
    assert translate.run(db, translator=fake) == 0  # nothing pending any more


def test_changed_title_is_translated_again(db):
    fake = FakeTranslator()
    e = place(db, "Joga w parku")
    translate.run(db, translator=fake)
    e.title = "Joga nad Wisłą"
    db.commit()
    assert translate.run(db, translator=fake) == 1
    db.refresh(e)
    assert e.i18n["en"]["title"] == "EN:Joga nad Wisłą"


def test_api_serves_the_requested_language_with_the_original(db, client):
    place(db, "Toaleta publiczna", "Czynna całą dobę")
    translate.run(db, translator=FakeTranslator())
    en = client.get("/places?lang=en").json()["features"][0]["properties"]
    assert en["title"] == "EN:Toaleta publiczna"
    assert en["lead"] == "EN:Czynna całą dobę"
    assert en["translated"] is True
    assert en["original"] == {"lang": "pl", "title": "Toaleta publiczna", "lead": "Czynna całą dobę"}
    pl = client.get("/places?lang=pl").json()["features"][0]["properties"]
    assert pl["title"] == "Toaleta publiczna" and pl["translated"] is False
    plain = client.get("/places").json()["features"][0]["properties"]
    assert plain["title"] == "Toaleta publiczna" and "translated" not in plain


def test_skipped_without_the_model(db, monkeypatch, tmp_path):
    monkeypatch.setattr(translate.settings, "translation_model_dir", str(tmp_path))
    place(db, "Kino plenerowe")
    assert translate.run(db) == 0


def test_english_originals_are_kept_not_translated():
    fake = FakeTranslator()
    out = translate.translate_batch(fake, ["Sunset yoga on the Vistula with friends", "Zajęcia jogi"])
    assert out["Sunset yoga on the Vistula with friends"] == {
        "lang": "en",
        "pl": "Sunset yoga on the Vistula with friends",
        "en": "Sunset yoga on the Vistula with friends",
    }
    assert out["Zajęcia jogi"]["en"] == "EN:Zajęcia jogi" and fake.sent == ["Zajęcia jogi"]
