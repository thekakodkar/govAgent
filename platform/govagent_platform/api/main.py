"""ASGI factory. No CORS middleware is installed."""

from __future__ import annotations

from fastapi import FastAPI

from govagent_platform import __version__
from govagent_platform.api.platform_admin import router as platform_router
from govagent_platform.api.runtime import router as runtime_router
from govagent_platform.api.tenant_admin import router as tenant_router
from govagent_platform.config import get_settings


def create_app() -> FastAPI:
    get_settings(require_secret=True)
    app = FastAPI(title="govagent-platform", version=__version__)
    app.include_router(platform_router)
    app.include_router(tenant_router)
    app.include_router(runtime_router)
    return app
