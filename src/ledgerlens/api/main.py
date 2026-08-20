"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from ledgerlens import __version__
from ledgerlens.api.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ledgerlens",
        description="Invoice and receipt intelligence: field extraction from PDFs, an accounting validation-rules engine, and policy RAG Q&A with cited answers.",
        version=__version__,
    )
    app.include_router(router)
    return app


app = create_app()
