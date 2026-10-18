"""Understanding a typed request: which intent, and the what / when / where in it. Polish or English,
with or without accents, typos tolerated (rapidfuzz). No LLM, no model files: word lists and rules.

The slot rules follow the map's search box (frontend/src/search/understand.js), so the assistant and the
search box read "koncerty na Saskiej Kępie w weekend" the same way.
"""

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from app.categories import CATEGORIES

AREAS_FILE = Path(__file__).resolve().parent.parent / "data" / "warsaw_areas.geojson"


def fold(s: str | None) -> str:
    """Lowercase, no accents, no punctuation: "Saskiej Kępie!" -> "saskiej kepie"."""
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("ł", "l")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]|_", " ", s)).strip()


# folded synonyms per category, on top of the category's own label
SYNONYMS = {
    "nightlife": "nightlife,night life,nightclub,nightclubs,club,clubs,clubbing,party,parties,rave,disco,dj,techno,"
    "bar,bars,pub,pubs,drinks,cocktails,beer,klub,kluby,klubie,klubach,impreza,imprezy,impreze,imprezka,imprezki,"
    "zycie nocne,zycia nocnego,dyskoteka,bary,barze,puby,koktajle,piwo,na miasto,na piwo,potancowka",
    "music": "music,concert,concerts,gig,gigs,live music,jazz,rock,opera,philharmonic,recital,muzyka,muzyki,"
    "koncert,koncerty,koncertu,koncercie,koncertow,filharmonia,filharmonii,jazzowe,jazzowy,jazzu",
    "theatre": "theatre,theater,play,plays,stand up,standup,comedy,cabaret,teatr,teatru,teatrze,spektakl,"
    "spektakle,kabaret,przedstawienie",
    "film": "film,films,movie,movies,cinema,screening,kino,kina,kinie,seans,filmy",
    "exhibitions": "exhibition,exhibitions,museum,museums,gallery,galleries,art,vernissage,wystawa,wystawy,"
    "wystawe,muzeum,muzea,galeria,galerii,sztuka,wernisaz",
    "meetups": "meetup,meetups,meet up,networking,language exchange,spotkanie,spotkania,wymiana jezykowa",
    "running": "run,runs,running,jogging,parkrun,park run,bieganie,bieg,biegi,biegac,maraton,running club,"
    "running clubs,run club,run clubs,club run,club runs,klub biegowy,kluby biegowe,grupa biegowa,grupy biegowe,"
    "wspolne bieganie",
    "yoga": "yoga,joga,jogi,jodze,joge",
    "sports": "sport,sports,football,basketball,volleyball,gym,swimming,pool,tennis,fitness,workout,pilka,"
    "pilka nozna,koszykowka,siatkowka,silownia,plywanie,basen,tenis,trening,boisko,boiska",
    "festivals": "festival,festivals,fest,festiwal,festiwale,festiwalu,piknik,picnic",
    "markets": "market,markets,flea market,fair,targ,targi,jarmark,bazar,pchli targ",
    "culture": "culture,cultural,kultura,kulturalne",
    "education": "education,lecture,lectures,workshop,workshops,course,warsztaty,wyklad,wyklady,kurs,zajecia",
    "family": "family,kids,children,for kids,dzieci,dla dzieci,rodzina,rodzinne,rodzinny",
    "business": "business,startup,biznes",
    "health": "health,zdrowie,sauna",
    "grzybki": "grzybki,mushrooms,mushroom picking,grzyby",
    "study_buddies": "study,studying,study buddies,wspolna nauka,nauka",
    "food": "food,restaurant,restaurants,eat,dinner,lunch,breakfast,cafe,coffee,jedzenie,restauracja,"
    "restauracje,restauracji,obiad,kolacja,sniadanie,kawiarnia,kawiarnie,kawa,zjesc",
}
# also rank items that mention these ("jazz" within music)
KEEP_AS_TERM = {
    "opera",
    "recital",
    "stand up",
    "standup",
    "kabaret",
    "rave",
}
# k-bar's rule-based search (feature/rule-based-prompt-search): a music genre or a cuisine sets its category
# and stays a search term, so "death metal" is exact only where the listing says so. Any alias confirms the
# term in a listing ("wloska" is italian).
GENRES = {
    "death metal": "death metal",
    "black metal": "black metal",
    "thrash metal": "thrash metal",
    "heavy metal": "heavy metal",
    "metal": "metal,metalowy,metalowa,metalowe",
    "rock": "rock,rockowy,rockowa,rockowe",
    "punk": "punk,punkowy,punkowa",
    "jazz": "jazz,jazzu,jazzowy,jazzowa,jazzowe",
    "disco polo": "disco polo",
    "techno": "techno",
    "hip hop": "hip hop",
    "classical music": "classical music,muzyka klasyczna",
    "electronic music": "electronic music,muzyka elektroniczna",
}
CUISINES = {
    "italian": "italian,wloska,wloskie",
    "mexican": "mexican,meksykanska,meksykanskie",
    "japanese": "japanese,japonska,japonskie",
    "sushi": "sushi",
    "thai": "thai,tajska,tajskie",
    "indian": "indian,indyjska,indyjskie",
    "polish": "polish,polska,polskie",
    "vegan": "vegan,weganskie,weganska",
    "vegetarian": "vegetarian,wegetarianskie,wegetarianska",
    "pizza": "pizza,pizzeria",
}
# soft preferences only rank: nothing guarantees "free" unless the listing says so
PREFERENCES = {
    "free": "free,darmowy,darmowa,darmowe,bezplatny,bezplatna,bezplatne",
    "cheap": "cheap,inexpensive,tani,tania,tanie",
    "family-friendly": "family friendly,dla rodzin,przyjazne rodzinom",
}
TERM_FORMS = {
    term: forms.split(",") for table in (GENRES, CUISINES, PREFERENCES) for term, forms in table.items()
}
# venues with opening hours are a full answer for these (a bar is open on Saturday night)
VENUE_CATEGORIES = {"nightlife", "food"}

STOP = set(
    (
        "in at on the a an for near nearby this next coming upcoming what whats is are to do go going me my i with "
        "and or of any some something things thing events event happening around best good nice cool find show "
        "where when there that please can could you tell recommend suggest want would like about how which who "
        "w we na do z ze o co cos jest sa gdzie kiedy przy obok kolo blisko ten ta te to tym tej tego "
        "najblizszy najblizsza najblizsze najblizszej nastepny nastepna nastepne nastepnej przyszly przyszla "
        "przyszle przyszlej ciekawe ciekawego fajne fajnego dzieje sie robic gdzies wydarzenia wydarzenie wydarzen "
        "jakies jakis jakas mozna idziemy isc pojsc chce chcialbym chcialabym szukam czy mi mnie polec polecisz "
        "pokaz znajdz powiedz jaki jaka jakie ktory ktora ktore o ktorej mam masz macie dla sobie tu tutaj "
        "jeszcze wiecej more else other inne cos innego a i oraz albo lub"
    ).split()
)
NEXT = {"next", "following", "nastepny", "nastepna", "nastepne", "nastepnej", "przyszly", "przyszla",
        "przyszle", "przyszlej", "kolejny", "kolejna"}  # fmt: skip
DAYS = [  # Monday first, like date.weekday()
    ["monday", "mon", "poniedzialek", "poniedzialku"],
    ["tuesday", "tue", "wtorek", "wtorku"],
    ["wednesday", "wed", "sroda", "srode", "srody", "srodzie"],
    ["thursday", "thu", "czwartek", "czwartku"],
    ["friday", "fri", "piatek", "piatku"],
    ["saturday", "sat", "sobota", "sobote", "soboty", "sobocie"],
    ["sunday", "sun", "niedziela", "niedziele", "niedzieli", "niedziel"],
]
MONTHS = [
    ["january", "jan", "styczen", "stycznia"],
    ["february", "feb", "luty", "lutego"],
    ["march", "mar", "marzec", "marca"],
    ["april", "apr", "kwiecien", "kwietnia"],
    ["may", "maj", "maja"],
    ["june", "jun", "czerwiec", "czerwca"],
    ["july", "jul", "lipiec", "lipca"],
    ["august", "aug", "sierpien", "sierpnia"],
    ["september", "sep", "sept", "wrzesien", "wrzesnia"],
    ["october", "oct", "pazdziernik", "pazdziernika"],
    ["november", "nov", "listopad", "listopada"],
    ["december", "dec", "grudzien", "grudnia"],
]
NOW = {"now", "teraz", "currently", "obecnie", "aktualnie"}
TODAY = {"today", "tonight", "dzis", "dzisiaj", "dzisiejszy", "dzisiejsza"}
TOMORROW = {"tomorrow", "jutro", "jutrzejszy", "jutrzejsza"}
WEEKEND = {"weekend", "weekendzie", "weekendu", "weekendy"}
WEEK = {"week", "tydzien", "tygodniu", "tygodnia"}
MONTH = {"month", "miesiac", "miesiacu", "miesiaca"}
MORNING = {"morning", "rano", "rana", "przedpoludnie", "przed poludniem"}
EVENING = {"tonight", "evening", "night", "late", "wieczor", "wieczorem", "wieczorny", "wieczorna", "noc",
           "noca", "nocy", "nocne"}  # fmt: skip
NEAR_ME = ["near me", "nearby", "around me", "close to me", "closest", "nearest", "kolo mnie", "obok mnie",
           "blisko mnie", "w poblizu", "niedaleko", "najblizej", "najblizszy", "najblizsza", "najblizsze"]  # fmt: skip
FOLLOW_UP = ["a ", "and ", "what about ", "how about ", "co z ", "a co z ", "a jak ", "i "]
MORE = {"more", "wiecej", "jeszcze", "else", "dalej", "kolejne"}

# Trigger words per intent: a typed word that starts with one of these (or is a near-typo of it) counts.
INTENT_WORDS = {
    "amenity_toilets": [
        "toalet",
        "wc",
        "kibel",
        "kibl",
        "toilet",
        "restroom",
        "bathroom",
        "lazienk",
        "ubikacj",
    ],
    "amenity_aed": ["defibrylator", "aed", "defibrillator"],
    "weather": [
        "pogod",
        "weather",
        "temperatur",
        "deszcz",
        "pada",
        "rain",
        "zimno",
        "cieplo",
        "wiatr",
        "wind",
        "parasol",
        "umbrella",
        "stopni",
        "degrees",
        "snieg",
        "snow",
    ],  # fmt: skip
    "air": ["smog", "powietrz", "air", "pm10", "pm25", "pm2", "zanieczyszcz", "pollution"],
    "company": [
        "towarzystw",
        "company",
        "alone",
        "sam ",
        "sama ",
        "kto idzie",
        "who is going",
        "whos going",
        "z kim",
        "someone to go",
        "kogos",
        "people going",
        "join someone",
        "dolaczyc",
    ],  # fmt: skip
    "open": ["open", "otwart", "czynn", "opening hours", "godziny otwarcia"],
}
SMALL_TALK = {
    "greet": [
        "hi",
        "hello",
        "hey",
        "hej",
        "czesc",
        "siema",
        "elo",
        "dzien dobry",
        "dobry wieczor",
        "witam",
        "good morning",
        "good evening",
        "yo",
        "hejka",
        "siemka",
    ],  # fmt: skip
    "thanks": [
        "thanks",
        "thank you",
        "thx",
        "dzieki",
        "dziekuje",
        "dziekowac",
        "super dzieki",
        "great thanks",
    ],
    "bye": ["bye", "goodbye", "see you", "pa", "papa", "na razie", "do widzenia", "nara", "cześć na razie"],
    "help": [
        "help",
        "what can you do",
        "how does it work",
        "what do you know",
        "pomoc",
        "pomocy",
        "co umiesz",
        "co potrafisz",
        "jak to dziala",
        "w czym pomozesz",
        "kim jestes",
        "who are you",
        "what are you",
    ],  # fmt: skip
}
QUESTION_WORDS = {
    "czy",
    "is",
    "are",
    "when",
    "where",
    "kiedy",
    "gdzie",
    "what",
    "time",
    "ktorej",
    "the",
    "ile",
}
QUESTION_INFO = re.compile(r"^(when|where|what time|kiedy|gdzie|o ktorej|jak dlugo|ile osob|how many)\b")


@dataclass
class Area:
    name: str
    kind: str  # district / area
    district: str | None
    geometry: str = field(repr=False)  # GeoJSON, for PostGIS


@dataclass
class When:
    start: datetime  # local Warsaw time
    end: datetime
    key: str  # now / today / tomorrow / weekend / week / month / day / date


@dataclass
class Parsed:
    intent: str
    categories: list[str] = field(default_factory=list)
    when: When | None = None
    evening: bool = False
    morning: bool = False
    areas: list[Area] = field(default_factory=list)
    near: bool = False
    terms: list[str] = field(default_factory=list)
    name: str = ""  # the rest of the sentence, for "is Spatif open" / "when is Jazz na Starówce"
    more: bool = False
    follow_up: bool = False
    preferences: list[str] = field(default_factory=list)  # free / cheap / family-friendly: ranking only

    def context(self) -> dict:
        """What the frontend sends back next time, so "and tomorrow?" keeps the rest."""
        return {
            "intent": self.intent,
            "categories": self.categories,
            "when": {
                "start": self.when.start.isoformat(),
                "end": self.when.end.isoformat(),
                "key": self.when.key,
            }
            if self.when
            else None,
            "evening": self.evening,
            "morning": self.morning,
            "areas": [a.name for a in self.areas],
            "near": self.near,
            "terms": self.terms,
            "name": self.name,
            "preferences": self.preferences,
        }


@lru_cache(maxsize=1)
def areas() -> list[tuple[list[str], Area]]:
    """Warsaw's districts and neighbourhoods (from OpenStreetMap, frontend/scripts/build_areas.py)."""
    fc = json.loads(AREAS_FILE.read_text(encoding="utf-8"))
    out = []
    for f in fc["features"]:
        p = f["properties"]
        out.append(
            (
                fold(p["name"]).split(),
                Area(p["name"], p["kind"], p.get("district"), json.dumps(f["geometry"])),
            )
        )
    return out


def area_named(name: str) -> Area | None:
    return next((a for _, a in areas() if a.name == name), None)


# words people use for a place that is not one OSM area
AREA_ALIASES = {
    "praga": ["Praga-Północ", "Praga-Południe"],
    "centrum": ["Śródmieście"],
    "center": ["Śródmieście"],
    "centre": ["Śródmieście"],
    "downtown": ["Śródmieście"],
    "city centre": ["Śródmieście"],
    "city center": ["Śródmieście"],
    "starowka": ["Stare Miasto"],
    "starowce": ["Stare Miasto"],
    "old town": ["Stare Miasto"],
}


def same_word(typed: str, name: str) -> bool:
    """Does a typed word mean this name word? Exact, or a Polish case ending: woli~wola, kepie~kepa."""
    if typed == name:
        return True
    if len(typed) < 3 or typed in STOP:
        return False
    k = 0
    while k < len(typed) and k < len(name) and typed[k] == name[k]:
        k += 1
    return k >= max(3, len(name) - 2) and abs(len(typed) - len(name)) <= 4


def word_hit(tokens: list[str], text: str, triggers: list[str]) -> bool:
    """A trigger is a word stem ("toalet") or a phrase ("z kim"). Long stems also match near-typos."""
    padded = f" {text} "
    for t in triggers:
        if " " in t.strip() or t.endswith(" "):
            if f" {t.strip()} " in padded:
                return True
            continue
        for tok in tokens:
            if tok.startswith(t) and (len(t) >= 4 or tok == t or len(tok) <= len(t) + 3):
                return True
            if len(t) >= 5 and len(tok) >= 5 and fuzz.ratio(tok[: len(t)], t) >= 80:  # pogda ~ pogod
                return True
    return False


@lru_cache(maxsize=1)
def synonym_index() -> list[tuple[list[str], str]]:
    pairs = []
    for slug, label in CATEGORIES.items():
        phrases = {fold(label), *(s.strip() for s in SYNONYMS.get(slug, "").split(","))} - {""}
        pairs += [(p.split(), slug) for p in phrases]
    return sorted(pairs, key=lambda p: -len(p[0]))  # "zycie nocne" before "nocne"


@lru_cache(maxsize=3)
def phrase_index(table: str) -> list[tuple[list[str], str]]:
    """PREFERENCES / GENRES / CUISINES as (words, term), longest first: "death metal" before "metal"."""
    pairs = [(f.split(), term) for term, forms in globals()[table].items() for f in forms.split(",")]
    return sorted(pairs, key=lambda p: -len(p[0]))


def day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def span(d1: date, d2: date, key: str) -> When:
    return When(day_start(d1), day_start(d2) + timedelta(days=1), key)


def month_number(word: str) -> int | None:
    return next((k + 1 for k, names in enumerate(MONTHS) if word in names), None)


def parse_when(tokens: list[str], used: list[bool], now: datetime) -> When | None:
    def find(words) -> int:
        return next((i for i, t in enumerate(tokens) if not used[i] and t in words), -1)

    is_next = any(not used[i] and t in NEXT for i, t in enumerate(tokens))
    today = now.date()
    dow = today.weekday()
    # explicit date: "25 października", "october 25" ("25.10" is read before fold(), see dotted_date)
    for i in range(len(tokens) - 1):
        if used[i] or used[i + 1]:
            continue
        a, b = tokens[i], tokens[i + 1]
        if a.isdigit() and (m := month_number(b)):
            day_num, month = int(a), m
        elif b.isdigit() and (m := month_number(a)):
            day_num, month = int(b), m
        else:
            continue
        try:
            d = date(today.year, month, day_num)
        except ValueError:
            continue
        if d < today:
            d = d.replace(year=today.year + 1)
        used[i] = used[i + 1] = True
        return span(d, d, "date")
    if (i := find(NOW)) >= 0:
        used[i] = True
        return When(now, now + timedelta(hours=3), "now")
    if (i := find(TODAY)) >= 0:
        used[i] = True
        return span(today, today, "today")
    if (i := find(TOMORROW)) >= 0:
        used[i] = True
        d = today + timedelta(days=1)
        return span(d, d, "tomorrow")
    if (i := find(WEEKEND)) >= 0:
        used[i] = True
        to_sat = 5 - dow  # Sunday: -1, this weekend is today
        start = to_sat + 7 if is_next else max(0, to_sat)
        end = start + 1 if (is_next or dow != 6) else 0
        return span(today + timedelta(days=start), today + timedelta(days=end), "weekend")
    if (i := find(WEEK)) >= 0:
        used[i] = True
        if is_next:
            monday = today + timedelta(days=7 - dow)
            return span(monday, monday + timedelta(days=6), "week")
        return span(today, today + timedelta(days=6), "week")
    if (i := find(MONTH)) >= 0:
        used[i] = True
        return span(today, today + timedelta(days=30), "month")
    for d, names in enumerate(DAYS):
        if (i := find(names)) >= 0:
            used[i] = True
            ahead = (d - dow) % 7 or (7 if is_next else 0)
            day = today + timedelta(days=ahead)
            return span(day, day, "day")
    return None


def dotted_date(text: str, now: datetime) -> tuple[When | None, str]:
    """ "25.10" / "25/10" before fold() splits it. Returns the span and the text without it."""
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})\b", text)
    if not m:
        return None, text
    try:
        d = date(now.year, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None, text
    if d < now.date():
        d = date(now.year + 1, d.month, d.day)
    return span(d, d, "date"), text[: m.start()] + " " + text[m.end() :]


def detect_intent(tokens: list[str], text: str) -> str | None:
    for intent in ("amenity_toilets", "amenity_aed", "air", "weather", "company", "open"):
        if word_hit(tokens, text, INTENT_WORDS[intent]):
            return intent
    return None


def small_talk(text: str) -> str | None:
    """Greeting, thanks, bye or help, when that is (nearly) the whole message."""
    best, best_score = None, 0.0
    for intent, phrases in SMALL_TALK.items():
        for p in phrases:
            score = fuzz.ratio(text, p) if len(text) <= 4 or len(p) <= 4 else fuzz.token_set_ratio(text, p)
            if score > best_score:
                best, best_score = intent, score
    if best_score >= 90 or (best_score >= 80 and len(text) > 5):
        return best
    return None


def understand(query: str, now: datetime) -> Parsed:
    """now: local Warsaw time (naive)."""
    when, query = dotted_date(query, now)
    text = fold(query)
    tokens = text.split()
    used = [False] * len(tokens)

    def take(i: int, n: int) -> None:
        for k in range(i, i + n):
            used[k] = True

    intent = detect_intent(tokens, text)

    def phrase_at(phrase: list[str]) -> bool:
        n = len(phrase)
        for i in range(len(tokens) - n + 1):
            if not any(used[i : i + n]) and tokens[i : i + n] == phrase:
                take(i, n)
                return True
        return False

    # what: soft preferences, then genres and cuisines (k-bar's rules), then the categories
    categories, keep, preferences = [], [], []
    for phrase, pref in phrase_index("PREFERENCES"):
        if phrase_at(phrase) and pref not in preferences:
            preferences.append(pref)
    for table, slug in (("GENRES", "music"), ("CUISINES", "food")):
        for phrase, term in phrase_index(table):
            if phrase_at(phrase):
                categories += [slug] if slug not in categories else []
                keep += [term] if term not in keep else []
    for phrase, slug in synonym_index():
        n = len(phrase)
        for i in range(len(tokens) - n + 1):
            if not any(used[i : i + n]) and tokens[i : i + n] == phrase:
                take(i, n)
                if slug not in categories:
                    categories.append(slug)
                if " ".join(phrase) in KEEP_AS_TERM:
                    keep.append(" ".join(phrase))

    # where: aliases ("praga", "old town"), then the longest area name whose words all appear in a row
    found: list[Area] = []
    for alias, names in sorted(AREA_ALIASES.items(), key=lambda a: -len(a[0])):
        words = alias.split()
        for i in range(len(tokens) - len(words) + 1):
            if not any(used[i : i + len(words)]) and all(
                same_word(tokens[i + k], w) for k, w in enumerate(words)
            ):
                if alias == "praga" and i + 1 < len(tokens) and tokens[i + 1].startswith(("pol", "pn", "pd")):
                    continue  # "Praga Północ/Południe" is an area name: matched below
                take(i, len(words))
                found = [a for a in map(area_named, names) if a]
    if not found:
        best, best_len, best_at = None, 0, 0
        for words, a in areas():
            n = len(words)
            if n < best_len:
                continue
            for i in range(len(tokens) - n + 1):
                if any(used[i : i + n]) or not all(same_word(tokens[i + k], w) for k, w in enumerate(words)):
                    continue
                if n > best_len or (a.kind == "district" and best and best.kind != "district"):
                    best, best_len, best_at = a, n, i
        if best:
            take(best_at, best_len)
            found = [best]

    near = any(f" {p} " in f" {text} " for p in NEAR_ME)
    if near:
        for p in NEAR_ME:
            words = p.split()
            for i in range(len(tokens) - len(words) + 1):
                if tokens[i : i + len(words)] == words:
                    take(i, len(words))

    # when
    when = when or parse_when(tokens, used, now)
    evening = "nightlife" in categories or "tonight" in tokens
    for i, t in enumerate(tokens):
        if not used[i] and t in EVENING:
            used[i] = True
            evening = True

    morning = False
    for i, t in enumerate(tokens):
        if not used[i] and t in MORNING:
            used[i] = True
            morning = True

    more = any(t in MORE for t in tokens)
    follow_up = any(f"{text} ".startswith(p) for p in FOLLOW_UP) or text.endswith(("i co", "and"))

    rest = [t for i, t in enumerate(tokens) if not used[i]]
    terms = keep + [t for t in rest if t not in STOP and t not in NEXT and len(t) > 1 and not t.isdigit()]
    for words in INTENT_WORDS.get(intent or "", []):  # "open" / "toaleta" are not search terms
        terms = [t for t in terms if not t.startswith(words.strip())]
    words = [t for t in rest if t not in NEXT and not any(t.startswith(w) for w in INTENT_WORDS["open"])]
    while words and words[0] in STOP | QUESTION_WORDS:
        words.pop(0)
    while words and words[-1] in STOP | QUESTION_WORDS:
        words.pop()
    name = " ".join(words)  # "czy Spatif jest otwarty" -> "spatif"; inner words stay ("jazz na starowce")

    if intent is None:
        slots = categories or when or found or near or evening or morning or preferences
        if not slots and (chat := small_talk(text)):
            intent = chat
        elif QUESTION_INFO.match(text) and terms and not categories:
            intent = "info"
        elif not (slots or terms or more or follow_up):
            intent = "unknown"
        else:
            intent = "find"
    return Parsed(
        intent, categories, when, evening, morning, found, near, terms, name, more, follow_up, preferences
    )


def merge(new: Parsed, ctx: dict | None) -> Parsed:
    """A follow-up ("and tomorrow?", "a na Mokotowie?", "more") keeps what the last question asked for."""
    if not ctx or new.intent in ("greet", "thanks", "bye", "help"):
        return new
    last = ctx.get("intent")
    slots_only = not new.categories and not new.terms
    if not (new.follow_up or new.more or (slots_only and new.intent in ("find", "unknown"))):
        return new
    if last not in ("find", "company", "open", "amenity_toilets", "amenity_aed", "weather", "air"):
        return new
    if new.intent in ("find", "unknown"):
        new.intent = last
    if not new.categories:
        new.categories = list(ctx.get("categories") or [])
        new.terms = new.terms or list(ctx.get("terms") or [])
    if not new.when and ctx.get("when"):
        w = ctx["when"]
        new.when = When(datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"]), w["key"])
    if not new.areas and not new.near:
        new.areas = [a for a in map(area_named, ctx.get("areas") or []) if a]
        new.near = bool(ctx.get("near"))
    if not new.when:
        new.evening = new.evening or bool(ctx.get("evening"))
        new.morning = new.morning or bool(ctx.get("morning"))
    new.name = new.name or ctx.get("name") or ""
    new.preferences = new.preferences or list(ctx.get("preferences") or [])
    return new


def to_dict(p: Parsed) -> dict:
    """Debug view of a parse (tests, logs)."""
    d = asdict(p)
    d["areas"] = [a.name for a in p.areas]
    return d
