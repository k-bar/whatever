import re
import unicodedata
from datetime import UTC, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.categories import CATEGORIES
from app.db import get_db
from app.models import Event, Occurrence
from app.routers.events import feature
from app.routers.events import is_open as event_is_open
from app.schemas import GeoJSONFeature

router = APIRouter(prefix="/search", tags=["search"])
WARSAW = ZoneInfo("Europe/Warsaw")
MAX_CANDIDATES = 600
MAX_RESULTS = 40
DISTRICTS = (
    "Bemowo",
    "Białołęka",
    "Bielany",
    "Mokotów",
    "Ochota",
    "Praga",
    "Praga-Południe",
    "Praga-Północ",
    "Rembertów",
    "Śródmieście",
    "Targówek",
    "Ursus",
    "Ursynów",
    "Wawer",
    "Wesoła",
    "Wilanów",
    "Włochy",
    "Wola",
    "Żoliborz",
)
CategorySlug = Literal[tuple(CATEGORIES)]  # type: ignore[valid-type]

RUNNING_CLUB_ALIASES = (
    "running club",
    "running clubs",
    "run club",
    "run clubs",
    "club run",
    "club runs",
    "klub biegowy",
    "kluby biegowe",
    "grupa biegowa",
    "grupy biegowe",
    "wspolne bieganie",
    "parkrun",
    "park run",
)

CATEGORY_ALIASES = {
    "music": ("music", "muzyka", "koncert", "koncerty", "concert", "concerts"),
    "nightlife": ("nightlife", "impreza", "imprezy", "klub", "kluby", "dyskoteka", "dyskoteki", "clubbing"),
    "theatre": ("theatre", "theater", "teatr", "teatrze", "spektakl", "spektakle"),
    "film": ("film", "films", "kino", "seans", "seanse", "cinema", "movie", "movies"),
    "exhibitions": (
        "exhibition",
        "exhibitions",
        "wystawa",
        "wystawy",
        "muzeum",
        "muzea",
        "galeria",
        "galerie",
    ),
    "meetups": ("meetup", "meetups", "spotkanie", "spotkania", "wymiana jezykowa", "language exchange"),
    "grzybki": ("grzybki", "grzybobranie"),
    "study_buddies": ("study buddies", "study buddy", "wspolna nauka", "nauka w grupie"),
    "running": (
        "running",
        "run",
        "runs",
        "jogging",
        "bieganie",
        "bieg",
        "biegi",
        "biegac",
        *RUNNING_CLUB_ALIASES,
        "maraton",
    ),
    "yoga": ("yoga", "joga"),
    "sports": ("sports", "sport", "sporty", "nordic walking", "fitness"),
    "festivals": ("festival", "festivals", "festiwal", "festiwale", "festyn", "festyny"),
    "markets": ("market", "markets", "targ", "targi", "jarmark", "jarmarki", "kiermasz", "bazar"),
    "culture": ("culture", "kultura", "cultural", "historia", "history"),
    "education": ("education", "edukacja", "warsztaty", "workshop", "workshops", "wyklad", "wyklady", "kurs"),
    "family": ("family", "kids", "children", "dla dzieci", "rodzinne", "dzieci"),
    "business": ("business", "biznes", "konferencja", "konferencje", "conference", "networking"),
    "health": ("health", "zdrowie", "wellness", "medytacja", "meditation"),
    "food": (
        "food",
        "food and drink",
        "restauracja",
        "restauracje",
        "restauracji",
        "restaurant",
        "restaurants",
        "kawiarnia",
        "kawiarnie",
        "cafe",
        "cafes",
        "coffee shop",
        "pizzeria",
    ),
    "other": ("other", "inne", "pozostale"),
    "toilets": ("public toilet", "public toilets", "toilet", "toilets", "toaleta", "toalety"),
    "aed": ("aed", "defibrillator", "defibrillators", "defibrylator", "defibrylatory"),
    "transit": (
        "transit",
        "metro",
        "subway",
        "metro station",
        "metro stations",
        "bus station",
        "bus stations",
        "metro & bus stations",
        "stacja metra",
        "stacje metra",
        "przystanek autobusowy",
        "przystanki autobusowe",
    ),
}

GENRE_ALIASES = {
    "death metal": ("death metal", "death-metal"),
    "black metal": ("black metal",),
    "thrash metal": ("thrash metal",),
    "heavy metal": ("heavy metal",),
    "metal": ("metal", "metalowy", "metalowa", "metalowe"),
    "rock": ("rock", "rockowy", "rockowa", "rockowe"),
    "punk": ("punk", "punkowy", "punkowa"),
    "jazz": ("jazz", "jazzowy", "jazzowa", "jazzowe"),
    "disco polo": ("disco polo",),
    "techno": ("techno",),
    "hip hop": ("hip hop", "hip-hop"),
    "classical music": ("classical music", "muzyka klasyczna"),
    "electronic music": ("electronic music", "muzyka elektroniczna"),
}

CUISINE_ALIASES = {
    "italian": ("italian", "wloska", "wloskie"),
    "mexican": ("mexican", "meksykanska", "meksykanskie"),
    "japanese": ("japanese", "japonska", "japonskie"),
    "sushi": ("sushi",),
    "thai": ("thai", "tajska", "tajskie"),
    "indian": ("indian", "indyjska", "indyjskie"),
    "polish": ("polish", "polska", "polskie"),
    "vegan": ("vegan", "weganskie", "weganska"),
    "vegetarian": ("vegetarian", "wegetarianskie", "wegetarianska"),
    "pizza": ("pizza", "pizzeria"),
}

PLACE_ALIASES = (
    "restaurant",
    "restaurants",
    "restauracja",
    "restauracje",
    "restauracji",
    "cafe",
    "cafes",
    "coffee shop",
    "kawiarnia",
    "kawiarnie",
    "bar",
    "bars",
    "pub",
    "pubs",
    "club",
    "clubs",
    "nightclub",
    "nightclubs",
    "night club",
    "night clubs",
    "venue",
    "venues",
    "miejsce",
    "miejsca",
)
EVENT_ALIASES = (
    "event",
    "events",
    "wydarzenie",
    "wydarzenia",
    "activity",
    "activities",
    "zajecia",
    "class",
    "classes",
    "concert",
    "concerts",
    "gig",
    "gigs",
    "show",
    "shows",
)
NEARBY_ALIASES = (
    "near me",
    "nearby",
    "close to me",
    "around me",
    "w poblizu",
    "blisko mnie",
    "niedaleko mnie",
    "w okolicy",
)
OPEN_NOW_ALIASES = ("open now", "currently open", "otwarte teraz", "czynne teraz")
DATE_ALIASES = (
    (("tonight", "dzis wieczorem", "dzisiaj wieczorem"), "tonight"),
    (("today", "dzis", "dzisiaj"), "today"),
    (("tomorrow", "jutro"), "tomorrow"),
    (("this weekend", "w ten weekend", "w tym weekend", "weekend"), "weekend"),
    (("this week", "w tym tygodniu", "w tym tygodniu"), "week"),
    (("this month", "w tym miesiacu"), "month"),
)
WEEKDAY_ALIASES = {
    0: ("monday", "poniedzialek", "poniedzialku"),
    1: ("tuesday", "wtorek", "wtorku"),
    2: ("wednesday", "sroda", "srode", "srodzie"),
    3: ("thursday", "czwartek", "czwartku"),
    4: ("friday", "piatek", "piatku"),
    5: ("saturday", "sobota", "sobote", "soboty"),
    6: ("sunday", "niedziela", "niedziele", "niedzieli"),
}
DISTRICT_ALIASES = {
    "Bemowo": ("bemowo", "bemowie"),
    "Białołęka": ("bialoleka", "bialolece"),
    "Bielany": ("bielany", "bielanach"),
    "Mokotów": ("mokotow", "mokotowie"),
    "Ochota": ("ochota", "ochocie"),
    "Praga": ("praga", "pradze"),
    "Praga-Południe": ("praga poludnie", "praga-poludnie"),
    "Praga-Północ": ("praga polnoc", "praga-polnoc"),
    "Rembertów": ("rembertow", "rembertowie"),
    "Śródmieście": ("srodmiescie", "srodmiesciu", "centrum"),
    "Targówek": ("targowek", "targowku"),
    "Ursus": ("ursus",),
    "Ursynów": ("ursynow", "ursynowie"),
    "Wawer": ("wawer", "wawrze"),
    "Wesoła": ("wesola", "wesolej"),
    "Wilanów": ("wilanow", "wilanowie"),
    "Włochy": ("wlochy", "wlochach"),
    "Wola": ("wola", "woli"),
    "Żoliborz": ("zoliborz", "zoliborzu"),
}
SOFT_PREFERENCES = {
    "free": ("free", "darmowy", "darmowa", "darmowe", "bezplatny", "bezplatna", "bezplatne"),
    "cheap": ("cheap", "inexpensive", "tani", "tania", "tanie"),
    "family-friendly": ("family friendly", "dla rodzin", "przyjazne rodzinom"),
}
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "by",
    "for",
    "find",
    "in",
    "is",
    "it",
    "looking",
    "me",
    "next",
    "of",
    "on",
    "or",
    "please",
    "show",
    "some",
    "the",
    "to",
    "with",
    "w",
    "we",
    "na",
    "do",
    "od",
    "i",
    "z",
    "ze",
    "dla",
    "mi",
    "szukam",
    "znajdz",
    "pokaz",
    "prosze",
    "chce",
    "chcialbym",
    "chcialabym",
    "jakies",
    "this",
}


class AssistantSearchRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    lang: Literal["pl", "en"] = "en"
    latitude: float | None = Field(None, ge=52.0, le=52.5)
    longitude: float | None = Field(None, ge=20.7, le=21.4)
    preferences: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("preferences")
    @classmethod
    def validate_preferences(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(value) > 80:
                raise ValueError("Each preference must be at most 80 characters")
        return [value.strip() for value in values if value.strip()]


class SearchIntent(BaseModel):
    intent: Literal["events", "places", "any"] = "any"
    terms: list[str] = Field(default_factory=list, max_length=8)
    categories: list[CategorySlug] = Field(default_factory=list, max_length=4)
    district: str | None = Field(None, max_length=40, json_schema_extra={"enum": [*DISTRICTS, None]})
    date_window: Literal["any", "today", "tonight", "tomorrow", "weekend", "week", "month"] = "any"
    weekday: int | None = Field(None, ge=0, le=6)
    nearby: bool = False
    radius_km: float = Field(5, ge=0.5, le=30)
    open_now: bool = False
    alternative_terms: list[str] = Field(default_factory=list, max_length=6)
    preferences: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("terms", "alternative_terms", "preferences")
    @classmethod
    def clean_terms(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            term = " ".join(value.split()).strip()
            if term and len(term) <= 80 and term not in cleaned:
                cleaned.append(term)
        return cleaned

    @field_validator("district")
    @classmethod
    def known_district_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        match = next((district for district in DISTRICTS if district.casefold() == value.casefold()), None)
        if match is None:
            raise ValueError("District must be one of Warsaw's districts")
        return match


class SuggestionGroup(BaseModel):
    label: str
    results: list[GeoJSONFeature]


class AssistantSearchResponse(BaseModel):
    answer: str
    intent: SearchIntent
    results: list[GeoJSONFeature]
    suggestions: list[SuggestionGroup] = Field(default_factory=list)


def normalize(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", (value or "").casefold())
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", unaccented).strip()


def has_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(normalize(phrase))}(?!\w)", text) is not None


def remove_phrases(text: str, phrases: tuple[str, ...] | list[str]) -> str:
    for phrase in sorted(phrases, key=len, reverse=True):
        text = re.sub(
            rf"(?<!\w){re.escape(normalize(phrase))}(?!\w)",
            " ",
            text,
        )
    return re.sub(r"\s+", " ", text).strip()


def interpret_prompt(prompt: str) -> SearchIntent:
    remaining = normalize(prompt)
    running_club_alias = next(
        (alias for alias in RUNNING_CLUB_ALIASES if has_phrase(remaining, alias)),
        None,
    )
    running_club_request = running_club_alias is not None
    place_request = not running_club_request and any(
        has_phrase(remaining, phrase) for phrase in PLACE_ALIASES
    )
    event_request = running_club_request or any(
        has_phrase(remaining, phrase) for phrase in EVENT_ALIASES
    )
    categories: list[str] = []
    terms: list[str] = []

    if running_club_alias:
        categories.append("running")
        remaining = remove_phrases(remaining, [running_club_alias])

    for genre, aliases in sorted(
        GENRE_ALIASES.items(), key=lambda item: max(map(len, item[1])), reverse=True
    ):
        if any(has_phrase(remaining, alias) for alias in aliases):
            categories.append("music")
            terms.append(genre)
            remaining = remove_phrases(remaining, list(aliases))

    for cuisine, aliases in sorted(
        CUISINE_ALIASES.items(), key=lambda item: max(map(len, item[1])), reverse=True
    ):
        if any(has_phrase(remaining, alias) for alias in aliases):
            categories.append("food")
            terms.append(cuisine)
            remaining = remove_phrases(remaining, list(aliases))

    for category, aliases in CATEGORY_ALIASES.items():
        label = CATEGORIES[category]
        candidates = (*aliases, label)
        if any(has_phrase(remaining, alias) for alias in candidates):
            categories.append(category)
            remaining = remove_phrases(remaining, list(candidates))

    district = None
    for name, aliases in sorted(
        DISTRICT_ALIASES.items(), key=lambda item: max(map(len, item[1])), reverse=True
    ):
        if any(has_phrase(remaining, alias) for alias in aliases):
            district = name
            remaining = remove_phrases(remaining, list(aliases))
            break

    date_window = "any"
    for aliases, window in DATE_ALIASES:
        if any(has_phrase(remaining, alias) for alias in aliases):
            date_window = window
            remaining = remove_phrases(remaining, list(aliases))
            break

    weekday = None
    for day, aliases in WEEKDAY_ALIASES.items():
        if any(has_phrase(remaining, alias) for alias in aliases):
            weekday = day
            remaining = remove_phrases(remaining, list(aliases))
            break

    nearby = any(has_phrase(remaining, phrase) for phrase in NEARBY_ALIASES)
    remaining = remove_phrases(remaining, list(NEARBY_ALIASES))
    open_now = any(has_phrase(remaining, phrase) for phrase in OPEN_NOW_ALIASES)
    remaining = remove_phrases(remaining, list(OPEN_NOW_ALIASES))

    place_request = place_request or open_now
    remaining = remove_phrases(remaining, [*PLACE_ALIASES, *EVENT_ALIASES])

    preferences: list[str] = []
    for preference, aliases in SOFT_PREFERENCES.items():
        if any(has_phrase(remaining, alias) for alias in aliases):
            preferences.append(preference)
            remaining = remove_phrases(remaining, list(aliases))

    terms.extend(word for word in re.findall(r"[\w'-]+", remaining) if word not in STOP_WORDS)
    terms = list(dict.fromkeys(terms))[:8]
    categories = list(dict.fromkeys(categories))[:4]
    if place_request and event_request:
        intent = "any"
    elif place_request:
        intent = "places"
    elif any(category in categories for category in ("food", "toilets", "aed", "transit")):
        intent = "places"
    elif event_request or categories:
        intent = "events"
    else:
        intent = "any"

    return SearchIntent(
        intent=intent,
        terms=terms,
        categories=categories,
        district=district,
        date_window=date_window,
        weekday=weekday,
        nearby=nearby,
        open_now=open_now,
        preferences=preferences,
    )


def window_bounds(window: str, now: datetime, weekday: int | None = None) -> tuple[datetime, datetime] | None:
    local = now.astimezone(WARSAW)
    today = local.date()
    start_of_day = datetime.combine(today, time.min, WARSAW)
    next_day = start_of_day + timedelta(days=1)
    if weekday is not None:
        day_start = start_of_day + timedelta(days=(weekday - today.weekday()) % 7)
        return max(day_start, now), day_start + timedelta(days=1)
    if window == "today":
        return max(start_of_day, now), next_day
    if window == "tonight":
        start = datetime.combine(today, time(17), WARSAW)
        return max(start, now), next_day
    if window == "tomorrow":
        return next_day, next_day + timedelta(days=1)
    if window == "weekend":
        days_to_saturday = (5 - today.weekday()) % 7
        saturday = start_of_day + timedelta(days=days_to_saturday)
        if local.weekday() == 6:
            saturday = start_of_day - timedelta(days=1)
        return max(saturday, now), saturday + timedelta(days=2)
    if window == "week":
        monday = start_of_day - timedelta(days=today.weekday())
        return max(monday, now), monday + timedelta(days=7)
    if window == "month":
        return now, now + timedelta(days=30)
    return None


def haversine_km(origin: tuple[float, float], target: tuple[float, float]) -> float:
    from math import asin, cos, radians, sin, sqrt

    lon1, lat1 = map(radians, origin)
    lon2, lat2 = map(radians, target)
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def matches_terms(event: Event, terms: list[str]) -> bool:
    if not terms:
        return True
    searchable = normalize(
        " ".join(
            filter(
                None,
                [
                    event.title,
                    event.lead,
                    event.text_plain,
                    event.venue_name,
                    event.address,
                    event.district,
                    *event.categories,
                ],
            )
        )
    )
    return all(normalize(term) in searchable for term in terms)


def within_radius(event: Event, intent: SearchIntent, request: AssistantSearchRequest) -> bool:
    if not intent.nearby:
        return True
    if request.latitude is None or request.longitude is None:
        return False
    if event.lat is None or event.lng is None:
        return False
    return haversine_km((request.longitude, request.latitude), (event.lng, event.lat)) <= intent.radius_km


def event_occurrences(db: Session, intent: SearchIntent, from_: datetime, to: datetime):
    kinds = (
        ["event", "class"] if intent.intent == "events" else ["place"] if intent.intent == "places" else None
    )
    stmt = (
        select(Event, Occurrence)
        .join(Occurrence, Occurrence.event_id == Event.id, isouter=True)
        .where(Event.is_active)
        .options(selectinload(Event.source))
        .order_by(Occurrence.starts_at.nullslast(), Event.id)
        .limit(MAX_CANDIDATES)
    )
    if kinds:
        stmt = stmt.where(Event.kind.in_(kinds))
    if intent.intent == "places":
        stmt = stmt.where(Event.kind == "place")
    else:
        stmt = stmt.where(
            or_(
                Event.kind == "place",
                Occurrence.starts_at.is_not(None)
                & (Occurrence.starts_at <= to)
                & (Occurrence.ends_at.is_(None) | (Occurrence.ends_at >= from_)),
            )
        )
    query_terms = list(dict.fromkeys([*intent.terms, *intent.alternative_terms]))
    if query_terms:
        text_conditions = []
        for term in query_terms:
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{escaped}%"
            text_conditions.append(
                or_(
                    Event.title.ilike(like, escape="\\"),
                    Event.venue_name.ilike(like, escape="\\"),
                    Event.lead.ilike(like, escape="\\"),
                    Event.text_plain.ilike(like, escape="\\"),
                    Event.address.ilike(like, escape="\\"),
                    Event.district.ilike(like, escape="\\"),
                )
            )
        category_condition = Event.categories.overlap(intent.categories) if intent.categories else None
        stmt = stmt.where(
            or_(*text_conditions, *([category_condition] if category_condition is not None else []))
        )
    elif intent.categories:
        stmt = stmt.where(Event.categories.overlap(intent.categories))
    return db.execute(stmt).all()


def to_feature(event: Event, occurrence: Occurrence | None, lang: str | None = None) -> GeoJSONFeature:
    return feature(event, occurrence, lang=lang)


def rank_pairs(pairs, terms: list[str], request: AssistantSearchRequest, preferences=()):
    ranking_terms = [*terms, *request.preferences, *preferences]

    def score(pair):
        event, occurrence = pair
        content = normalize(
            " ".join(filter(None, [event.title, event.lead, event.text_plain, event.venue_name]))
        )
        term_score = sum(
            (4 if normalize(term) in normalize(event.title) else 1)
            * (2 if term in [*request.preferences, *preferences] else 1)
            for term in ranking_terms
            if normalize(term) in content
        )
        distance = (
            haversine_km((request.longitude, request.latitude), (event.lng, event.lat))
            if request.latitude is not None
            and request.longitude is not None
            and event.lat is not None
            and event.lng is not None
            else float("inf")
        )
        starts = occurrence.starts_at.timestamp() if occurrence else float("inf")
        return (-term_score, distance, starts, event.id)

    return sorted(pairs, key=score)


def within_window(occurrence: Occurrence | None, bounds: tuple[datetime, datetime] | None) -> bool:
    if occurrence is None:
        return True
    if bounds is None:
        return (occurrence.ends_at or occurrence.starts_at) >= datetime.now(UTC)
    start, end = bounds
    event_end = occurrence.ends_at or occurrence.starts_at
    return occurrence.starts_at < end and event_end >= start


def filter_candidates(pairs, intent, request, bounds, terms, relax_area=False):
    selected = []
    for event, occurrence in pairs:
        if intent.categories and not set(intent.categories).intersection(event.categories or []):
            continue
        if not matches_terms(event, terms):
            continue
        if intent.district and not relax_area:
            event_district = normalize(event.district)
            requested_district = normalize(intent.district)
            if event_district != requested_district and not (
                requested_district == "praga" and event_district.startswith("praga-")
            ):
                continue
        if not relax_area and not within_radius(event, intent, request):
            continue
        if not within_window(occurrence, bounds):
            continue
        if intent.open_now and event.kind == "place":
            local_now = datetime.now(WARSAW)
            hours = (event.opening_hours or {}).get(local_now.strftime("%A").lower())
            if not event_is_open(hours, local_now):
                continue
        selected.append((event, occurrence))
    return rank_pairs(selected, terms, request, intent.preferences)


def make_suggestions(pairs, intent, request, bounds, include_relaxed=True, exclude_ids=None):
    groups = []
    seen: set[int] = set(exclude_ids or ())
    standard_terms = intent.terms
    if include_relaxed and (intent.district or intent.nearby):
        for pair in filter_candidates(pairs, intent, request, bounds, standard_terms, relax_area=True):
            event, occurrence = pair
            if event.id not in seen:
                seen.add(event.id)
                groups.append(to_feature(event, occurrence, request.lang))
            if len(groups) == 4:
                break
        if groups:
            label = (
                "Więcej podobnych wyników w innych dzielnicach Warszawy"
                if request.lang == "pl"
                else "More matches elsewhere in Warsaw"
            )
            yield SuggestionGroup(label=label, results=groups)

    if include_relaxed and (intent.date_window != "any" or intent.weekday is not None):
        later_bounds = (datetime.now(UTC), datetime.now(UTC) + timedelta(days=30))
        later = []
        for event, occurrence in filter_candidates(pairs, intent, request, later_bounds, standard_terms):
            if event.id not in seen:
                seen.add(event.id)
                later.append(to_feature(event, occurrence, request.lang))
            if len(later) == 4:
                break
        if later:
            label = (
                "Podobne wydarzenia w ciągu najbliższych 30 dni"
                if request.lang == "pl"
                else "Similar matches in the next 30 days"
            )
            yield SuggestionGroup(label=label, results=later)

    if intent.categories and (intent.terms or intent.alternative_terms):
        broad_matches = []
        for event, occurrence in filter_candidates(pairs, intent, request, bounds, []):
            if event.id not in seen and set(event.categories or []).intersection(intent.categories):
                seen.add(event.id)
                broad_matches.append(to_feature(event, occurrence, request.lang))
            if len(broad_matches) == 4:
                break
        if broad_matches:
            category_names = ", ".join(CATEGORIES[category] for category in intent.categories)
            label = (
                f"Więcej wydarzeń z kategorii: {category_names}; dokładny gatunek nie jest potwierdzony"
                if request.lang == "pl"
                else f"More {category_names} events; the exact match is not confirmed"
            )
            yield SuggestionGroup(
                label=label,
                results=broad_matches,
            )

    alternatives = []
    alternatives_elsewhere = False
    if intent.alternative_terms:
        matches = filter_candidates(pairs, intent, request, bounds, intent.alternative_terms)
        if not matches and include_relaxed and (intent.district or intent.nearby):
            matches = filter_candidates(
                pairs, intent, request, bounds, intent.alternative_terms, relax_area=True
            )
            alternatives_elsewhere = bool(matches)
        for event, occurrence in matches:
            if event.id not in seen:
                seen.add(event.id)
                alternatives.append(to_feature(event, occurrence, request.lang))
            if len(alternatives) == 4:
                break
        if alternatives:
            label = (
                "Podobne propozycje według słownika kategorii (to nie są dokładne dopasowania)"
                if request.lang == "pl"
                else "Related options from category synonyms (not exact matches)"
            )
            if alternatives_elsewhere:
                label = (
                    "Podobne propozycje poza wybraną dzielnicą lub zasięgiem; to nie są dokładne dopasowania"
                    if request.lang == "pl"
                    else "Related options outside the requested area (not exact matches)"
                )
            yield SuggestionGroup(
                label=label,
                results=alternatives,
            )


def build_answer(intent: SearchIntent, results: list[dict], suggestions: list[SuggestionGroup], request):
    if intent.nearby and (request.latitude is None or request.longitude is None):
        if request.lang == "pl":
            return (
                "Nie mam Twojej lokalizacji, więc nie potwierdzę, co jest blisko. "
                "Podaj dzielnicę lub udostępnij lokalizację."
            )
        return "I do not have your location, so I cannot confirm what is nearby. Add a district or share your location."
    if results:
        if request.lang == "pl":
            return f"Znalazłem {len(results)} pasujących wyników w dostępnych danych."
        return f"Found {len(results)} matches. Results are selected from the event database using the interpreted filters."
    if suggestions:
        if request.lang == "pl":
            return "Nie znalazłem dokładnego dopasowania. Poniżej są oddzielnie opisane alternatywy i zmienione kryteria."
        return "No exact matches. I found the separately labeled alternatives below; their headings explain what changed."
    if request.lang == "pl":
        return "Nie znalazłem pasujących wydarzeń ani miejsc w dostępnych danych. Wyszukiwarka nie pokaże ofert, których nie ma w bazie."
    return "No matching events or places were found in the available data. Search cannot show listings that are not in the database."


@router.post("/assistant", response_model=AssistantSearchResponse)
def assistant_search(body: AssistantSearchRequest, db: Session = Depends(get_db)):
    prompt = body.prompt
    if body.preferences:
        prompt += "\nUser's explicit preferences: " + ", ".join(body.preferences)
    intent = interpret_prompt(prompt)
    if body.preferences:
        intent.preferences = list(dict.fromkeys([*intent.preferences, *body.preferences]))[:8]
    now = datetime.now(UTC)
    bounds = window_bounds(intent.date_window, now, intent.weekday)
    search_start = bounds[0] if bounds else now
    search_end = now + timedelta(days=30)
    if bounds:
        search_end = max(bounds[1], search_end)
    pairs = event_occurrences(db, intent, search_start, search_end)
    exact = filter_candidates(pairs, intent, body, bounds, intent.terms)
    result_features = [to_feature(event, occurrence, body.lang) for event, occurrence in exact[:MAX_RESULTS]]
    suggestions = list(
        make_suggestions(
            pairs,
            intent,
            body,
            bounds,
            include_relaxed=not exact,
            exclude_ids={event.id for event, _ in exact},
        )
    )
    return AssistantSearchResponse(
        answer=build_answer(intent, result_features, suggestions, body),
        intent=intent,
        results=result_features,
        suggestions=suggestions[:3],
    )
