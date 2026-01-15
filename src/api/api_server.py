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
from api.routers import parameters
from api.routers import visualizations

# Konfigurera appen
app = FastAPI(
    title="Nibe Autotuner API",
    description="API för styrning och övervakning av Nibe värmepump",
    version="2.1.0"
)

# CORS-inställningar
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Inkludera routers ---

# System Status
app.include_router(status.router, prefix="/api", tags=["Status"])

# AI & Automation
app.include_router(ai_agent.router, prefix="/api/ai-agent", tags=["AI Agent"])

# Metrics & Performance
app.include_router(metrics.router, prefix="/api", tags=["Metrics"])

# User Settings
app.include_router(user_settings.router, prefix="/api/settings", tags=["Settings"])

# Ventilation Control
app.include_router(ventilation.router, prefix="/api/ventilation", tags=["Ventilation"])

# Parameters & History
app.include_router(parameters.router, prefix="/api", tags=["Parameters"])

# Visualizations & Plots
app.include_router(visualizations.router, prefix="/api/visualizations", tags=["Visualizations"])

@app.get("/")
def root():
    return {
        "message": "Nibe Autotuner API is running",
        "docs_url": "/docs",
        "version": "2.1.0"
    }

if __name__ == "__main__":
    uvicorn.run("api.api_server:app", host="0.0.0.0", port=8502, reload=True)

