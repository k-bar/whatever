# backend/db — skrypty eksploracyjne i lokalne bazy SQLite

Skrypty Mateusza, które pobierają dane do lokalnych baz SQLite (do przeglądania i analizy).
Używają tylko biblioteki standardowej Pythona i zapisują bazy obok siebie. Bazy `*.db`
są w `.gitignore` i nie trafiają do repozytorium.

**Aplikacja z nich nie korzysta.** Dane na mapie (syrenka.me) ładuje `backend/app/ingest/`
prosto do Postgresa, co godzinę:

| Skrypt tutaj | Odpowiednik w aplikacji |
|---|---|
| ~~`fetch_data.py`~~ (usunięty) | `app/ingest/sources/warsaw_open_data.py` (wydarzenia, zajęcia sportowe, boiska) |
| `fetch_streets_gl.py` | `app/ingest/sources/osm_venues.py` (miejsca z OpenStreetMap) |
| `fetch_kupbilecik.py` | brak: kupbilecik.pl blokuje automaty (HTTP 403), czekamy na ich API |
| `create_users_db.py` | brak: użytkownicy są w Postgresie (`app/models.py`, migracje Alembic) |

Nowe źródło danych dodaje się w `backend/app/ingest/sources/` (patrz `CONTRIBUTING.md`).

## Struktura

```
backend/db/
├── db.md                    # ten plik
├── fetch_kupbilecik.py      # kupbilecik.pl   -> kup_bilecik.db
├── fetch_streets_gl.py      # OpenStreetMap   -> street_gl.db
├── create_users_db.py       # przykładowi użytkownicy -> users.db
└── *.db                     # lokalne bazy (gitignored)
```

## Bazy

| Plik | Źródło | Tabele (liczba wierszy) |
|---|---|---|
| `events.db` (stara migawka) | [dane.um.warszawa.pl](https://dane.um.warszawa.pl) — Kalendarz wydarzeń | `events` (650), `event_occurrences` (2231), `event_addresses` (491), `event_locations` (384) |
| `sport.db` (stara migawka) | dane.um.warszawa.pl — Zajęcia sportowe, Otwarte boiska | `sport_classes` (592), `sport_class_dates` (1253), `sport_class_addresses` (488), `open_pitches` (1227) |
| `kup_bilecik.db` | [kupbilecik.pl](https://www.kupbilecik.pl) — bilety na wydarzenia w całej Polsce | `events` (4637) |
| `street_gl.db` | OpenStreetMap (Overpass API) — dane wyświetlane przez [streets.gl](https://streets.gl) | `venues` (447) |

Liczby wierszy według stanu z 17.10.2026. `events.db` i `sport.db` pochodzą z usuniętego `fetch_data.py`;
aktualne dane są w Postgresie (schemat `dev` lub `public`).

### events.db

- `events` — jedno wydarzenie: `title`, `kiedy`, `gdzie`, `data` (YYYY-MM-DD), `czas`,
  adres (`place_name`, `street`, `postcode`, `district`, `full_address`), współrzędne (`lat`, `lon`),
  pola pomocnicze (`is_recurring`, `is_all_day`, `time_of_day`, `weekdays`, `is_finished`, ...) i `raw_json`.
- `event_occurrences` — wszystkie terminy wydarzenia (`event_id` → `events.id`).
- `event_addresses` — miejsca wydarzenia.
- `event_locations` — punkty na mapie z dzielnicą.

### sport.db

- `sport_classes` — zajęcia sportowe: `title`, `time`, `days`, `districts`, `categories`, ...
- `sport_class_dates` — daty zajęć (`class_id` → `sport_classes.id`).
- `sport_class_addresses` — miejsca zajęć.
- `open_pitches` — otwarte boiska szkolne: adres, dzielnica, nawierzchnia, wyposażenie, godziny dla każdego dnia tygodnia.

### kup_bilecik.db — tabela `events`

Jeden wiersz = jeden spektakl/koncert (jedna data w jednym miejscu); `id` to numer wydarzenia z URL.

| Kolumna | Opis |
|---|---|
| `name` | nazwa wydarzenia |
| `date`, `time` | początek: `YYYY-MM-DD`, `HH:MM` |
| `end_date`, `end_time` | koniec |
| `location` | nazwa miejsca (sala, teatr, klub) |
| `address`, `city`, `postcode`, `region` | adres, `region` = województwo |
| `category` | kategoria z serwisu (teatr, muzyka, kabaret, ...) |
| `event_type` | typ schema.org (`TheaterEvent`, `MusicEvent`, ...) |
| `price`, `currency` | cena od |
| `availability` | `InStock`, `SoldOut`, ... |
| `status` | `EventScheduled`, `EventCancelled`, ... |
| `url`, `image_url`, `description`, `scraped_at` | |

Uwaga: obecne dane obejmują 17.10–22.11.2026, a `category` jest puste. Serwis zablokował
pobieranie (HTTP 403) w połowie — patrz „Odświeżanie danych”.

### street_gl.db — tabela `venues`

streets.gl to trójwymiarowa mapa OpenStreetMap i nie ma własnych wydarzeń, więc baza zawiera
**miejsca**, w których odbywają się wydarzenia (Warszawa). OSM nie przechowuje dat wydarzeń.

| Kolumna | Opis |
|---|---|
| `id` | `node/…`, `way/…` lub `relation/…` |
| `name` | nazwa miejsca |
| `category` | `museum`, `arts_centre`, `theatre`, `nightclub`, `gallery`, `cinema`, `events_venue`, `stadium`, `conference_centre`, `exhibition_centre` |
| `location` | pełny adres, np. „Chmielna 33, 00-021 Warszawa” |
| `street`, `housenumber`, `postcode`, `city` | części adresu |
| `lat`, `lon` | współrzędne (zawsze wypełnione) |
| `time` | godziny otwarcia w formacie OSM, np. `Tu-Su 10:00-18:00` |
| `website`, `phone`, `email`, `wheelchair`, `capacity` | |
| `osm_url`, `streets_gl_url` | link do OSM i do widoku 3D w streets.gl |
| `tags_json` | wszystkie tagi OSM |

## Odświeżanie danych

Uruchamiaj z folderu `backend/db`:

```bash
# kup_bilecik.db — pełne pobieranie (~2 s na stronę)
python fetch_kupbilecik.py
# po blokadzie (HTTP 403) odczekaj ok. godzinę i wznów od strony, którą poda skrypt:
python fetch_kupbilecik.py --listings search theatre concerts cabarets standup impro sport kids festivals other --start-page 236

# street_gl.db — miejsca z OpenStreetMap
python fetch_streets_gl.py                     # Warszawa
python fetch_streets_gl.py --city "Kraków"
```

Ponowne uruchomienie aktualizuje istniejące wiersze, nie tworzy duplikatów.

## Przykładowe zapytania

```sql
-- kup_bilecik.db: wydarzenia w Warszawie w najbliższym tygodniu
SELECT name, date, time, location
FROM events
WHERE city = 'Warszawa' AND date BETWEEN date('now') AND date('now', '+7 days')
ORDER BY date, time;

-- street_gl.db: teatry z godzinami otwarcia
SELECT name, location, time FROM venues WHERE category = 'theatre' AND time IS NOT NULL;
```
