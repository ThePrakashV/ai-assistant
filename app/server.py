import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api.web_routes import router
from app.core.config import settings
from app.runtime import runtime

# Windows registry la sila file types ku thappa MIME irukkalam ("text/plain").
# nosniff irukkaradhaala browser adhai reject pannum. Namma thaane sariyaa solrom.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/manifest+json", ".webmanifest")

STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"

# Inline script / style illa, so strict CSP podalam (XSS risk kammi)
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "media-src 'self' blob:; connect-src 'self' ws: wss:; worker-src 'self'; "
    "manifest-src 'self'; base-uri 'none'; frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.api_token:
        print("[Server] API_TOKEN set illa. localhost mattum use pannu (LAN ku token kandippa venum).")
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title=f"{settings.assistant_name} Server", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


app.include_router(router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")