"""AWS Lambda entry points (see infra/).

api:    HTTP requests from the Function URL, plus {"action": "migrate"} to run Alembic.
ingest: EventBridge schedule, or {"source": "warsaw_events", "geocode_limit": 50} by hand.
"""

from pathlib import Path

from mangum import Mangum

from app.main import app

BACKEND = Path(__file__).resolve().parent.parent
_http = Mangum(app, lifespan="off")


def migrate() -> dict:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    return {"migrated": True}


def api(event, context):
    if isinstance(event, dict) and event.get("action") == "migrate":
        return migrate()
    return _http(event, context)


def ingest(event, context):
    from app.ingest.run import main

    event = event if isinstance(event, dict) else {}
    argv = ["--geocode-limit", str(event.get("geocode_limit", 200))]
    if event.get("source") and event["source"] != "aws.events":  # scheduler events carry source=aws.events
        argv += ["--source", event["source"]]
    status = main(argv)
    if status:
        raise RuntimeError("one or more sources failed; see logs and GET /sources")
    return {"ok": True}
