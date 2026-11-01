from fastapi import FastAPI

from app.api.monitor_routes import router as monitor_router
from app.core.config import settings

# Docker dashboard ku light app: LLM / FAISS / torch import aagaadhu (image chinna, RAM kammi)
app = FastAPI(title=f"{settings.assistant_name} Monitor")
app.include_router(monitor_router)


@app.get("/")
async def root():
    return {"message": f"{settings.assistant_name} monitor is alive", "dashboard": "/dashboard"}


@app.get("/health")
async def health():
    return {"status": "ok"}