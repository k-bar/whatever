from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.routers import events, map, profiles, social, users
from app.userevents.router import router as userevents_router

app = FastAPI(
    title="Warszawa Live API",
    description="Everything social happening in Warsaw, on one map. Interactive docs: /docs",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(events.router)
app.include_router(users.router)
app.include_router(social.router)
app.include_router(profiles.router)
app.include_router(map.router)
app.include_router(userevents_router)


@app.get("/health", tags=["meta"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "env": settings.app_env, "sha": settings.git_sha}
