from fastapi import FastAPI
from app.errors import register_error_handlers
from app.routes import chat, documents, health


def create_app() -> FastAPI:
    app = FastAPI(title="MC Club Assistant")
    register_error_handlers(app)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    return app


app = create_app()
