from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os

# Importera routers
from api.routers import status
from api.routers import ai_agent
from api.routers import metrics
from api.routers import user_settings
from api.routers import ventilation

# Konfigurera appen
app = FastAPI(
    title="Nibe Autotuner API",
    description="API för styrning och övervakning av Nibe värmepump",
    version="2.0.0"
)

# CORS-inställningar
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inkludera routers
# Status ligger på /api/status
app.include_router(status.router, prefix="/api")

# AI Agent endpoints
app.include_router(ai_agent.router, prefix="/api/ai-agent", tags=["AI Agent"])

# Metrics endpoints (/api/metrics, /api/performance-score, etc)
app.include_router(metrics.router, prefix="/api", tags=["Metrics"])

# User settings endpoints
app.include_router(user_settings.router, prefix="/api/settings", tags=["Settings"])

# Ventilation endpoints
app.include_router(ventilation.router, prefix="/api/ventilation", tags=["Ventilation"])

@app.get("/")
def root():
    return {
        "message": "Nibe Autotuner API is running",
        "docs_url": "/docs",
        "version": "2.0.0"
    }

if __name__ == "__main__":
    uvicorn.run("api.api_server:app", host="0.0.0.0", port=8502, reload=True)
