from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
import os

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(title="Polymarket Weather Bot")

    from dashboard.routes.index import router as index_router
    from dashboard.routes.health import router as health_router
    from dashboard.routes.trades import router as trades_router
    from dashboard.routes.analytics_routes import router as analytics_router
    from dashboard.routes.wallets import router as wallets_router

    app.include_router(index_router)
    app.include_router(health_router)
    app.include_router(trades_router)
    app.include_router(analytics_router)
    app.include_router(wallets_router)

    return app
