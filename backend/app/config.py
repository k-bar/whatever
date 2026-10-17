from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres@localhost:54329/warszawa"
    jwt_secret: str = "dev-only-insecure-secret-change-me-in-prod"  # Render generates the real one
    jwt_expire_days: int = 7
    cors_origins: list[str] = ["*"]
    warsaw_api_token: str | None = None
    nominatim_user_agent: str = "warszawa-live-hackathon (github.com/k-bar/whatever)"

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, v: str) -> str:
        # Render hands out postgres:// URLs; SQLAlchemy needs an explicit driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix) :]
        return v


settings = Settings()
