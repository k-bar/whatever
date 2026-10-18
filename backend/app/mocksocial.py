"""Demo people: 30 made-up Varsovians so the social side of the map has someone in it.

    python -m app.mocksocial          # create / refresh them (safe to re-run; run by every ingest)

Each of them
  - has a Polish name, an Instagram-style @handle, a bio, interests and the Syrenka favicon as photo
  - is friends with 3-20 of the others (one random web, the same on every run)
  - has been to 1-3 past events and is going to 1-3 upcoming ones, picked from our catalogue
    (preferring their interests); topped up / trimmed on every run, so the lists stay true as time passes
  - hosts one upcoming open invitation (audience "public_confirm", so it is a "New friends" pin); once
    it is over it moves to a new date. Some of their friends asked to join; the host approved some of them
  - has "Share my area" on, somewhere in Warsaw (app/routers/people.py)

They are marked users.is_mock (their profiles are public) and can't log in (random password).
Not run on prod (app_env "prod").
"""

import random
import secrets
import zlib
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.db import SessionLocal
from app.friends import pair
from app.models import Attendance, Event, Friendship, JoinRequest, Occurrence, Source, User
from app.timeutil import WARSAW
from app.userevents import EVENT_TYPES, SOURCE_SLUG
from app.userevents.models import UserEvent
from app.userevents.service import publish

AVATAR = "/people/avatar.svg"
EMAIL = "{}@demo.syrenka.me"
SEED = 1830  # the graph and the people are the same on every run

# fmt: off
# first, last, gender, @handle, interests, bio, "you can find me at"
PEOPLE = [
    ("Agnieszka", "Wiśniewska", "f", "agnieszk.w", ["meetups", "culture", "film"], "Graficzka z Mokotowa. Planszówki, kino i dobra herbata.", ["Plac Zbawiciela"]),
    ("Maciej", "Kowalczyk", "m", "macie_k", ["running", "sports", "health"], "Biegam, bo lubię jeść. Pole Mokotowskie to mój drugi dom.", ["Pole Mokotowskie"]),
    ("Zbigniew", "Zieliński", "m", "zbysz37", ["culture", "meetups", "exhibitions"], "Emerytowany inżynier, szachista, gaduła.", ["Ogród Saski"]),
    ("Katarzyna", "Lewandowska", "f", "kasia.lew", ["meetups", "markets", "festivals"], "Powiśle, bulwary, zachody słońca. Zawsze z kocem w plecaku.", ["Bulwary Wiślane"]),
    ("Grzegorz", "Wójcik", "m", "grzesiek_wojo", ["sports", "running", "meetups"], "Rower w każdą pogodę. Szukam ekipy na weekendowe trasy.", ["Most Poniatowskiego"]),
    ("Małgorzata", "Kamińska", "f", "gosia.kam", ["yoga", "health", "meetups"], "Nauczycielka jogi. Wstaję z kurami, chodzę spać z sowami.", ["Park Skaryszewski"]),
    ("Przemysław", "Szymański", "m", "przemo.sz", ["film", "nightlife", "music"], "Praga Północ od urodzenia. Kino, winyle, podwórka.", ["Ząbkowska"]),
    ("Joanna", "Woźniak", "f", "asia_wozniak", ["study_buddies", "education", "culture"], "Studentka prawa na UW. Kawa, notatki, powtórka.", ["BUW"]),
    ("Krzysztof", "Dąbrowski", "m", "krzychu.d", ["culture", "meetups", "exhibitions"], "Przewodnik po Starówce. Znam każdą kamienicę.", ["Plac Zamkowy"]),
    ("Magdalena", "Kozłowska", "f", "madzia.koz", ["sports", "festivals", "nightlife"], "Siatkówka plażowa, a potem coś zimnego.", ["Plaża Poniatówka"]),
    ("Tomasz", "Jankowski", "m", "tomek_jank", ["music", "nightlife", "festivals"], "Gram na basie. Jam session? Zawsze.", ["Muzeum nad Wisłą"]),
    ("Aleksandra", "Mazur", "f", "ola.mazur", ["grzybki", "meetups", "health"], "Na grzyby jeżdżę z mapą i termosem. Prawdziwki albo nic.", ["Las Kabacki"]),
    ("Paweł", "Kwiatkowski", "m", "pawel.kwiat", ["film", "culture", "theatre"], "Kieślowski, Wajda, Holland. Dyskusje po seansie mile widziane.", ["Muranów"]),
    ("Zofia", "Krawczyk", "f", "zosia_kraw", ["sports", "meetups", "running"], "Gram w piłkę od podstawówki. Szukam drużyny na środy.", ["Agrykola"]),
    ("Łukasz", "Piotrowski", "m", "lukasz.p88", ["exhibitions", "culture", "nightlife"], "Wernisaże, wino i rozmowy do późna.", ["Zachęta"]),
    ("Weronika", "Grabowska", "f", "wera.grab", ["nightlife", "music", "festivals"], "Karaoke to sport wyczynowy. Disco polo też się liczy.", ["Nowy Świat"]),
    ("Bartosz", "Nowakowski", "m", "bartek_nowak", ["meetups", "family", "health"], "Ja i mój beagle Pimpek. Spacery po Żoliborzu.", ["Park Żeromskiego"]),
    ("Justyna", "Pawłowska", "f", "justi.paw", ["meetups", "education", "nightlife"], "Quizy w pubach. Specjalność: geografia i lata 90.", ["Plac Konstytucji"]),
    ("Michał", "Michalski", "m", "misiek.m", ["sports", "family", "running"], "Rolki, deskorolka, co ma kółka. Wilanów i okolice.", ["Wilanów"]),
    ("Dorota", "Adamczyk", "f", "dorotka_a", ["meetups", "music", "grzybki"], "Ogniska, gitara i kiełbaski. Las Bielański najlepszy.", ["Las Bielański"]),
    ("Wojciech", "Zając", "m", "wojtek.zajac", ["sports", "health", "meetups"], "Kajaki, żagle, wszystko co pływa.", ["Port Czerniakowski"]),
    ("Ewa", "Król", "f", "ewcia.krol", ["theatre", "culture", "nightlife"], "Improwizuję na scenie i w kuchni.", ["Teatr Powszechny"]),
    ("Jakub", "Wieczorek", "m", "kuba_wiecz", ["markets", "meetups", "culture"], "Sobota = targ, śniadanie, kawa. W tej kolejności.", ["Hala Mirowska"]),
    ("Monika", "Jabłońska", "f", "monia.jablko", ["exhibitions", "culture", "family"], "Maluję akwarelami w Łazienkach. Przynieś pędzel.", ["Łazienki"]),
    ("Szymon", "Wróbel", "m", "szymek_wrobel", ["music", "festivals", "culture"], "Koncerty plenerowe, im głośniej, tym lepiej.", ["Park Sowińskiego"]),
    ("Natalia", "Stępień", "f", "nati.stepien", ["nightlife", "music", "health"], "Salsa, bachata, kizomba. Uczę początkujących.", ["Plac Defilad"]),
    ("Jarosław", "Górski", "m", "jarek.gorski", ["sports", "health", "running"], "Trener personalny. Pierwszy trening gratis, drugi też.", ["Park Szczęśliwicki"]),
    ("Bożena", "Sikora", "f", "bozenka_s", ["markets", "family", "meetups"], "Lepię pierogi jak babcia. Ruskie, z mięsem, z jagodami.", ["Saska Kępa"]),
    ("Mateusz", "Baran", "m", "mati.baran", ["sports", "meetups", "culture"], "Bule, krykiet, gry podwórkowe. Wola górą.", ["Park Moczydło"]),
    ("Halina", "Rutkowska", "f", "halinka44", ["culture", "family", "meetups"], "Robię na drutach i opowiadam o dawnej Ochocie.", ["Plac Narutowicza"]),
]

# the open invitation each of them hosts: title, event type, place, lat, lng, hour, what to expect
HOSTING = [
    ("Planszówki i herbata", "games", "Plac Zbawiciela", 52.2195, 21.0177, 18, "Przynoszę Carcassonne i Dixit. Szukamy jeszcze 3-4 osób."),
    ("Bieganie: pętla Pola Mokotowskiego", "run", "Pole Mokotowskie", 52.2125, 20.9990, 8, "Spokojne 5 km, tempo rozmowy. Potem kawa."),
    ("Szachy w Ogrodzie Saskim", "games", "Ogród Saski", 52.2405, 21.0080, 16, "Mam dwie szachownice. Każdy poziom mile widziany."),
    ("Piknik na Bulwarach", "picnic", "Bulwary Wiślane", 52.2425, 21.0300, 17, "Koc, owoce, zachód słońca nad Wisłą. Przynieś coś do podzielenia."),
    ("Rower nad Wisłą", "sport", "Most Poniatowskiego", 52.2370, 21.0420, 10, "Około 30 km wzdłuż Wisły, z przerwą na lody."),
    ("Joga o wschodzie słońca", "yoga", "Park Skaryszewski", 52.2440, 21.0590, 7, "Godzina łagodnej jogi na trawie. Mata i woda."),
    ("Kino plenerowe na podwórku", "film", "Ząbkowska", 52.2530, 21.0430, 20, "Rzutnik na ścianie kamienicy, stara polska komedia."),
    ("Wspólna nauka przed sesją", "studying", "BUW, Biblioteka Uniwersytecka", 52.2425, 21.0250, 10, "Pomodoro w grupie: 50 minut nauki, 10 minut gadania."),
    ("Spacer po Starówce", "meetup", "Plac Zamkowy", 52.2477, 21.0137, 15, "Opowiem, co tu było przed wojną i jak to odbudowano."),
    ("Siatkówka plażowa", "sport", "Plaża Poniatówka", 52.2365, 21.0450, 17, "Mamy siatkę i piłkę, brakuje nam dwóch osób."),
    ("Jam session nad Wisłą", "concert", "Muzeum Sztuki Nowoczesnej nad Wisłą", 52.2372, 21.0340, 19, "Akustycznie: gitara, bas, cajon. Śpiewający też."),
    ("Grzybobranie w Lesie Kabackim", "meetup", "Las Kabacki", 52.1270, 21.0570, 9, "Zbiórka przy metrze Kabaty. Koszyk, nóż, kalosze."),
    ("Wieczór z Kieślowskim", "film", "Muranów", 52.2470, 20.9960, 19, "Dekalog, odcinek pierwszy, potem rozmowa przy herbacie."),
    ("Mecz na Agrykoli", "sport", "Agrykola", 52.2140, 21.0330, 18, "Gramy 5 na 5, mieszane składy. Korki niekonieczne."),
    ("Wernisaż i wino", "exhibition", "Zachęta", 52.2390, 21.0110, 18, "Idziemy razem na nową wystawę, potem wino na Królewskiej."),
    ("Karaoke po polsku", "party", "Nowy Świat", 52.2330, 21.0190, 21, "Tylko polskie hity. Wymagany co najmniej jeden Perfect."),
    ("Spacer z psami po Żoliborzu", "meetup", "Park Żeromskiego", 52.2700, 20.9850, 17, "Psy, ludzie, smaczki. Mile widziani też bez psa."),
    ("Quiz w pubie", "games", "Plac Konstytucji", 52.2215, 21.0145, 20, "Szukam 2-3 osób do drużyny. Nagroda: chwała i piwo."),
    ("Rolki na Wilanowie", "sport", "Wilanów", 52.1650, 21.0900, 16, "Równe ścieżki wokół pałacu. Kask obowiązkowy."),
    ("Ognisko w Lesie Bielańskim", "picnic", "Las Bielański", 52.2930, 20.9580, 18, "Gitara, kiełbaski, śpiewnik. Kocyk się przyda."),
    ("Kajaki po Wiśle", "sport", "Port Czerniakowski", 52.2230, 21.0510, 11, "Dwie godziny z prądem, wracamy autobusem."),
    ("Otwarty wieczór improwizacji", "theatre", "Teatr Powszechny", 52.2370, 21.0610, 19, "Ćwiczenia z impro dla każdego. Bez tremy, bez scenariusza."),
    ("Sobotni targ i śniadanie", "meetup", "Hala Mirowska", 52.2385, 20.9950, 10, "Zakupy na targu, potem wspólne śniadanie z tego, co kupimy."),
    ("Akwarele w Łazienkach", "exhibition", "Park Łazienkowski", 52.2150, 21.0350, 15, "Mam zapasowe farby i papier. Malujemy Pałac na Wyspie."),
    ("Koncert w Parku Sowińskiego", "concert", "Park Sowińskiego", 52.2335, 20.9530, 19, "Idziemy razem pod scenę. Spotkanie przy wejściu."),
    ("Salsa dla początkujących", "party", "Plac Defilad", 52.2310, 21.0060, 20, "Pierwsze kroki salsy pod Pałacem Kultury. Para niepotrzebna."),
    ("Trening w Parku Szczęśliwickim", "sport", "Park Szczęśliwicki", 52.2080, 20.9600, 18, "Godzina obwodów na siłowni plenerowej. Każdy poziom."),
    ("Lepimy pierogi razem", "meetup", "Saska Kępa", 52.2320, 21.0560, 17, "Ciasto i farsz z przepisu babci. Zjadamy na miejscu."),
    ("Gra w bule", "games", "Park Moczydło", 52.2390, 20.9480, 16, "Mam komplet kul. Zasady wytłumaczę w pięć minut."),
    ("Herbatka i robótki", "meetup", "Plac Narutowicza", 52.2200, 20.9850, 15, "Druty, szydełka, herbata i ciasto drożdżowe."),
]

# where they are right now ("share my area"): around these, a few hundred metres off
AREAS = [
    (52.2319, 21.0187), (52.2497, 21.0122), (52.2400, 21.0290), (52.2530, 21.0420), (52.2330, 21.0560),
    (52.1950, 21.0150), (52.2110, 21.0190), (52.2690, 20.9840), (52.2300, 20.9840), (52.2200, 20.9850),
    (52.2470, 20.9970), (52.2120, 21.0000), (52.2850, 20.9600), (52.2450, 21.0900), (52.2260, 21.0110),
]
# fmt: on

ASK = ["Mogę dołączyć?", "Brzmi super, wpadnę!", "Czy jest jeszcze miejsce?", "Chętnie, jeśli można.", None]


def rng(*key) -> random.Random:
    return random.Random(zlib.crc32(repr((SEED, *key)).encode()))


def friend_graph(n: int) -> set[tuple[int, int]]:
    """A random web where everyone has 3-20 friends."""
    r = rng("graph")
    want = [3, 20] + [
        int(r.triangular(3, 20.99, 7)) for _ in range(n - 2)
    ]  # the loner and the social butterfly
    r.shuffle(want)
    edges: set[tuple[int, int]] = set()
    deg = [0] * n
    order = sorted(range(n), key=lambda i: -want[i])  # the most sociable pick first, while others have room
    for i in order:
        others = [j for j in range(n) if j != i]
        r.shuffle(others)
        for j in others:
            if deg[i] >= want[i]:
                break
            e = (min(i, j), max(i, j))
            if e not in edges and deg[j] < 20 and (deg[j] < want[j] or deg[i] < 3):
                edges.add(e)
                deg[i] += 1
                deg[j] += 1
    for i in range(n):  # anyone still under 3 (everyone else was full)
        for j in sorted(range(n), key=lambda k: deg[k]):
            if deg[i] >= 3:
                break
            e = (min(i, j), max(i, j))
            if j != i and e not in edges and deg[j] < 20:
                edges.add(e)
                deg[i] += 1
                deg[j] += 1
    return edges


def ensure_people(db: Session, now: datetime) -> list[User]:
    users = []
    for i, (first, last, gender, handle, interests, bio, hangouts) in enumerate(PEOPLE):
        email = EMAIL.format(handle)
        u = db.scalar(select(User).where(User.email == email))
        if u is None:
            name = handle
            if db.scalar(select(func.count()).select_from(User).where(User.username == name)):
                name = f"{handle[:26]}_waw"  # a real person took it first
            u = User(email=email, password_hash=hash_password(secrets.token_urlsafe(24)), username=name)
            db.add(u)
        r = rng("area", i)
        lat, lng = AREAS[r.randrange(len(AREAS))]
        u.display_name = f"{first} {last[0]}."
        u.first_name, u.last_name, u.gender = first, last, gender
        u.age = rng("age", i).randint(19, 72) if handle != "zbysz37" else 69
        u.bio, u.interests, u.photos = bio, interests, [AVATAR]
        u.hangouts = [{"name": h, "place_id": None} for h in hangouts]
        u.is_mock, u.share_area = True, True
        u.area_lat = round(lat + r.uniform(-0.006, 0.006), 4)
        u.area_lng = round(lng + r.uniform(-0.009, 0.009), 4)
        u.area_at = now
        users.append(u)
    db.flush()
    return users


def ensure_friends(db: Session, users: list[User], now: datetime) -> None:
    for a, b in friend_graph(len(users)):
        ua, ub = users[a], users[b]
        f = pair(db, ua.id, ub.id)
        if f is None:
            db.add(Friendship(requester_id=ua.id, addressee_id=ub.id, status="accepted", responded_at=now))
        elif f.status != "accepted":
            f.status, f.responded_at = "accepted", now
    db.flush()


ENDED = func.coalesce(Occurrence.ends_at, Occurrence.starts_at)
# things you'd tell friends you went to (not e.g. "free legal advice" or a clinic, which are "other" / "health")
FUN = [
    "music",
    "nightlife",
    "theatre",
    "film",
    "exhibitions",
    "meetups",
    "grzybki",
    "study_buddies",
    "running",
    "yoga",
    "sports",
    "festivals",
    "markets",
    "culture",
]
NOT_FUN = r"dyżur|\mops\M|konsultac|porad|badani|terapi|wsparci|dla dzieci|dla senior|w wieku"


def catalogue(db: Session, now: datetime, past: bool) -> list[tuple[int, int, list[str]]]:
    """(occurrence id, event id, categories) of real dated catalogue events: the last 120 days, or the next 30."""
    stmt = (
        select(Occurrence.id, Event.id, Event.categories)
        .join(Event, Event.id == Occurrence.event_id)
        .join(Source, Source.id == Event.source_id)
        .where(
            Event.kind == "event",
            Event.lat.is_not(None),
            Event.host_user_id.is_(None),
            Source.slug != SOURCE_SLUG,
            Event.categories.overlap(FUN),
            ~Event.categories.overlap(["health", "other"]),
            ~Event.title.regexp_match(NOT_FUN, flags="i"),
            Occurrence.daily.is_not(True),
            or_(Occurrence.ends_at.is_(None), Occurrence.ends_at - Occurrence.starts_at < timedelta(days=2)),
        )
    )
    if past:
        stmt = stmt.where(ENDED < now, Occurrence.starts_at > now - timedelta(days=120))
    else:
        stmt = stmt.where(
            Event.is_active, Occurrence.starts_at >= now, Occurrence.starts_at < now + timedelta(days=30)
        )
    return [(oid, eid, cats or []) for oid, eid, cats in db.execute(stmt.order_by(Occurrence.id).limit(5000))]


def pick(pool, interests: list[str], k: int, skip: set[int], r: random.Random) -> list[tuple[int, int]]:
    """k (occurrence, event) pairs, events they like first, never twice the same event or one in `skip`."""
    liked = [(oid, eid) for oid, eid, cats in pool if eid not in skip and set(cats) & set(interests)]
    rest = [(oid, eid) for oid, eid, cats in pool if eid not in skip and not set(cats) & set(interests)]
    r.shuffle(liked)
    r.shuffle(rest)
    out = []
    for oid, eid in liked + rest:
        if len(out) == k:
            break
        if eid not in skip:
            out.append((oid, eid))
            skip.add(eid)
    return out


def ensure_attendance(db: Session, users: list[User], now: datetime) -> None:
    """1-3 events been to and 1-3 going to, from the catalogue (not the Syrenka Users events)."""
    pools = {True: catalogue(db, now, past=True), False: catalogue(db, now, past=False)}
    for i, u in enumerate(users):
        rows = db.execute(
            select(Attendance, Occurrence)
            .join(Occurrence, Occurrence.id == Attendance.occurrence_id)
            .join(Event, Event.id == Occurrence.event_id)
            .join(Source, Source.id == Event.source_id)
            .where(Attendance.user_id == u.id, Source.slug != SOURCE_SLUG)
            .order_by(Occurrence.starts_at.desc())
        ).all()
        mine = {o.event_id for _, o in rows}  # one date per event
        for past in (True, False):
            have = [(a, o) for a, o in rows if ((o.ends_at or o.starts_at) < now) == past]
            for a, _ in have[3:]:  # going-to dates that are now over pile up in "been to": keep the latest 3
                db.delete(a)
            want = rng("count", i, past).randint(1, 3)
            r = rng("pick", i, past, now.date().isoformat())
            for oid, _ in (
                pick(pools[past], u.interests, want - len(have), mine, r) if len(have) < want else []
            ):
                db.add(
                    Attendance(
                        user_id=u.id,
                        occurrence_id=oid,
                        wants_company=r.random() < 0.6,
                        max_group=r.choice([None, 2, 4]),
                    )
                )
    db.flush()


def next_slot(i: int, hour: int, now: datetime) -> datetime:
    """A date 1-12 days ahead at the event's hour (Warsaw time), stable for a given week."""
    r = rng("when", i, now.isocalendar()[:2])
    day = (now.astimezone(WARSAW) + timedelta(days=r.randint(1, 12))).date()
    return datetime.combine(day, time(hour, r.choice([0, 0, 30])), WARSAW).astimezone(UTC)


def ensure_hosting(db: Session, users: list[User], friends: dict[int, list[int]], now: datetime) -> None:
    for i, u in enumerate(users):
        title, etype, venue, lat, lng, hour, about = HOSTING[i]
        ue = db.scalar(
            select(UserEvent)
            .where(UserEvent.host_user_id == u.id, UserEvent.title == title, UserEvent.status == "active")
            .order_by(UserEvent.id.desc())
        )
        if ue is None:
            starts = next_slot(i, hour, now)
            ue = UserEvent(
                host_user_id=u.id,
                title=title,
                description=about,
                event_type=etype,
                category=EVENT_TYPES[etype],
                audience="public_confirm",
                starts_at=starts,
                ends_at=starts + timedelta(hours=2),
                lat=lat,
                lng=lng,
                venue_name=venue,
                address="Warszawa",
                invited_user_ids=[],
            )
            ue.host = u
            db.add(ue)
            db.flush()
            publish(db, ue)
        elif (ue.ends_at or ue.starts_at) < now:  # it happened: same invitation, new date
            starts = next_slot(i, hour, now)
            ue.starts_at, ue.ends_at = starts, starts + timedelta(hours=2)
            if ue.event_id:
                for o in db.scalars(select(Occurrence).where(Occurrence.event_id == ue.event_id)):
                    o.starts_at, o.ends_at = ue.starts_at, ue.ends_at
        db.flush()
        occ = (
            db.scalar(select(Occurrence.id).where(Occurrence.event_id == ue.event_id))
            if ue.event_id
            else None
        )
        if occ is None:
            continue
        # some friends asked to join; the host said yes to some of them
        r = rng("join", i)
        mates = friends[u.id][:]
        r.shuffle(mates)
        asked = mates[: max(2, round(len(mates) * r.uniform(0.3, 0.7)))]
        yes = r.randint(1, max(1, len(asked) - 1))  # at least one approved, usually someone still waiting
        for k, fid in enumerate(asked):
            jr = db.scalar(
                select(JoinRequest).where(
                    JoinRequest.occurrence_id == occ,
                    JoinRequest.target_user_id == u.id,
                    JoinRequest.requester_id == fid,
                )
            )
            if jr is None:
                db.add(
                    JoinRequest(
                        occurrence_id=occ,
                        target_user_id=u.id,
                        requester_id=fid,
                        message=r.choice(ASK),
                        status="accepted" if k < yes else "pending",
                    )
                )
    db.flush()


def run(db: Session) -> dict:
    now = datetime.now(UTC)
    users = ensure_people(db, now)
    ensure_friends(db, users, now)
    ids = {u.id for u in users}
    friends: dict[int, list[int]] = {u.id: [] for u in users}
    for a, b in db.execute(
        select(Friendship.requester_id, Friendship.addressee_id).where(
            Friendship.status == "accepted",
            Friendship.requester_id.in_(ids),
            Friendship.addressee_id.in_(ids),
        )
    ):
        friends[a].append(b)
        friends[b].append(a)
    ensure_attendance(db, users, now)
    ensure_hosting(db, users, friends, now)
    db.commit()
    degrees = [len(v) for v in friends.values()]
    return {
        "people": len(users),
        "friendships": sum(degrees) // 2,
        "friends_min": min(degrees),
        "friends_max": max(degrees),
    }


def main() -> int:
    from app.config import settings

    if settings.app_env == "prod":
        print("mocksocial: skipped on prod")
        return 0
    with SessionLocal() as db:
        print("mocksocial:", run(db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
