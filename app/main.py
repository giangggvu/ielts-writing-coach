import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import db
from app.config import get_settings
from app.routers import auth, essays, pages

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if db._engine is None:
        db.init_engine(get_settings().database_url)
    yield
    if db._engine is not None:
        await db._engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="IELTS Writing Coach",
        description="Estimated IELTS Writing Task 2 bands and feedback. "
        "Scores are estimates only and do not replace an IELTS examiner.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(auth.router)
    app.include_router(essays.router)
    app.include_router(pages.router)
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).resolve().parent / "static"),
        name="static",
    )

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
