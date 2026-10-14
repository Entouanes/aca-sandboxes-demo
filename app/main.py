import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt

from app.manager import Manager

WEB = Path(__file__).resolve().parent.parent / "web"


class LaunchRequest(BaseModel):
    count: Annotated[StrictInt, Field(ge=1, le=50)] = 12


def create_app(manager: Manager, key: str, mode: str = "azure") -> FastAPI:
    if not key:
        raise ValueError("DEMO_API_KEY is required; the control API must not be public.")

    @asynccontextmanager
    async def lifespan(app):
        manager.start_monitor()
        yield
        manager.close()

    app = FastAPI(title="Sandbox Launchpad", lifespan=lifespan, docs_url=None, redoc_url=None)

    def authorize(x_demo_key: Annotated[str | None, Header()] = None):
        if x_demo_key is None or not hmac.compare_digest(x_demo_key, key):
            raise HTTPException(status_code=401, detail="Enter the presenter access key.")

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/api/sandboxes", dependencies=[Depends(authorize)])
    def status():
        manager.observe()
        return {**manager.snapshot(), "mode": mode}

    @app.post("/api/sandboxes", status_code=202, dependencies=[Depends(authorize)])
    def launch(request: LaunchRequest):
        try:
            return {**manager.start(request.count), "mode": mode}
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.delete("/api/sandboxes", dependencies=[Depends(authorize)])
    def cleanup():
        try:
            return {**manager.cleanup(), "mode": mode}
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=f"Cleanup incomplete: {error}") from error

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app


def build_app() -> FastAPI:
    from app.providers import AzureProvider, SimulationProvider

    mode = os.getenv("DEMO_MODE", "azure")
    if mode not in ("azure", "simulation"):
        raise ValueError("DEMO_MODE must be azure or simulation.")
    provider = SimulationProvider() if mode == "simulation" else AzureProvider()
    return create_app(
        Manager(provider, limit=int(os.getenv("MAX_SANDBOXES", "50"))),
        key=os.environ["DEMO_API_KEY"],
        mode=mode,
    )
