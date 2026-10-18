"""Answers: one handler per intent, reading the same tables as the map. Replies in Polish or English."""

from dataclasses import replace
from datetime import datetime, timedelta

from geoalchemy2 import Geography
from rapidfuzz import fuzz
from sqlalchemy import cast, func, literal, or_, select
from sqlalchemy.orm import Session, selectinload

from app.assistant.nlu import VENUE_CATEGORIES, Parsed, fold
from app.categories import AMENITIES, CATEGORIES
from app.models import AirStation, Attendance, Event, Occurrence, WeatherStation
from app.routers.events import attendance_counts, feature, is_open
from app.timeutil import WARSAW

CENTER = (21.0114, 52.2306)  # Rondo Dmowskiego, like the frontend's WARSAW_CENTER
NEAR_M = 2000
SHOWN = 5  # items listed in the answer text; `results` carries the rest for the map
MAX_RESULTS = 60
SUGGESTED = 4  # per suggestion group
EVENING_HOUR = 17
MORNING_END = 12

PL_LABELS = {
    "music": "muzyka", "nightlife": "życie nocne", "theatre": "teatr", "film": "film", "exhibitions": "wystawy",
    "meetups": "spotkania", "grzybki": "grzybki", "study_buddies": "wspólna nauka", "running": "bieganie",
    "yoga": "joga", "sports": "sport", "festivals": "festiwale", "markets": "targi", "culture": "kultura",
    "education": "edukacja", "family": "rodzina i dzieci", "business": "biznes", "health": "zdrowie",
    "food": "jedzenie i picie", "other": "inne", "toilets": "toalety", "aed": "defibrylatory (AED)",
}  # fmt: skip
WEEKDAYS = {
    "pl": ["pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "niedz."],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}
DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
AIR_INDEX_EN = {
    "bardzo dobry": "very good", "dobry": "good", "umiarkowany": "moderate", "dostateczny": "sufficient",
    "zły": "bad", "bardzo zły": "very bad",
}  # fmt: skip

TEXT = {
    "greet": {
        "pl": "Cześć! Jestem asystentem Syrenki. Zapytaj np. „jazz na Pradze w weekend”, „gdzie najbliższa toaleta” albo „jaka pogoda”.",
        "en": "Hi! I'm Syrenka's assistant. Try “jazz in Praga this weekend”, “nearest toilet” or “what's the weather”.",
    },
    "thanks": {"pl": "Nie ma za co! Baw się dobrze.", "en": "You're welcome! Have fun."},
    "bye": {"pl": "Na razie! Do zobaczenia na mieście.", "en": "Bye! See you around town."},
    "help": {
        "pl": "Znam wydarzenia, zajęcia i miejsca w Warszawie. Mogę:\n"
        "• znaleźć coś po rodzaju, dniu i dzielnicy: „koncerty na Mokotowie w sobotę”\n"
        "• powiedzieć, co jest otwarte: „bary otwarte teraz”, „czy Spatif jest otwarty”\n"
        "• podać termin wydarzenia: „kiedy jest Jazz na Starówce”\n"
        "• znaleźć ludzi do towarzystwa: „szukam towarzystwa na koncert w piątek”\n"
        "• wskazać najbliższą toaletę albo defibrylator\n"
        "• podać pogodę i jakość powietrza\n"
        "Możesz dopytać: „a jutro?”, „a na Woli?”, „więcej”.",
        "en": "I know Warsaw's events, classes and places. I can:\n"
        "• find things by type, day and district: “concerts in Mokotów on Saturday”\n"
        "• tell what's open: “bars open now”, “is Spatif open”\n"
        "• give an event's dates: “when is Jazz na Starówce”\n"
        "• find people to go with: “looking for company for a concert on Friday”\n"
        "• point to the nearest toilet or defibrillator\n"
        "• tell the weather and air quality\n"
        "Follow up with “and tomorrow?”, “what about Wola?”, “more”.",
    },
    "unknown": {
        "pl": "Nie zrozumiałem. Spróbuj np. „teatr jutro”, „joga na Mokotowie”, „co dziś wieczorem na Pradze” albo napisz „pomoc”.",
        "en": "I didn't get that. Try “theatre tomorrow”, “yoga in Mokotów”, “what's on tonight in Praga”, or type “help”.",
    },
    "none": {
        "pl": "Nic nie znalazłem dla: {what}. Spróbuj innego dnia albo dzielnicy.",
        "en": "Nothing found for: {what}. Try another day or district.",
    },
    "found": {"pl": "Znalazłem {n} dla: {what}.", "en": "Found {n} for: {what}."},
    "close": {
        "pl": "Nic dokładnie dla: {what}. Podobne propozycje:",
        "en": "Nothing exactly for: {what}. Related options:",
    },
    # suggestion groups: never presented as matches, each label says what was relaxed
    "sugg_broad": {
        "pl": "Więcej z kategorii: {cats}; dokładne dopasowanie nie jest potwierdzone",
        "en": "More {cats}; the exact match is not confirmed",
    },
    "sugg_elsewhere": {"pl": "Pasujące w innych częściach Warszawy", "en": "Matches elsewhere in Warsaw"},
    "sugg_later": {"pl": "Pasujące w ciągu najbliższych 30 dni", "en": "Matches in the next 30 days"},
    "more_end": {"pl": "To już wszystko dla: {what}.", "en": "That's everything for: {what}."},
    "more_hint": {"pl": "Napisz „więcej”, żeby zobaczyć kolejne.", "en": "Type “more” for the next ones."},
    "map_hint": {"pl": "Kliknij, żeby otworzyć na mapie.", "en": "Tap one to open it on the map."},
    "open_none": {"pl": "Nic otwartego nie znalazłem dla: {what}.", "en": "Nothing open found for: {what}."},
    "open_found": {"pl": "Otwarte ({when}): {n} dla: {what}.", "en": "Open ({when}): {n} for: {what}."},
    "venue_open": {
        "pl": "{name}: teraz otwarte (dziś {hours}).",
        "en": "{name} is open now (today {hours}).",
    },
    "venue_closed": {"pl": "{name}: teraz zamknięte.", "en": "{name} is closed now."},
    "venue_hours_today": {"pl": " Dziś: {hours}.", "en": " Today: {hours}."},
    "venue_no_hours": {
        "pl": "Nie mam godzin otwarcia dla {name}.",
        "en": "I don't have opening hours for {name}.",
    },
    "info_event": {"pl": "{name}: {next}{venue}.", "en": "{name}: {next}{venue}."},
    "info_past": {"pl": "{name}: brak nadchodzących terminów.", "en": "{name}: no upcoming dates."},
    "info_going": {
        "pl": " Idzie {a} os., {w} szuka towarzystwa.",
        "en": " {a} going, {w} looking for company.",
    },
    "info_none": {"pl": "Nie znam „{name}”.", "en": "I don't know “{name}”."},
    "company_found": {
        "pl": "{n} wydarzeń, gdzie ktoś szuka towarzystwa ({what}). Zaznacz „Idę” i dołącz:",
        "en": "{n} events where people are looking for company ({what}). Mark “Going” to join:",
    },
    "company_none": {
        "pl": "Na razie nikt nie szuka towarzystwa ({what}). Utwórz zaproszenie przyciskiem „+”, to inni dołączą.",
        "en": "Nobody is looking for company yet ({what}). Create an invite with “+” and others can join you.",
    },
    "toilets": {"pl": "Najbliższe toalety{from_}:", "en": "Nearest toilets{from_}:"},
    "aed": {"pl": "Najbliższe defibrylatory (AED){from_}:", "en": "Nearest defibrillators (AED){from_}:"},
    "aed_note": {
        "pl": "W nagłym wypadku dzwoń 112.",
        "en": "In an emergency call 112.",
    },
    "from_center": {
        "pl": " (od centrum, nie znam Twojej lokalizacji)",
        "en": " (from the centre, I don't know where you are)",
    },
    "amenity_none": {"pl": "Nie mam takich miejsc w pobliżu.", "en": "I have none of those nearby."},
    "weather": {
        "pl": "Teraz w Warszawie {temp}°C{wind}{rain} ({station}, {time}).",
        "en": "In Warsaw now: {temp}°C{wind}{rain} ({station}, {time}).",
    },
    "wind": {"pl": ", wiatr {v} m/s", "en": ", wind {v} m/s"},
    "rain": {"pl": ", pada", "en": ", it's raining"},
    "dry": {"pl": ", bez opadów", "en": ", dry"},
    "weather_none": {"pl": "Nie mam teraz odczytów pogody.", "en": "I have no weather readings right now."},
    "now_only": {
        "pl": " Znam tylko bieżące odczyty, nie prognozę.",
        "en": " I only know current readings, not forecasts.",
    },
    "air": {
        "pl": "Jakość powietrza: {index} ({station}, {time}).",
        "en": "Air quality: {index} ({station}, {time}).",
    },
    "air_none": {
        "pl": "Nie mam teraz odczytów jakości powietrza.",
        "en": "I have no air quality readings right now.",
    },
    "when": {
        "now": {"pl": "teraz", "en": "now"},
        "today": {"pl": "dziś", "en": "today"},
        "tomorrow": {"pl": "jutro", "en": "tomorrow"},
        "weekend": {"pl": "weekend", "en": "this weekend"},
        "week": {"pl": "7 dni", "en": "7 days"},
        "month": {"pl": "30 dni", "en": "30 days"},
        "evening": {"pl": "wieczorem", "en": "evening"},
        "morning": {"pl": "rano", "en": "morning"},
        "near": {"pl": "w pobliżu", "en": "nearby"},
        "anything": {"pl": "wszystko", "en": "anything"},
    },
}
PLURAL = {
    "pl": lambda n: (
        "1 wynik"
        if n == 1
        else f"{n} wyniki"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14
        else f"{n} wyników"
    ),
    "en": lambda n: "1 result" if n == 1 else f"{n} results",
}


def t(key: str, lang: str, **kw) -> str:
    return TEXT[key][lang].format(**kw)


def label(slug: str, lang: str) -> str:
    return PL_LABELS.get(slug, slug) if lang == "pl" else CATEGORIES.get(slug, slug).lower()


def local(dt: datetime) -> datetime:
    return dt.astimezone(WARSAW)


def fmt_dt(dt: datetime, lang: str) -> str:
    d = local(dt)
    if lang == "pl":
        return f"{WEEKDAYS['pl'][d.weekday()]} {d.day:02}.{d.month:02} {d:%H:%M}"
    return f"{WEEKDAYS['en'][d.weekday()]} {d.day} {d:%b}, {d:%H:%M}"


def fmt_date(dt: datetime, lang: str) -> str:
    return (
        f"{WEEKDAYS[lang][dt.weekday()]} {dt.day:02}.{dt.month:02}"
        if lang == "pl"
        else f"{WEEKDAYS['en'][dt.weekday()]} {dt.day} {dt:%b}"
    )


def describe(p: Parsed, lang: str) -> str:
    """'muzyka · weekend · Saska Kępa' — what the assistant understood."""
    parts = [label(c, lang) for c in p.categories]
    parts += [
        f"„{x}”" if lang == "pl" else f"“{x}”"
        for x in p.terms
        if not any(x in fold(label(c, lang)) for c in p.categories)
    ]
    if p.when:
        if p.when.key in TEXT["when"]:
            parts.append(TEXT["when"][p.when.key][lang])
        elif (p.when.end - p.when.start) <= timedelta(days=1):
            parts.append(fmt_date(p.when.start, lang))
        else:
            parts.append(f"{fmt_date(p.when.start, lang)} – {fmt_date(p.when.end - timedelta(days=1), lang)}")
    if p.evening and not (p.when and p.when.key == "now"):
        parts.append(TEXT["when"]["evening"][lang])
    if p.morning:
        parts.append(TEXT["when"]["morning"][lang])
    parts += [a.name for a in p.areas]
    if p.near:
        parts.append(TEXT["when"]["near"][lang])
    return " · ".join(parts) or TEXT["when"]["anything"][lang]


def folded(col):
    """Lowercase, Polish letters without accents, in SQL (no unaccent extension needed)."""
    return func.translate(func.lower(col), "ąćęłńóśźż", "acelnoszz")


def stem(term: str) -> str:
    return term[:-2] if len(term) > 5 else term  # koncertu -> koncer, mokotowie -> mokoto


def place_filters(stmt, p: Parsed, here):
    if p.areas:
        shapes = [
            func.ST_Intersects(
                Event.location, cast(func.ST_SetSRID(func.ST_GeomFromGeoJSON(a.geometry), 4326), Geography)
            )
            for a in p.areas
        ]
        names = [Event.district.ilike(a.name) for a in p.areas if a.kind == "district"]
        stmt = stmt.where(or_(*shapes, *names))
    if p.near and here:
        stmt = stmt.where(func.ST_DWithin(Event.location, point(here), NEAR_M))
    return stmt


def point(here: tuple[float, float]):
    return func.ST_GeogFromText(literal(f"SRID=4326;POINT({here[0]} {here[1]})"))


def term_score(terms: list[str], e: Event) -> int:
    title, rest = fold(e.title), fold(f"{e.venue_name or ''} {e.lead or ''} {e.address or ''}")
    score = 0
    for term in terms:
        if term in title or stem(term) in title:
            score += 3
        elif term in rest or stem(term) in rest:
            score += 1
    return score


def term_filter(terms: list[str]):
    cols = [
        folded(Event.title),
        folded(func.coalesce(Event.venue_name, "")),
        folded(func.coalesce(Event.lead, "")),
    ]
    return or_(*(c.contains(stem(term)) for term in terms for c in cols))


def window(p: Parsed, now: datetime, default_days: int = 30) -> tuple[datetime, datetime]:
    if p.when:
        start = p.when.start.replace(tzinfo=WARSAW) if p.when.start.tzinfo is None else p.when.start
        end = p.when.end.replace(tzinfo=WARSAW) if p.when.end.tzinfo is None else p.when.end
        return max(start, now), end
    return now, now + timedelta(days=default_days)


def time_of_day_ok(p: Parsed, occ: Occurrence) -> bool:
    if not (p.evening or p.morning) or occ.daily:
        return True
    s = local(occ.starts_at)
    if occ.ends_at and occ.ends_at - occ.starts_at > timedelta(hours=20):
        return True  # festivals, exhibitions: on all day
    if p.evening:
        return s.hour >= EVENING_HOUR or s.hour < 5
    return s.hour < MORNING_END


def occurrences(db: Session, p: Parsed, start, end, here, company: bool = False, limit: int = 400):
    counts = attendance_counts()
    stmt = (
        select(
            Event,
            Occurrence,
            func.coalesce(counts.c.attendees, 0),
            func.coalesce(counts.c.wanting_company, 0),
        )
        .join(Occurrence, Occurrence.event_id == Event.id)
        .outerjoin(counts, counts.c.occurrence_id == Occurrence.id)
        .where(
            Event.is_active,
            Event.location.is_not(None),
            Event.kind != "place",
            Occurrence.starts_at < end,
            func.coalesce(Occurrence.ends_at, Occurrence.starts_at) >= start,
        )
        .options(selectinload(Event.source))
        .order_by(Occurrence.starts_at)
        .limit(limit)
    )
    if p.categories:
        stmt = stmt.where(Event.categories.overlap(p.categories))
    elif p.terms:
        stmt = stmt.where(term_filter(p.terms))
    if company:
        stmt = stmt.where(counts.c.wanting_company > 0)
    stmt = place_filters(stmt, p, here)
    rows = [r for r in db.execute(stmt).all() if time_of_day_ok(p, r[1])]
    seen, out = set(), []
    for e, o, a, w in rows:  # one line per event: its next occurrence in the window
        if e.id not in seen:
            seen.add(e.id)
            out.append((e, o, a, w))
    out.sort(key=lambda r: r[1].starts_at < start)  # what starts in the window first, then what's already on
    return out


def open_at(e: Event, at: datetime) -> bool:
    return is_open((e.opening_hours or {}).get(DAY_NAMES[at.weekday()]), at)


def places(
    db: Session, p: Parsed, here, categories: list[str] | None = None, limit: int = 400
) -> list[Event]:
    stmt = (
        select(Event)
        .where(Event.is_active, Event.kind == "place", Event.location.is_not(None))
        .options(selectinload(Event.source))
        .limit(limit)
    )
    cats = categories if categories is not None else p.categories
    if cats:
        stmt = stmt.where(Event.categories.overlap(cats))
    else:
        stmt = stmt.where(~Event.categories.overlap(sorted(AMENITIES)))
    if p.terms and not cats:
        stmt = stmt.where(term_filter(p.terms))
    if here and p.near:
        stmt = stmt.order_by(func.ST_Distance(Event.location, point(here)))
    return db.scalars(place_filters(stmt, p, here)).all()


def check_time(p: Parsed, now: datetime) -> tuple[datetime, str]:
    """When should a place be open? Now, or the asked day at a sensible hour."""
    if not p.when or p.when.key == "now":
        return now, TEXT["when"]["now"]
    hour = 20 if p.evening else 10 if p.morning else 18
    start = p.when.start.replace(tzinfo=WARSAW) if p.when.start.tzinfo is None else p.when.start
    at = start.replace(hour=hour, minute=0)
    return max(at, now), {"pl": f"{fmt_date(at, 'pl')} {hour}:00", "en": f"{fmt_date(at, 'en')} {hour}:00"}


def line(e: Event, o: Occurrence | None, lang: str, since: datetime | None = None) -> str:
    """since: the asked window's start. Something already on by then (an exhibition) shows when it ends."""
    title = (e.i18n or {}).get(lang, {}).get("title") or e.title
    bits = [title]
    if o is not None and o.daily:
        bits.append(TEXT["when"]["now"][lang])
    elif o is not None and since and o.starts_at < since and o.ends_at:
        bits.append(("do " if lang == "pl" else "until ") + fmt_date(local(o.ends_at), lang))
    elif o is not None:
        bits.append(fmt_dt(o.starts_at, lang))
    if e.venue_name and fold(e.venue_name) not in fold(title):
        bits.append(e.venue_name)
    elif e.district:
        bits.append(e.district)
    return "• " + " · ".join(bits)


def listing(head: str, items: list, lang: str, offset: int, render) -> str:
    shown = items[offset : offset + SHOWN]
    lines = [head, *(render(x) for x in shown)]
    if len(items) > offset + SHOWN:
        lines.append(t("more_hint", lang))
    lines.append(t("map_hint", lang))
    return "\n".join(lines)


def count(n: int, lang: str) -> str:
    return PLURAL[lang](n)


# ---------- handlers: (db, parsed, lang, here, now, offset) -> (answer, features) ----------


def matches(db, p, lang, here, now):
    """Exact matches (the words, if any, appear in the event) and broad ones (only the category matches)."""
    start, end = window(p, now)
    rows = [(e, o, a, w) for e, o, a, w in occurrences(db, p, start, end, here)]
    broad: list = []
    if p.terms:
        scored = [(term_score(p.terms, r[0]), r) for r in rows]
        if any(score for score, _ in scored):
            broad = [r for score, r in scored if not score] if p.categories else []
            scored = [x for x in scored if x[0] > 0]
            scored.sort(key=lambda x: -x[0])  # stable: soonest first within a score
            rows = [r for _, r in scored]
        elif p.categories:
            rows, broad = [], rows  # nothing mentions the words: the category matches are broad, not exact
    if VENUE_CATEGORIES & set(p.categories) or (not rows and (p.categories or p.terms)):
        at, _ = check_time(p, now)
        venues = [v for v in places(db, p, here) if not v.opening_hours or open_at(v, at)]
        if p.terms:
            venues.sort(key=lambda v: -term_score(p.terms, v))
            if p.categories:
                broad += [(v, None, 0, 0) for v in venues if not term_score(p.terms, v)]
                venues = [v for v in venues if term_score(p.terms, v)]
        rows += [(v, None, 0, 0) for v in venues]
    return rows, broad, start


def suggestions(db, p, lang, here, now, exact: list, broad: list) -> list[dict]:
    """Labelled groups next to the exact results: broader category matches, and when nothing matched
    exactly, the same question without its area or its day. Each event is shown once."""
    seen = {r[0].id for r in exact}
    groups = []

    def group(kind: str, heading: str, rows: list):
        picked = []
        for e, o, a, w in rows:
            if e.id not in seen and len(picked) < SUGGESTED:
                seen.add(e.id)
                picked.append(feature(e, o, a, w, lang=lang))
        if picked:
            groups.append({"kind": kind, "label": heading, "results": picked})

    if broad:
        group("broad", t("sugg_broad", lang, cats=", ".join(label(c, lang) for c in p.categories)), broad)
    if not exact and (p.areas or p.near):
        group(
            "elsewhere",
            t("sugg_elsewhere", lang),
            matches(db, replace(p, areas=[], near=False), lang, here, now)[0],
        )
    if not exact and p.when and p.when.key != "now":
        group("later", t("sugg_later", lang), matches(db, replace(p, when=None), lang, here, now)[0])
    return groups


def find(db, p, lang, here, now, offset):
    if not (p.categories or p.terms or p.when or p.areas or p.near or p.evening or p.morning):
        return t("unknown", lang), []
    rows, broad, start = matches(db, p, lang, here, now)
    groups = suggestions(db, p, lang, here, now, rows, broad)
    what = describe(p, lang)
    features = [feature(e, o, a, w, lang=lang) for e, o, a, w in rows]
    if not rows:
        if not groups:
            return t("none", lang, what=what), []
        lines = [t("close", lang, what=what)]
        for g in groups:
            lines += [g["label"] + ":", *("• " + f.properties["title"] for f in g["results"][:2])]
        lines.append(t("map_hint", lang))
        return "\n".join(lines), [], groups
    if offset >= len(rows):
        return t("more_end", lang, what=what), features[:MAX_RESULTS], groups
    head = t("found", lang, n=count(len(rows), lang), what=what)
    render = lambda x: line(x[0], x[1], lang, start)  # noqa: E731
    return listing(head, rows, lang, offset, render), features[:MAX_RESULTS], groups


def find_named(db: Session, name: str) -> Event | None:
    """The event or venue someone names ("Spatif", "Jazz na Starówce"), typos and inflection tolerated."""
    words = sorted((w for w in name.split() if len(w) >= 3), key=len, reverse=True)[:3]
    if not words:
        return None
    stmt = (
        select(Event)
        .where(Event.is_active, or_(*(folded(Event.title).contains(stem(w)) for w in words),
                                    *(folded(func.coalesce(Event.venue_name, "")).contains(stem(w)) for w in words)))
        .options(selectinload(Event.source), selectinload(Event.occurrences))
        .limit(300)
    )  # fmt: skip
    best, best_score = None, 0.0
    for e in db.scalars(stmt):
        score = max(
            fuzz.WRatio(name, fold(e.title)), fuzz.WRatio(name, fold(e.venue_name)) - 5 if e.venue_name else 0
        )
        if score > best_score:
            best, best_score = e, score
    return best if best_score >= 75 else None


def info(db, p, lang, here, now, offset):
    e = find_named(db, p.name or " ".join(p.terms))
    if e is None:
        answer, feats, *groups = find(db, p, lang, here, now, offset)
        return (
            (
                t("info_none", lang, name=p.name) + " " + answer
                if feats
                else t("info_none", lang, name=p.name)
            ),
            feats,
            groups[0] if groups else [],
        )
    title = (e.i18n or {}).get(lang, {}).get("title") or e.title
    if e.kind == "place":
        return venue_hours(e, title, lang, now), [feature(e, None, lang=lang)]
    upcoming = [o for o in e.occurrences if (o.ends_at or o.starts_at) >= now]
    if not upcoming:
        return t("info_past", lang, name=title), [feature(e, None, lang=lang)]
    o = upcoming[0]
    nxt = fmt_dt(o.starts_at, lang)
    if len(upcoming) > 1:
        nxt += f" (+{len(upcoming) - 1})"
    venue = f" · {e.venue_name}" if e.venue_name else ""
    if e.address:
        venue += f", {e.address}"
    a, w = db.execute(
        select(func.count(), func.count().filter(Attendance.wants_company)).where(
            Attendance.occurrence_id == o.id
        )
    ).one()
    answer = t("info_event", lang, name=title, next=nxt, venue=venue)
    if a:
        answer += t("info_going", lang, a=a, w=w)
    return answer, [feature(e, o, a, w, lang=lang)]


def day_hours(e: Event, at: datetime, lang: str) -> str | None:
    hours = (e.opening_hours or {}).get(DAY_NAMES[at.weekday()])
    if hours == "00:00-24:00":
        return "całą dobę" if lang == "pl" else "24h"
    return hours


def venue_hours(e: Event, title: str, lang: str, now: datetime) -> str:
    hours = day_hours(e, now, lang)
    if not e.opening_hours:
        return t("venue_no_hours", lang, name=title)
    if hours and open_at(e, now):
        return t("venue_open", lang, name=title, hours=hours)
    return t("venue_closed", lang, name=title) + (t("venue_hours_today", lang, hours=hours) if hours else "")


def open_now(db, p, lang, here, now, offset):
    if p.name and not p.categories and not p.areas:
        e = find_named(db, p.name)
        if e is not None:
            title = (e.i18n or {}).get(lang, {}).get("title") or e.title
            return venue_hours(e, title, lang, now), [feature(e, None, lang=lang)]
    at, when = check_time(p, now)
    venues = [v for v in places(db, p, here) if v.opening_hours and open_at(v, at)]
    what = describe(p, lang)
    if not venues:
        return t("open_none", lang, what=what), []
    head = t("open_found", lang, when=when[lang], n=count(len(venues), lang), what=what)
    feats = [feature(v, None, lang=lang) for v in venues]
    return listing(
        head,
        venues,
        lang,
        offset,
        lambda v: line(v, None, lang) + f" ({day_hours(v, at, lang)})",
    ), feats[:MAX_RESULTS]


def company(db, p, lang, here, now, offset):
    start, end = window(p, now, default_days=7)
    rows = occurrences(db, p, start, end, here, company=True)
    rows.sort(key=lambda r: -r[3])
    what = describe(p, lang)
    if not rows:
        return t("company_none", lang, what=what), []
    head = t("company_found", lang, n=len(rows), what=what)
    feats = [feature(e, o, a, w, lang=lang) for e, o, a, w in rows]
    return listing(
        head, rows, lang, offset, lambda r: line(r[0], r[1], lang, start) + f" (🙋 {r[3]})"
    ), feats[:MAX_RESULTS]


def amenity(slug: str):
    def handler(db, p, lang, here, now, offset):
        origin = here or CENTER
        dist = func.ST_Distance(Event.location, point(origin))
        stmt = (
            select(Event, dist)
            .where(Event.is_active, Event.categories.overlap([slug]), Event.location.is_not(None))
            .options(selectinload(Event.source))
            .order_by(dist)
            .limit(offset + SHOWN)
        )
        rows = db.execute(stmt).all()[offset:]
        if not rows:
            return t("amenity_none", lang), []
        head = t(slug, lang, from_="" if here else t("from_center", lang))
        lines = [head]
        for e, d in rows:
            hours = day_hours(e, now, lang)
            closed = e.opening_hours and not open_at(e, now)
            extra = f" · {hours}" if hours else ""
            if closed:
                extra += " · " + ("zamknięte" if lang == "pl" else "closed now")
            lines.append(f"• {e.venue_name or e.title} · {round(d)} m{extra}")
        if slug == "aed":
            lines.append(t("aed_note", lang))
        return "\n".join(lines), [feature(e, None, distance_m=d, lang=lang) for e, d in rows]

    return handler


def nearest(rows, here):
    if not here:
        return rows
    return sorted(
        rows, key=lambda s: (s.lng - here[0]) ** 2 * 0.37 + (s.lat - here[1]) ** 2
    )  # cos(52°)² ≈ 0.37


def fresh(rows, now: datetime):
    return [s for s in rows if s.measured_at and now - s.measured_at < timedelta(hours=3)]


def weather(db, p, lang, here, now, offset):
    rows = nearest(
        fresh([s for s in db.scalars(select(WeatherStation)) if s.temp_air is not None], now), here
    )
    if not rows:
        return t("weather_none", lang), []
    s = rows[0] if here else max(rows, key=lambda s: s.measured_at)
    temp = round(sum(r.temp_air for r in rows) / len(rows)) if not here else round(s.temp_air)
    wind = t("wind", lang, v=round(s.wind_speed)) if s.wind_speed is not None else ""
    rain = "" if s.precipitation is None else t("rain", lang) if s.precipitation > 0 else t("dry", lang)
    answer = t(
        "weather", lang, temp=temp, wind=wind, rain=rain, station=s.name, time=f"{local(s.measured_at):%H:%M}"
    )
    if p.when and p.when.key not in ("now", "today"):
        answer += t("now_only", lang)
    return answer, []


def air(db, p, lang, here, now, offset):
    rows = nearest(fresh([s for s in db.scalars(select(AirStation)) if s.index_name], now), here)
    if not rows:
        return t("air_none", lang), []
    s = rows[0]
    index = s.index_name if lang == "pl" else AIR_INDEX_EN.get(s.index_name.lower(), s.index_name)
    answer = t("air", lang, index=index, station=s.name, time=f"{local(s.measured_at):%H:%M}")
    if lang == "pl" and s.recommendation:
        answer += f" {s.recommendation}"
    if p.when and p.when.key not in ("now", "today"):
        answer += t("now_only", lang)
    return answer, []


def canned(key: str):
    return lambda db, p, lang, here, now, offset: (t(key, lang), [])


HANDLERS = {
    "find": find,
    "info": info,
    "open": open_now,
    "company": company,
    "amenity_toilets": amenity("toilets"),
    "amenity_aed": amenity("aed"),
    "weather": weather,
    "air": air,
    "greet": canned("greet"),
    "thanks": canned("thanks"),
    "bye": canned("bye"),
    "help": canned("help"),
    "unknown": canned("unknown"),
}


def answer(db: Session, p: Parsed, lang: str, here: tuple[float, float] | None, offset: int = 0):
    now = datetime.now(WARSAW)  # opening hours and "today" are Warsaw time
    """-> (answer, results, suggestions); only `find` makes suggestions."""
    text, results, *groups = HANDLERS[p.intent](db, p, lang, here, now, offset)
    return text, results, groups[0] if groups else []
