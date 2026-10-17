## What

<!-- One or two sentences. Link the issue: Closes #12 -->

## Area

- [ ] Fetchers (`backend/app/ingest/sources/`)
- [ ] Backend / API / DB (`backend/`)
- [ ] UI (`frontend/`)
- [ ] Repo / CI (`.github/`)

## How I tested

<!-- e.g. "uv run pytest", "opened /docs and called GET /events", screenshot of the UI -->

## Checklist

- [ ] No secrets, tokens, `.env`, `apiKey.txt` or `*.db` files in the diff
- [ ] New source? Added `backend/tests/fixtures/<slug>.json` and registered it in `sources/__init__.py`
- [ ] Changed models? Ran `uv run alembic revision --autogenerate -m "..."` and committed the migration
