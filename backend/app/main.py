import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from app import realtime
from app.assistant.router import router as assistant_router
from app.config import settings
from app.db import engine
from app.routers import chats, events, map, people, profiles, social, users
from app.userevents.router import router as userevents_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    listener = asyncio.create_task(realtime.listen())  # live chat fan-out between workers
    yield
    listener.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await listener


app = FastAPI(
    lifespan=lifespan,
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
app.include_router(people.router)
app.include_router(map.router)
app.include_router(userevents_router)
app.include_router(chats.router)
app.include_router(realtime.router)
app.include_router(assistant_router)


@app.get("/", include_in_schema=False)
def root():
    """The bare API URL opens the interactive docs."""
    return RedirectResponse("/docs")


@app.get("/health", tags=["meta"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "env": settings.app_env, "sha": settings.git_sha}
