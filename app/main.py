from fastapi import FastAPI

from app.api.monitor_routes import router as monitor_router
from app.api.routes import router
from app.core.config import settings

app = FastAPI(title=f"{settings.assistant_name} - Personal AI Assistant")
app.include_router(router)
app.include_router(monitor_router)


@app.get("/")
async def root():
    return {"message": f"{settings.assistant_name} is alive", "dashboard": "/dashboard"}