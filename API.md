# Stan implementacji i Plan Zadania (API.md)

## 1. Analiza źródeł danych z `dane.txt`

W pliku `dane.txt` znajduje się 9 wierszy (8 unikalnych usług z portalu Otwarte Dane Warszawy — pozycja 4 i 9 to ten sam zasób AED). Wszystkie endpointy wywoływane są metodą `POST` z nagłówkiem `Authorization: <token>` (klucz z `apiKey.txt`):

| # | Zbiór danych | Endpoint (`POST`) | Struktura odpowiedzi | Strategia zapisu w SQL |
|---|---|---|---|---|
| 1 | **Trasy turystyczne** | `https://dane.um.warszawa.pl/api/action/get_sbt_trasy_turystyczne` | `{"result": [...]}` (9 tras; pola: `title`, `length`, `description`, `traces` JSONB, `tourist_points` JSONB + tabela punktów) | **Upsert** po `title` (oraz punkty po `id_point`) |
| 2 | **Toalety** | `https://dane.um.warszawa.pl/api/action/get_m_toalety` | Lista 695 obiektów GeoJSON (`geometry.coordinates` `[lon, lat]`, `properties`: `zarzadca`, `typ`, `lokalizacja`, `dzielnica`, `dostepnosc`, `platnosc`, `przewijak`, `aktu_dan`, `poch_dan`, `godziny`, `uwagi`) | **Upsert / Replace** po kluczu naturalnym (`lokalizacja`, `lon`, `lat`) |
| 3 | **Pogoda** | `https://dane.um.warszawa.pl/api/action/get_zom_pogoda` | Lista 16 stacji (`lokalizacja`, `lat`, `lon`, `czas`, `temp_pow`, `temp_naw`, `wilg_pow`, `pred_wiatru`, `kier_wiatru`, `int_opadu`) | **Historia (Append / ON CONFLICT DO NOTHING)** po (`lokalizacja`, `czas`) |
| 4 | **Defibrylatory (AED)** | `https://dane.um.warszawa.pl/api/action/get_scb_lokalizacja_defibrylatorow` | Lista 710 obiektów (`geometry.coordinates` `[[lon, lat]]`, `properties`: `defibrillator_id`, `device_*`, `location_*`) | **Upsert** po `defibrillator_id` |
| 5 | **Zajęcia sportowe** | `https://dane.um.warszawa.pl/api/action/get_bmm_zajecia_sportowe` | Lista 592 zajęć (`title`, `url`, `time`, `text`, `language`, `category` JSONB, `day` JSONB, `dedicated` JSONB, `localization` JSONB, `address` JSONB, `image` JSONB) | **Upsert** po `url` |
| 6 | **Otwarte boiska** | `https://dane.um.warszawa.pl/api/action/get_be_otwarte_boiska` | Lista 1227 obiektów (`Dzielnica`, `Adres obiektu`, `Nazwa placówki oświatowej`, `Typ obiektu`, `Boisk uniwersalne zawiera`, `Rodzaj nawierzchni`, trybuny, piłkochwyty, dni tygodnia, `Uwagi`, `Data aktualizacji`) | **Upsert / Replace** po (`nazwa_placowki`, `adres_obiektu`, `typ_obiektu`, `wyposazenie`) |
| 7 | **Kalendarz wydarzeń** | `https://dane.um.warszawa.pl/api/action/get_bmm_kalendarz_wydarzen` | Lista 652 wydarzeń (`title`, `url`, `lead`, `text`, `language`, `category` JSONB, `localization` JSONB, `address` JSONB, `map` JSONB + wyciągnięte `lat`/`lon`/`district`, `occurrence` JSONB) | **Upsert** po `url` |
| 8 | **Monitoring jakości powietrza** | `https://dane.um.warszawa.pl/api/action/get_bopipk_monitoring_jakosci_powietrza` | Lista 141 stacji (`name`, `station`, `station_type`, `owner`, `data_source`, `lat`, `lon`, `address`, `ijp`, `data`: lista pomiarów `param_code`, `param_name`, `time`, `unit`, `value`, `ijp`) | **Upsert** słownika stacji po `name` + **Historia (Append / ON CONFLICT DO NOTHING)** pomiarów po (`station_name`, `param_code`, `measurement_time`) |

---

## 2. Schemat bazy danych PostgreSQL

Projekt wykorzysta **SQLAlchemy 2.0** oraz sterownik **psycopg (v3)** z obsługą typów natywnych PostgreSQL (`JSONB`, `TIMESTAMPTZ`, `DOUBLE PRECISION`, `INSERT ... ON CONFLICT`).

Planowane tabele:
1. `tourist_routes` — trasy turystyczne (`id`, `title` UNIQUE, `length_km`, `description`, `traces` JSONB, `tourist_points` JSONB, `updated_at`)
2. `tourist_points` — punkty turystyczne powiązane z trasami (`id_point` PK, `name`, `city`, `lat`, `lng`, `updated_at`)
3. `toilets` — toalety miejskie (`id` PK, `zarzadca`, `typ`, `lokalizacja`, `dzielnica`, `dostepnosc`, `platnosc`, `przewijak`, `aktu_dan`, `poch_dan`, `godziny`, `uwagi`, `lon`, `lat`, `updated_at`, UNIQUE(`lokalizacja`, `lon`, `lat`))
4. `weather_measurements` — historia pomiarów pogodowych (`id` PK, `lokalizacja`, `lat`, `lon`, `czas` TIMESTAMP, `temp_pow`, `temp_naw`, `wilg_pow`, `pred_wiatru`, `kier_wiatru`, `int_opadu`, `fetched_at`, UNIQUE(`lokalizacja`, `czas`))
5. `defibrillators` — urządzenia AED (`defibrillator_id` PK, `lon`, `lat`, `device_access_description`, `device_availability`, `device_location`, `device_manufacturer`, `device_public_access`, `device_specifications`, `location_building`, `location_city`, `location_description`, `location_object_name`, `location_postcode`, `location_street`, `updated_at`)
6. `sports_activities` — zajęcia sportowe (`id` PK, `url` UNIQUE, `title`, `time`, `text`, `language`, `category` JSONB, `day` JSONB, `dedicated` JSONB, `localization` JSONB, `address` JSONB, `image` JSONB, `updated_at`)
7. `open_sports_fields` — otwarte boiska (`id` PK, `dzielnica`, `adres_obiektu`, `nazwa_placowki`, `typ_obiektu`, `wyposazenie`, `rodzaj_nawierzchni`, `trybuny`, `pilkochwyty`, `poniedzialek`, `wtorek`, `sroda`, `czwartek`, `piatek`, `sobota`, `niedziela`, `uwagi`, `data_aktualizacji`, `updated_at`, UNIQUE(`nazwa_placowki`, `adres_obiektu`, `typ_obiektu`, `wyposazenie`))
8. `city_events` — kalendarz wydarzeń (`id` PK, `url` UNIQUE, `title`, `lead`, `text`, `language`, `district`, `lat`, `lon`, `category` JSONB, `localization` JSONB, `address` JSONB, `map_data` JSONB, `occurrences` JSONB, `image` JSONB, `updated_at`)
9. `air_quality_stations` — stacje pomiarowe jakości powietrza (`name` PK, `station`, `station_type`, `owner`, `data_source`, `lat`, `lon`, `city`, `commune`, `district`, `street`, `zip_code`, `current_ijp_name`, `current_ijp_recommendations`, `updated_at`)
10. `air_quality_measurements` — historia pomiarów jakości powietrza (`id` PK, `station_name` FK, `param_code`, `param_name`, `measurement_time` TIMESTAMP, `value`, `unit`, `ijp_name`, `fetched_at`, UNIQUE(`station_name`, `param_code`, `measurement_time`))
11. `sync_logs` — logi pobrań (`id` PK, `dataset_name`, `status`, `records_processed`, `started_at`, `finished_at`, `error_message`) — realizuje m.in. punkt 7 z `PLAN.md` (*Trust in the data*).

---

## Zakres plików

- `API.md` — plan zadania, zakres plików i dziennik zmian
- `requirements.txt` — zależności Pythona (`requests`, `sqlalchemy`, `psycopg[binary]`, `pytest`, `flake8`, `mypy`)
- `docker-compose.yml` — opcjonalny lokalny kontener PostgreSQL 16 wyłącznie do dewelopmentu lokalnego
- `.gitignore` — zabezpieczenie przed przypadkowym wypchnięciem `apiKey.txt`, `.venv/` oraz cache Pythona
- `src/__init__.py` — pakiet główny
- `src/config.py` — konfiguracja połączenia z bazą PostgreSQL (obsługa `DATABASE_URL` oraz zmiennych pod AWS RDS: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE`) i odczyt klucza API
- `src/models.py` — modele SQLAlchemy 2.0 dla wszystkich 11 tabel PostgreSQL
- `src/api_client.py` — klient HTTP do pobierania danych z 8 endpointów `dane.um.warszawa.pl`
- `src/ingestor.py` — logika transformacji JSON -> modele SQL (upsert dla słowników, append historii dla pomiarów)
- `src/scheduler.py` — harmonogram okresowej synchronizacji: grupa `fast` co 10 minut (`weather`, `air_quality`) oraz grupa `slow` co 2 godziny (pozostałe 6 zbiorów), pętla ciągła (`run_scheduler`) oraz handler `lambda_handler` pod AWS EventBridge + AWS Lambda
- `src/main.py` — punkt wejścia CLI (obsługa flag `--dataset`, `--group {fast,slow}`, `--watch`, `--init-only`)
- `tests/test_ingestor.py` — testy jednostkowe transformacji i zapisu danych
- `tests/test_scheduler.py` — testy jednostkowe harmonogramu (`src/scheduler.py`) oraz konfiguracji AWS RDS

---

## Kroki realizacji

- [x] **Krok 1: Konfiguracja środowiska i modeli bazy danych** — aktualizacja `.gitignore`, utworzenie `requirements.txt`, `docker-compose.yml`, `src/__init__.py`, `src/config.py` oraz `src/models.py` wraz z weryfikacją składni/typów.
- [x] **Krok 2: Klient API Otwartych Danych Warszawy** — implementacja `src/api_client.py` obsługującego 8 endpointów z `dane.txt` i autoryzację kluczem z `apiKey.txt`.
- [x] **Krok 3: Moduł zasilania bazy SQL (Ingestor) oraz CLI** — implementacja `src/ingestor.py` (upsert danych lokalizacyjnych/wydarzeń + historia pomiarów pogody i powietrza) oraz `src/main.py`.
- [x] **Krok 4: Testy jednostkowe i pełna synchronizacja z bazą PostgreSQL** — utworzenie `tests/test_ingestor.py`, uruchomienie testów (`pytest`) oraz wykonanie synchronizacji danych do bazy PostgreSQL.
- [x] **Krok 5: Konfiguracja pod AWS RDS oraz implementacja harmonogramu (`src/scheduler.py`, `src/config.py`, `src/main.py`)** — obsługa zmiennych środowiskowych AWS RDS (`DB_HOST`, `DB_SSLMODE` itd.), harmonogram co 10 min (`weather`, `air_quality`) i co 2h (pozostałe 6 zbiorów), tryb ciągły `--watch`, grupy `--group {fast,slow}` oraz punkt wejścia `lambda_handler` dla AWS EventBridge/Lambda.
- [x] **Krok 6: Testy jednostkowe harmonogramu (`tests/test_scheduler.py`) i weryfikacja** — przetestowanie logiki wyznaczania zadań należnych do uruchomienia, grup `fast`/`slow` oraz konfiguracji połączenia AWS RDS (`pytest`, `flake8`, `mypy`).

---

## Dziennik zmian

- **2026-10-17**: Przeanalizowano wszystkie 8 unikalnych adresów z `dane.txt`, pobrano specyfikacje parametrów i zweryfikowano strukturę odpowiedzi API przy użyciu klucza z `apiKey.txt`. Utworzono plan w `API.md`.
- **2026-10-17 (Krok 1)**: Utworzono `.gitignore`, `requirements.txt`, `docker-compose.yml`, `src/__init__.py`, `src/config.py` oraz `src/models.py`. Zainstalowano pakiety w `.venv`, uruchomiono lokalny kontener PostgreSQL 16 (`warszawa_postgres` na porcie `5432`), utworzono wszystkie 11 tabel w bazie `warszawa_live` oraz zweryfikowano kod narzędziami `flake8` i `mypy` (0 błędów).
- **2026-10-17 (Krok 2)**: Zaimplementowano `src/api_client.py` (`DatasetSpec`, `parse_dane_file`, `WarszawaApiClient`). Dodano obsługę dopasowania prefiksowego dla UUID z `dane.txt` (wiersz 4 ma ucięte końcowe `de8`), normalizację odpowiedzi JSON oraz weryfikację `flake8` i `mypy` (0 błędów).
- **2026-10-17 (Krok 3)**: Zaimplementowano `src/ingestor.py` (transformacje JSON -> SQL, upsert dla danych słownikowych/wydarzeń z deduplikacją w obrębie wsadu, `ON CONFLICT DO NOTHING` dla historii pomiarów pogody i jakości powietrza, logowanie do `sync_logs`) oraz interfejs CLI w `src/main.py`. Zweryfikowano `flake8` i `mypy` (0 błędów w 6 plikach).
- **2026-10-17 (Krok 4)**: Utworzono `tests/test_ingestor.py`. Zweryfikowano całość projektu narzędziami `flake8 src tests` (0 błędów), `mypy src tests` (0 błędów w 7 plikach) oraz `pytest -v` (4/4 testy zaliczone). Uruchomiono pełną synchronizację `python -m src.main` — pobrano i zapisano do bazy PostgreSQL wszystkie 8 zbiorów danych z `dane.txt`.
- **2026-10-17 (Aktualizacja planu — Harmonogram i AWS)**: Zaktualizowano plan o **Krok 5** i **Krok 6** — wbudowany harmonogram Pythona (10 min dla pogody/powietrza, 2h dla pozostałych) oraz bezpośrednie wsparcie dla zarządzanej bazy PostgreSQL w AWS (Amazon RDS) i wywołań cyklicznych (tryb `--watch` dla EC2/ECS lub `--group fast|slow` / `lambda_handler` dla AWS EventBridge + Lambda).
- **2026-10-17 (Krok 5)**: Rozszerzono `src/config.py` o obsługę zmiennych środowiskowych AWS RDS (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE`), utworzono `src/scheduler.py` (`DatasetScheduler`, `get_specs_for_group`, `lambda_handler`) oraz dodano flagi `--watch` i `--group` w `src/main.py`. Zweryfikowano `flake8`, `mypy` (0 błędów w 8 plikach) oraz synchronizację grupy `fast`.
- **2026-10-17 (Krok 6)**: Utworzono `tests/test_scheduler.py`. Zweryfikowano cały projekt: `flake8 src tests` (0 błędów), `mypy src tests` (0 błędów w 9 plikach) oraz `pytest -v` (7/7 testów zaliczonych).
