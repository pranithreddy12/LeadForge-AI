from __future__ import annotations

from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.v1.router import api_router
from app.core.celery_app import celery as _celery  # noqa: F401  -- registers current_app for @shared_task
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger

configure_logging()
log = get_logger("app")

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=settings.app_env,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", env=settings.app_env, name=settings.app_name)
    yield
    log.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.app_debug,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)

register_error_handlers(app)
app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root():
    return {"name": settings.app_name, "version": "0.1.0", "docs": "/docs"}


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "env": settings.app_env}
