from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app import assistant_search
from app.categories import CATEGORIES
from app.db import get_db
from app.main import app


def test_polish_music_prompt_extracts_genre_district_and_weekday():
    intent = assistant_search.interpret_prompt("Koncert death metal w sobotę na Pradze")

    assert intent.intent == "events"
    assert intent.terms == ["death metal"]
    assert intent.categories == ["music"]
    assert intent.district == "Praga"
    assert intent.weekday == 5


def test_running_club_prompts_are_running_events_not_venues():
    for prompt in (
        "running club",
        "run clubs in Mokotow",
        "club run",
        "klub biegowy",
        "grupy biegowe",
        "parkrun",
    ):
        intent = assistant_search.interpret_prompt(prompt)

        assert intent.intent == "events", prompt
        assert intent.categories == ["running"], prompt
        assert not intent.terms, prompt


def test_food_prompt_extracts_cuisine_nearby_and_soft_preference():
    intent = assistant_search.interpret_prompt("Darmowa wegetariańska restauracja blisko mnie")

    assert intent.intent == "places"
    assert intent.categories == ["food"]
    assert intent.terms == ["vegetarian"]
    assert intent.nearby
    assert intent.preferences == ["free"]


def test_every_search_category_is_recognized_from_its_public_label():
    for slug, label in CATEGORIES.items():
        intent = assistant_search.interpret_prompt(label)
        assert intent.categories == [slug], f"category label {label!r} was not recognized"


def test_transit_category_label_is_a_places_query():
    intent = assistant_search.interpret_prompt("Metro & bus stations")

    assert intent.intent == "places"
    assert intent.categories == ["transit"]


def test_open_now_is_a_places_query():
    intent = assistant_search.interpret_prompt("restaurants open now")

    assert intent.intent == "places"
    assert intent.categories == ["food"]
    assert intent.open_now
    assert not intent.terms


def test_search_query_compiles_category_and_text_filters_for_postgres():
    class CaptureSession:
        def execute(self, statement):
            self.sql = str(statement.compile(dialect=postgresql.dialect()))
            return SimpleNamespace(all=lambda: [])

    db = CaptureSession()
    assistant_search.event_occurrences(
        db,
        assistant_search.SearchIntent(intent="events", terms=["rock"], categories=["music"]),
        datetime.now(UTC),
        datetime.now(UTC) + timedelta(days=30),
    )

    assert "ILIKE" in db.sql
    assert " && " in db.sql
    assert "events.is_active" in db.sql


def test_to_feature_passes_requested_language_to_event_localization(monkeypatch):
    captured = {}

    def fake_feature(event, occurrence, lang=None):
        captured["lang"] = lang
        return {"id": event.id}

    monkeypatch.setattr(assistant_search, "feature", fake_feature)

    result = assistant_search.to_feature(SimpleNamespace(id=21), None, "en")

    assert result == {"id": 21}
    assert captured["lang"] == "en"


def test_weekend_window_uses_warsaw_local_dates():
    saturday = datetime(2026, 6, 6, 12, tzinfo=UTC)
    start, end = assistant_search.window_bounds("weekend", saturday)

    assert start.astimezone(assistant_search.WARSAW).date().isoformat() == "2026-06-06"
    assert end.astimezone(assistant_search.WARSAW).date().isoformat() == "2026-06-08"


def test_weekday_window_uses_next_matching_day():
    monday = datetime(2026, 6, 1, 12, tzinfo=UTC)
    start, end = assistant_search.window_bounds("any", monday, weekday=5)

    assert start.astimezone(assistant_search.WARSAW).date().isoformat() == "2026-06-06"
    assert end - start == timedelta(days=1)


def test_assistant_search_returns_exact_matches_without_inventing_results(monkeypatch):
    event = SimpleNamespace(
        id=17,
        title="Jazz night",
        lead=None,
        text_plain=None,
        venue_name="Klub",
        address=None,
        district="Mokotów",
        categories=["music"],
        kind="event",
        lat=52.2,
        lng=21.0,
        opening_hours=None,
    )
    occurrence = SimpleNamespace(
        starts_at=datetime.now(UTC) + timedelta(hours=1),
        ends_at=None,
    )
    monkeypatch.setattr(
        assistant_search, "interpret_prompt", lambda _: assistant_search.SearchIntent(terms=["jazz"])
    )
    monkeypatch.setattr(assistant_search, "event_occurrences", lambda *_: [(event, occurrence)])
    monkeypatch.setattr(
        assistant_search,
        "to_feature",
        lambda e, o, lang=None: {"id": e.id, "geometry": None, "properties": {"title": e.title}},
    )

    response = assistant_search.assistant_search(
        assistant_search.AssistantSearchRequest(prompt="jazz tonight"),
        db=object(),
    )

    assert [feature.id for feature in response.results] == [17]
    assert response.results[0].properties["title"] == "Jazz night"
    assert response.suggestions == []
    assert "Found 1 matches" in response.answer


def test_running_club_search_returns_running_category_events(monkeypatch):
    event = SimpleNamespace(
        id=18,
        title="Open 5K training",
        lead=None,
        text_plain=None,
        venue_name="Park",
        address=None,
        district="Mokotów",
        categories=["running"],
        kind="event",
        lat=52.2,
        lng=21.0,
        opening_hours=None,
    )
    occurrence = SimpleNamespace(
        starts_at=datetime.now(UTC) + timedelta(days=2),
        ends_at=None,
    )
    monkeypatch.setattr(assistant_search, "event_occurrences", lambda *_: [(event, occurrence)])
    monkeypatch.setattr(
        assistant_search,
        "to_feature",
        lambda e, o, lang=None: {"id": e.id, "geometry": None, "properties": {"title": e.title}},
    )

    response = assistant_search.assistant_search(
        assistant_search.AssistantSearchRequest(prompt="running club"),
        db=object(),
    )

    assert [feature.id for feature in response.results] == [18]
    assert response.intent.intent == "events"
    assert response.intent.categories == ["running"]


def test_assistant_search_api_returns_structured_empty_result(monkeypatch):
    monkeypatch.setattr(
        assistant_search, "interpret_prompt", lambda _: assistant_search.SearchIntent(terms=["rock"])
    )
    monkeypatch.setattr(assistant_search, "event_occurrences", lambda *_: [])

    def fake_db():
        yield object()

    app.dependency_overrides[get_db] = fake_db
    try:
        response = TestClient(app).post("/search/assistant", json={"prompt": "rock tonight"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["intent"]["terms"] == ["rock"]
    assert response.json()["results"] == []
    assert response.json()["suggestions"] == []
    assert "not in the database" in response.json()["answer"]


def test_unrelated_sports_event_is_not_returned_for_death_metal():
    event = SimpleNamespace(
        id=19,
        title="Nordic Walking",
        lead=None,
        text_plain=None,
        venue_name=None,
        address=None,
        district="Mokotów",
        categories=["sports"],
        kind="event",
        lat=52.2,
        lng=21.0,
        opening_hours=None,
    )
    occurrence = SimpleNamespace(starts_at=datetime.now(UTC), ends_at=None)
    intent = assistant_search.SearchIntent(terms=["death metal"], categories=["music"])

    assert (
        assistant_search.filter_candidates(
            [(event, occurrence)],
            intent,
            assistant_search.AssistantSearchRequest(prompt="death metal"),
            None,
            intent.terms,
        )
        == []
    )


def test_exact_genre_search_requires_category_and_term_match():
    music_event = SimpleNamespace(
        id=20,
        title="Death metal live",
        lead=None,
        text_plain=None,
        venue_name=None,
        address=None,
        district=None,
        categories=["music"],
        kind="event",
        lat=None,
        lng=None,
        opening_hours=None,
    )
    intent = assistant_search.SearchIntent(terms=["death metal"], categories=["music"])

    matches = assistant_search.filter_candidates(
        [(music_event, None)],
        intent,
        assistant_search.AssistantSearchRequest(prompt="death metal"),
        None,
        intent.terms,
    )

    assert [event.id for event, _ in matches] == [20]
