from datetime import datetime, timedelta

import pytest

from app.assistant.nlu import merge, understand
from app.models import Attendance, Event, Occurrence, Source, User
from app.timeutil import WARSAW

SUNDAY = datetime(2026, 10, 18, 15, 0)  # local Warsaw time


@pytest.mark.parametrize(
    "q, intent, categories, when, areas",
    [
        (
            "koncerty jazzowe na Saskiej Kępie w weekend",
            "find",
            ["music"],
            ("weekend", 18, 19),
            ["Saska Kępa"],
        ),
        ("nightlife in Śródmieście next Saturday", "find", ["nightlife"], ("day", 24, 25), ["Śródmieście"]),
        ("joga na Mokotowie jutro", "find", ["yoga"], ("tomorrow", 19, 20), ["Mokotów"]),
        ("what's on tonight in Praga", "find", [], ("today", 18, 19), ["Praga-Północ", "Praga-Południe"]),
        ("restauracje na Pradze Północ", "find", ["food"], None, ["Praga-Północ"]),
        ("teatr 25 października", "find", ["theatre"], ("date", 25, 26), []),
        ("kino 25.10", "find", ["film"], ("date", 25, 26), []),
        ("things to do on Wola", "find", [], None, ["Wola"]),
        ("gdzie jest najbliższa toaleta", "amenity_toilets", [], None, []),
        ("defibrylator blisko mnie", "amenity_aed", [], None, []),
        ("jaka pogoda", "weather", [], None, []),
        ("pogda", "weather", [], None, []),
        ("smog dzisiaj", "air", [], ("today", 18, 19), []),
        ("bary otwarte teraz", "open", ["nightlife"], ("now", 18, 18), []),
        ("szukam towarzystwa na koncert w piątek", "company", ["music"], ("day", 23, 24), []),
        ("cześć", "greet", [], None, []),
        ("dzięki!", "thanks", [], None, []),
        ("co umiesz?", "help", [], None, []),
        ("what can you do", "help", [], None, []),
        ("asdfgh qwerty", "find", [], None, []),
    ],
)
def test_understand(q, intent, categories, when, areas):
    p = understand(q, SUNDAY)
    assert p.intent == intent
    assert p.categories == categories
    assert [a.name for a in p.areas] == areas
    if when is None:
        assert p.when is None
    else:
        assert (p.when.key, p.when.start.day, p.when.end.day) == when


def test_understand_names_and_times():
    p = understand("czy Spatif jest otwarty", SUNDAY)
    assert (p.intent, p.name) == ("open", "spatif")
    assert understand("kiedy jest Noc Muzeów Wilanów", SUNDAY).intent in ("info", "find")
    assert understand("when is Warsaw Marathon", SUNDAY).intent == "info"
    assert understand("dziś wieczorem", SUNDAY).evening
    assert understand("joga rano", SUNDAY).morning
    assert understand("koncert near me", SUNDAY).near


def test_follow_ups_keep_the_last_question():
    first = understand("jazz na Mokotowie jutro", SUNDAY)
    ctx = first.context()
    p = merge(understand("a w sobotę?", SUNDAY), ctx)
    assert (p.intent, p.categories, [a.name for a in p.areas], p.when.key) == (
        "find",
        ["music"],
        ["Mokotów"],
        "day",
    )
    p = merge(understand("and in Wola?", SUNDAY), ctx)
    assert ([a.name for a in p.areas], p.when.key, p.categories) == (["Wola"], "tomorrow", ["music"])
    p = merge(understand("a teatr?", SUNDAY), ctx)
    assert (p.categories, [a.name for a in p.areas]) == (["theatre"], ["Mokotów"])
    assert merge(understand("więcej", SUNDAY), ctx).more
    assert merge(understand("pogoda", SUNDAY), ctx).intent == "weather"  # a new question
    assert merge(understand("dzięki", SUNDAY), ctx).intent == "thanks"


# ---------- API ----------


def at(days: int, hour: int) -> datetime:
    d = datetime.now(WARSAW) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0)


def add(db, title, categories, lat, lng, *, kind="event", start=None, venue=None, district=None, hours=None):
    source = db.query(Source).filter_by(slug="test").one_or_none() or Source(slug="test", name="Test")
    e = Event(
        source=source,
        external_key=title,
        kind=kind,
        title=title,
        categories=categories,
        categories_raw=[],
        lat=lat,
        lng=lng,
        location=f"SRID=4326;POINT({lng} {lat})",
        venue_name=venue,
        district=district,
        opening_hours=hours,
        contact={},
        audience=[],
        occurrences=[Occurrence(starts_at=start)] if start else [],
    )
    db.add(e)
    db.commit()
    return e


ALL_DAY = dict.fromkeys(
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"], "00:00-24:00"
)


@pytest.fixture
def city(db):
    praga = (52.2510, 21.0350)  # Praga-Północ, near Ząbkowska
    mokotow = (52.1930, 21.0200)
    add(db, "Jazz w Hydrozagadce", ["music"], *praga, start=at(1, 20), venue="Hydrozagadka")
    add(db, "Koncert organowy", ["music"], *mokotow, start=at(1, 18), venue="Kościół św. Michała")
    add(db, "Spektakl Hamlet", ["theatre"], *mokotow, start=at(2, 19), venue="Teatr Rampa")
    add(db, "Poranna joga w parku", ["yoga"], *mokotow, start=at(1, 8), venue="Park Morskie Oko")
    add(db, "Spatif", ["nightlife"], 52.2275, 21.0170, kind="place", venue="Spatif", hours=ALL_DAY)
    add(db, "Toaleta Plac Zbawiciela", ["toilets"], 52.2196, 21.0175, kind="place", hours=ALL_DAY)
    add(db, "Toaleta Praga", ["toilets"], *praga, kind="place")
    return {"praga": praga}


def ask(client, q, lang="pl", **kw):
    r = client.post("/assistant", json={"q": q, "lang": lang} | kw)
    assert r.status_code == 200, r.text
    return r.json()


def titles(r):
    return [f["properties"]["title"] for f in r["results"]]


def test_find_by_category_area_and_day(client, city):
    r = ask(client, "koncerty jutro")
    assert set(titles(r)) == {"Jazz w Hydrozagadce", "Koncert organowy"}
    assert "2 wyniki" in r["answer"] and "muzyka" in r["understood"]
    r = ask(client, "koncerty na Pradze jutro wieczorem")
    assert titles(r) == ["Jazz w Hydrozagadce"]
    r = ask(client, "jazz", lang="en")
    assert titles(r)[0] == "Jazz w Hydrozagadce" and r["answer"].startswith("Found")
    assert ask(client, "joga rano")["results"][0]["properties"]["title"] == "Poranna joga w parku"
    assert ask(client, "hamlet")["results"][0]["properties"]["title"] == "Spektakl Hamlet"


def test_follow_up_through_context(client, city):
    first = ask(client, "koncerty jutro na Mokotowie")
    assert titles(first) == ["Koncert organowy"]
    r = ask(client, "a na Pradze?", context=first["context"])
    assert titles(r) == ["Jazz w Hydrozagadce"]
    r = ask(client, "a teatr?", context=first["context"])
    assert r["results"] == []  # Hamlet is the day after tomorrow
    r = ask(client, "a w weekend?", context=ask(client, "teatr na Mokotowie")["context"])
    assert r["intent"] == "find"


def test_venues_open_and_info(client, city):
    r = ask(client, "czy Spatif jest otwarty")
    assert r["intent"] == "open" and "otwarte" in r["answer"]
    r = ask(client, "bary otwarte teraz", lang="en")
    assert titles(r) == ["Spatif"]
    r = ask(client, "when is Hamlet", lang="en")
    assert r["intent"] == "info" and "Teatr Rampa" in r["answer"]


def test_amenities_weather_and_small_talk(client, city):
    lat, lng = city["praga"]
    r = ask(client, "gdzie najbliższa toaleta", lat=lat, lng=lng)
    assert titles(r)[0] == "Toaleta Praga" and r["results"][0]["properties"]["distance_m"] < 50
    r = ask(client, "nearest toilet", lang="en")
    assert "from the centre" in r["answer"] and titles(r)[0] == "Toaleta Plac Zbawiciela"
    assert "pogody" in ask(client, "jaka pogoda")["answer"]  # no readings in the test database
    assert ask(client, "hej")["intent"] == "greet"
    assert "112" not in ask(client, "co umiesz")["answer"]
    assert ask(client, "xyzzy plugh")["results"] == []


def test_company(client, city, db):
    user = User(email="a@example.com", password_hash="x", display_name="A", username="a")
    db.add(user)
    db.commit()
    occ = db.query(Occurrence).join(Event).filter(Event.title == "Spektakl Hamlet").one()
    db.add(Attendance(user_id=user.id, occurrence_id=occ.id, wants_company=True))
    db.commit()
    r = ask(client, "szukam towarzystwa")
    assert titles(r) == ["Spektakl Hamlet"] and "towarzystwa" in r["answer"]
    assert ask(client, "szukam towarzystwa na koncert")["results"] == []


def test_close_matches_and_ongoing_exhibitions(client, city, db):
    e = add(db, "Wystawa Dwurnik", ["exhibitions"], 52.2410, 21.0150, start=at(-60, 10))
    e.occurrences[0].ends_at = at(30, 18)
    db.commit()
    r = ask(client, "jazz jutro")
    assert titles(r) == ["Jazz w Hydrozagadce"]  # the word narrows music down
    r = ask(client, "rock jutro")
    assert r["answer"].startswith("Nic dokładnie") and len(r["results"]) == 2  # no rock: music is close
    r = ask(client, "wystawy jutro")
    assert titles(r) == ["Wystawa Dwurnik"] and "· do " in r["answer"]  # on since two months: shows its end


def test_more_pages_through_the_list(client, db):
    for i in range(7):
        add(db, f"Koncert {i}", ["music"], 52.23, 21.01, start=at(1, 10 + i))
    first = ask(client, "koncerty jutro")
    assert "Koncert 0" in first["answer"] and "„więcej”" in first["answer"]
    r = ask(client, "więcej", context=first["context"])
    assert "Koncert 5" in r["answer"] and "Koncert 0" not in r["answer"]
    r = ask(client, "więcej", context=r["context"])
    assert r["answer"].startswith("To już wszystko")


@pytest.mark.parametrize(
    "q, ui, lang",
    [
        ("concerts tonight", "pl", "en"),
        ("nightlife in Śródmieście next Saturday", "pl", "en"),  # Polish place name, English question
        ("where can I go running tomorrow morning", "pl", "en"),
        ("koncerty dzisiaj wieczorem", "en", "pl"),
        ("joga na Mokotowie jutro", "en", "pl"),
        ("a jutro?", "en", "pl"),
        ("and in Wola?", "pl", "en"),
        ("Hala Koszyki", "en", "en"),  # can't tell: the UI language
        ("Hala Koszyki", "pl", "pl"),
    ],
)
def test_answers_in_the_language_of_the_question(q, ui, lang):
    from app.assistant.router import question_lang

    assert question_lang(q, ui) == lang
