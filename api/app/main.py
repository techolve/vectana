import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app import __version__
from app.core.config import settings
from app.i18n import request_locale, translate_error, validation_message
from app.routers import auth, eol, org, project

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
app.include_router(eol.router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse | FileResponse:
    """Translate English error details for the caller's language. Covers
    Starlette's own errors too, so unknown web paths get the app's 404 page."""
    if (
        exc.status_code == 404
        and not request.url.path.startswith("/api/")
        and settings.static_dir.is_dir()
    ):
        return FileResponse(settings.static_dir / "404.html", status_code=404)
    detail = exc.detail
    if isinstance(detail, str):
        detail = translate_error(detail, request_locale(request))
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    message = validation_message(list(exc.errors()), request_locale(request))
    return JSONResponse({"detail": message}, status_code=422)


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


# Serve the exported Next.js app. API routes are registered first and win.
if settings.static_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="web")
