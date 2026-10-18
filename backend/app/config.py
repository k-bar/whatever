import json
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def read_secret(arn: str) -> str:
    import boto3  # only needed on AWS (EC2 boxes use their instance role)

    return boto3.client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres@localhost:54329/warszawa"
    jwt_secret: str = "dev-only-insecure-secret-change-me-in-prod"
    jwt_expire_days: int = 7
    cors_origins: list[str] = ["*"]
    warsaw_api_token: str | None = None
    # dane.um.warszawa.pl drops connections from AWS IPs, so the boxes go through an HTTP relay
    # with a Polish IP (X-Relay-Target protocol). Unset = call the API directly.
    warsaw_relay_url: str | None = None
    warsaw_relay_token: str | None = None
    # Offline PL -> EN model for event titles/descriptions (app/translate.py); downloaded by deploy/deploy.sh.
    translation_model_dir: str = "/opt/warszawa/models/translate-pl_en-1_9"
    nominatim_user_agent: str = "warszawa-live-hackathon (github.com/k-bar/whatever)"
    db_pool_size: int = 5
    # Postgres schema for this environment ("dev" on the dev box). Tables live there;
    # PostGIS types stay in public, so the search_path is "<schema>, public".
    db_schema: str | None = None
    app_env: str = "local"  # local / dev / prod
    git_sha: str = "unknown"  # set by deploy/deploy.sh

    # Mail (app/mail.py): Amazon SES on the boxes (their instance role may send as syrenka.me);
    # locally, and whenever mail_backend is "log", mails are logged and kept in app.mail.outbox.
    mail_backend: str | None = None  # "ses" / "log"; unset = ses on dev/prod, log elsewhere
    mail_from: str = "Syrenka <no-reply@syrenka.me>"
    ses_region: str = "eu-north-1"
    # Site that links in mails open (?verify=… / ?reset=…); unset = deploy/environments.json for app_env
    web_url: str | None = None
    verify_token_hours: int = 48
    reset_token_minutes: int = 60
    mail_resend_seconds: int = 60  # one verification / reset mail per account per minute
    # True: friends, creating events, join requests and chat need a confirmed email (get_verified_user).
    # Off while SES is in sandbox (mail only reaches verified addresses): links are still mailed.
    require_verified_email: bool = False
    login_max_failures: int = 10  # wrong passwords in a row before the account is locked for a while
    login_lock_minutes: int = 15

    # On AWS the values above come from Secrets Manager (set by infra/).
    db_secret_arn: str | None = None  # RDS-generated JSON: username, password, host, port, dbname
    jwt_secret_arn: str | None = None
    warsaw_api_token_secret_arn: str | None = None

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, v: str) -> str:
        # Hosted Postgres hands out postgres:// URLs; SQLAlchemy needs an explicit driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix) :]
        return v

    @field_validator("db_schema")
    @classmethod
    def safe_schema(cls, v: str | None) -> str | None:
        if v and not v.isidentifier():
            raise ValueError("DB_SCHEMA must be a plain identifier")
        return v or None

    @property
    def connect_args(self) -> dict:
        return {"options": f"-csearch_path={self.db_schema},public"} if self.db_schema else {}

    @model_validator(mode="after")
    def defaults_for_env(self) -> "Settings":
        if self.web_url is None:
            envs = Path(__file__).resolve().parents[2] / "deploy" / "environments.json"
            known = json.loads(envs.read_text()) if envs.exists() else {}
            self.web_url = known.get(self.app_env, {}).get("web", "http://localhost:5173")
        if self.mail_backend is None:
            self.mail_backend = "ses" if self.app_env in ("dev", "prod") else "log"
        return self

    @model_validator(mode="after")
    def load_aws_secrets(self) -> "Settings":
        if self.db_secret_arn:
            s = json.loads(read_secret(self.db_secret_arn))
            self.database_url = (
                f"postgresql+psycopg://{quote_plus(s['username'])}:{quote_plus(s['password'])}"
                f"@{s['host']}:{s['port']}/{s.get('dbname', 'warszawa')}?sslmode=require"
            )
        if self.jwt_secret_arn:
            self.jwt_secret = read_secret(self.jwt_secret_arn)
        if self.warsaw_api_token_secret_arn:
            # Plain token, or JSON {"token", "relay_url", "relay_token"}
            raw = read_secret(self.warsaw_api_token_secret_arn).strip()
            s = json.loads(raw) if raw.startswith("{") else {"token": raw}
            token = (s.get("token") or "").strip()
            self.warsaw_api_token = token if token and token != "CHANGE_ME" else None
            self.warsaw_relay_url = s.get("relay_url") or self.warsaw_relay_url
            self.warsaw_relay_token = s.get("relay_token") or self.warsaw_relay_token
        return self


settings = Settings()
