import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.core.config import settings
from app.routers import auth, org, project

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

logger = logging.getLogger("vectana")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    if settings.secret_key == "change-me-in-production" and not settings.debug:
        raise RuntimeError("Set SECRET_KEY (openssl rand -hex 32) before starting Vectana")
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version=__version__,
    description="Project dependency vulnerability monitoring",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(org.router)
app.include_router(project.router)


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


# Serve the exported Next.js app. API routes are registered first and win.
if settings.static_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="web")

    @app.exception_handler(404)
    async def not_found(request: Request, exc: HTTPException) -> FileResponse | JSONResponse:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=404)
        return FileResponse(settings.static_dir / "404.html", status_code=404)
