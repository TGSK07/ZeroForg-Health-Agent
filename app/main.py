from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings
from app.monitoring.scheduler import Agent

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background agent with the web app and stop it on shutdown."""
    agent = Agent()
    agent.start()
    app.state.agent = agent
    yield
    agent.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")


@app.get("/", include_in_schema=False)
def root():
    """Send visitors to the dashboard."""
    return RedirectResponse("/dashboard/")
