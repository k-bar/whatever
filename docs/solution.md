# Opis rozwiązania — Syrenka (Warszawa Live)

**Dokumentacja rozwiązania na potrzeby Hackatonu**  
Stan opisu: 18 października 2026 r.  
Projekt: Syrenka (Warszawa Live)

## 1. Cel i zakres

Syrenka to aplikacja internetowa, której celem jest ułatwienie odkrywania wydarzeń i miejsc w Warszawie. Łączy dane z kilku źródeł na interaktywnej mapie, pozwala filtrować wydarzenia według czasu i kategorii, a także wspiera znalezienie osób, które chcą wziąć w nich udział.

Rozwiązanie obejmuje:

- mapę wydarzeń, zajęć sportowych, wybranych miejsc, lokali i obiektów miejskich;
- wyszukiwanie i filtrowanie dostępnych danych;
- konta i profile użytkowników, listę znajomych oraz ulubione;
- deklarowanie udziału w wydarzeniu, informację o szukaniu towarzystwa i prośby o dołączenie;
- tworzenie wydarzeń przez użytkowników;
- warstwę API i cykliczne pobieranie danych źródłowych.

Zakres odpowiada wersji MVP opisanej w [planie projektu](PLAN.md). Funkcje widoczne w planie nie muszą być wszystkie jednakowo kompletne. Dostępność konkretnych endpointów i funkcji interfejsu opisują [API](api.md) oraz [dokumentacja frontendu](frontend.md). W repozytorium są środowiska produkcyjne i deweloperskie; dokumentacja architektury wskazuje, że produkcja może działać na starszej wersji niż aktualny kod gałęzi `dev`.

## 2. Założenia projektowe

- Aplikacja koncentruje się na Warszawie i pokazuje dane przestrzenne na mapie.
- Dane z różnych źródeł są sprowadzane do wspólnego modelu wydarzeń, miejsc i wystąpień wydarzeń, z zachowaniem identyfikatora źródła i danych źródłowych.
- Zakres danych zależy od dostępności i jakości zewnętrznych źródeł. Brak rekordu w aplikacji nie oznacza, że wydarzenie nie odbywa się.
- Powtarzające się pobrania aktualizują rekordy, a wpisy znikające ze źródeł mogą być oznaczane jako nieaktywne. Historia zakończonych wystąpień jest zachowywana.
- Brak współrzędnych może uruchomić geokodowanie przez Nominatim; rekordy poza granicą Warszawy są odrzucane w głównym potoku.
- Wyszukiwanie w języku naturalnym jest oparte na regułach i dostępnych danych, a nie na zewnętrznym modelu językowym. Wyniki zależą od opisów i kategorii dostarczonych przez źródła.
- Dane miejskie są przetwarzane w dwóch równoległych potokach: głównym potoku backendu oraz synchronizatorze zapisującym surowe dane do osobnych tabel. API wykorzystuje głównie tabele głównego potoku; z synchronizatora korzysta m.in. przy trasach turystycznych. To aktualny stan implementacji, a nie założenie o docelowym uproszczeniu architektury.
- Dane od użytkowników (np. profil, deklaracja udziału lub własne wydarzenie) są odrębne od danych pobranych z miejskich i zewnętrznych źródeł.

## 3. Wykorzystane dane

### 3.1. Dane miejskie Warszawy

Podstawowym źródłem miejskim jest [Warszawski Serwis Otwartych Danych](https://dane.um.warszawa.pl/). Kod korzysta m.in. z następujących zbiorów/interfejsów API:

| Dane | Przykładowe zastosowanie |
|---|---|
| Kalendarz wydarzeń (`get_bmm_kalendarz_wydarzen`) | Wydarzenia miejskie prezentowane na mapie |
| Zajęcia sportowe (`get_bmm_zajecia_sportowe`) | Zajęcia i aktywności sportowe |
| Otwarte boiska (`get_be_otwarte_boiska`) | Lokalizacje obiektów sportowych i godziny otwarcia |
| Toalety (`get_m_toalety`) | Miejskie punkty użyteczności publicznej |
| Defibrylatory AED (`get_scb_lokalizacja_defibrylatorow`) | Lokalizacje urządzeń AED |
| Pogoda (`get_zom_pogoda`) | Bieżące odczyty ze stacji pogodowych |
| Jakość powietrza (`get_bopipk_monitoring_jakosci_powietrza`) | Odczyty ze stacji monitoringu powietrza |
| Trasy turystyczne (`get_sbt_trasy_turystyczne`) | Trasy i punkty turystyczne |

### 3.2. Pozostałe źródła

- **OpenStreetMap** przez usługę Overpass: obiekty i lokale, w tym miejsca kultury, rozrywki, gastronomii i wybrane przystanki. Dane OSM mają oznaczenie źródła w aplikacji; szczegóły wymaganych atrybucji i warunków użycia należy zachować przy publikacji danych i map.
- **Songkick**: wybrane koncerty i wydarzenia muzyczne w Warszawie.
- **Waw4Free**: wybrane bezpłatne wydarzenia, koncerty i imprezy.
- **Nominatim**: geokodowanie części lokalizacji, gdy źródło nie dostarcza współrzędnych.
- **Dane użytkowników**: profile, relacje, deklaracje obecności i wydarzenia tworzone w aplikacji.

Każde źródło może mieć własne warunki ponownego wykorzystania, atrybucji, częstotliwości pobierania i prezentacji. Przed publicznym zgłoszeniem lub dalszą dystrybucją należy sprawdzić aktualne warunki właściwe dla każdego źródła oraz wymagane oznaczenia. Dokumentacja kodu identyfikuje źródła, ale sama w sobie nie stanowi potwierdzenia zgodności prawnej ani licencji dla każdego zbioru.

Szczegółowe nazwy, harmonogramy i sposób zapisu źródeł opisuje [dokumentacja danych](data.md). Dane pochodzące z otwartych źródeł mogą być niepełne, nieaktualne lub błędnie opisane. Projekt nie gwarantuje ich kompletności.

## 4. Przetwarzanie danych i architektura

1. Moduły pobierające odpytują źródła według skonfigurowanych harmonogramów.
2. Parsery normalizują rekordy do wspólnego formatu. Mapowane są m.in. tytuł, opis, kategoria, lokalizacja, termin i klucz źródłowy.
3. Backend zapisuje dane w PostgreSQL z rozszerzeniem PostGIS. Wykonuje aktualizacje istniejących rekordów, geokoduje wybrane lokalizacje i filtruje dane przestrzenne.
4. Wybrane polskie tytuły i opisy są tłumaczone na angielski lokalnym modelem Argos/OPUS-MT. Tłumaczenie nie jest zewnętrznym chatbotem.
5. API udostępnia dane aplikacji internetowej, a frontend pokazuje je na mapie i w widokach użytkownika.

Projekt ma dwa potoki ingestii danych miejskich, co może powodować powielone pobieranie niektórych zbiorów. Główny backend zapisuje znormalizowane rekordy używane przez API. Osobny synchronizator zachowuje surowe tabele i historię niektórych pomiarów. Pomocnicze skrypty i migawki SQLite w `backend/db/` są narzędziami eksploracyjnymi i referencyjnymi, nie produkcyjnym magazynem danych aplikacji.

## 5. Technologie i narzędzia

| Obszar | Wykorzystane technologie |
|---|---|
| Frontend | React 18, JavaScript, Vite, MapLibre GL, Framer Motion, React Day Picker |
| Backend API | Python 3.11+, FastAPI, Uvicorn, Pydantic Settings |
| Baza danych | PostgreSQL 16, PostGIS, SQLAlchemy 2, GeoAlchemy2, Alembic |
| Pobieranie i przetwarzanie danych | Python, `requests`/`httpx`, parsery źródeł, Shapely, Nominatim, OpenStreetMap Overpass |
| Tłumaczenie | Argos/OPUS-MT uruchamiany lokalnie przez CTranslate2 i SentencePiece |
| Infrastruktura i wdrożenie | AWS CDK (Python), EC2, RDS, S3, CloudFront, Route 53, AWS Secrets Manager, systemd |
| Jakość i automatyzacja | pytest, Ruff, GitHub Actions, npm |

Konfiguracja i szczegóły wdrożenia opisane są w [dokumentacji architektury](architecture.md) i [operacyjnej](operations.md). Repozytorium zawiera również moduł synchronizatora danych oraz lokalne skrypty pomocnicze.

## 6. Wykorzystanie narzędzi sztucznej inteligencji

Podczas przygotowania rozwiązania wykorzystywano narzędzia AI wskazane przez Zespół: **Claude Code, GitHub Copilot oraz Antigravity**. Zgodnie z deklarowanym zakresem narzędzia te wspomagały powstawanie rozwiązania, w szczególności pracę nad kodem, treścią dokumentacji i materiałami graficznymi. W kodzie aplikacji wyszukiwanie asystowane opisane w API działa deterministycznie na podstawie reguł; nie wysyła zapytań do modelu językowego. Automatyczne tłumaczenie treści wydarzeń korzysta z lokalnego modelu Argos/OPUS-MT.

Wygenerowane lub zasugerowane przez narzędzia AI elementy zostały użyte jako wsparcie pracy Zespołu. Zespół weryfikuje ich poprawność i ponosi pełną odpowiedzialność za zgodność rozwiązania, treści i grafik z obowiązującym prawem, regulaminem Hackatonu oraz prawami osób trzecich, w tym prawami autorskimi i licencjami danych. W szczególności Zespół odpowiada za sprawdzenie praw do wykorzystanych danych i grafik oraz prawidłowe oznaczenie ich źródeł.

## 7. Ograniczenia

- Aplikacja prezentuje dane, które udało się pobrać i znormalizować; dostępność zależy od źródeł zewnętrznych i ich aktualności.
- Współrzędne, daty i kategorie mogą wymagać weryfikacji; geokodowanie nie gwarantuje poprawnej lokalizacji.
- Potoki danych częściowo się pokrywają, a implementacja w środowisku produkcyjnym może nie odpowiadać najnowszemu stanowi gałęzi deweloperskiej.
- Regułowe wyszukiwanie rozpoznaje obsługiwane pojęcia i aliasy, nie dowolne sformułowania.
- Informacje pogodowe, jakości powietrza, godziny otwarcia i wydarzenia należy traktować jako informacyjne i potwierdzać u organizatora lub właściwego źródła.

## 8. Dokumentacja uzupełniająca

- [Architektura i przepływ danych](architecture.md)
- [Źródła danych i potoki pobierania](data.md)
- [API](api.md)
- [Frontend](frontend.md)
- [Wdrożenie i utrzymanie](operations.md)
- [Założenia produktu](PLAN.md)
