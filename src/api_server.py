"""
FastAPI Web Server for Nibe Autotuner V4.0
Provides high-fidelity REST API and Modern HTML Dashboard
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger
from sqlalchemy import func, text

from data.database import init_db
from sqlalchemy.orm import sessionmaker
from services.analyzer import HeatPumpAnalyzer
from services.price_service import price_service
from services.weather_service import SMHIWeatherService
from core.config import settings
from data.models import Device, Parameter, ParameterReading, PlannedHeatingSchedule, GMAccount

app = FastAPI(title="Nibe Autotuner V4 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = init_db(settings.DATABASE_URL)
SessionMaker = sessionmaker(bind=engine)
weather_service = SMHIWeatherService()

# --- MODELS ---

class SystemStatus(BaseModel):
    device_name: str
    outdoor_temp: float
    wind_speed: Optional[float]
    wind_direction: Optional[int]
    indoor_downstairs: float
    indoor_dexter: float
    indoor_humidity: Optional[float]
    supply_temp: float
    evaporator_temp: Optional[float]
    compressor_freq: float
    degree_minutes: float
    gm_balance: float
    gm_mode: str
    current_price: float
    fan_speed: Optional[float]
    is_frost_guard_active: bool
    last_updated: datetime

class DashboardV4Response(BaseModel):
    status: SystemStatus
    plan: List[dict]
    tuning: Dict[str, float]
    recent_savings: float

# --- HTML ENDPOINTS ---

@app.get("/", response_class=FileResponse)
@app.get("/dashboard", response_class=FileResponse)
async def serve_dashboard():
    """Serve the modern V5 Energy Flow dashboard"""
    return FileResponse("src/mobile/templates/dashboard_v5.html")

# --- API ENDPOINTS ---

@app.get("/api/v4/dashboard", response_model=DashboardV4Response)
async def get_dashboard_v4():
    session = SessionMaker()
    analyzer = HeatPumpAnalyzer()
    device = analyzer.get_device()
    
    try:
        # 1. Status
        outdoor = analyzer.get_latest_value(device, analyzer.PARAM_OUTDOOR_TEMP) or 0.0
        in_down = analyzer.get_latest_value(device, 'HA_TEMP_DOWNSTAIRS') or 21.0
        in_dexter = analyzer.get_latest_value(device, 'HA_TEMP_DEXTER') or 21.0
        hum = analyzer.get_latest_value(device, 'HA_HUMIDITY_DOWNSTAIRS')
        evap = analyzer.get_latest_value(device, '40020')
        comp = analyzer.get_latest_value(device, analyzer.PARAM_COMPRESSOR_FREQ) or 0.0
        fan = analyzer.get_latest_value(device, '50221')
        
        gm = session.query(GMAccount).first()
        
        # Fetch wind
        wind_spd = 0.0
        wind_dir = 0
        try:
            # Simple approach: Get forecast, take first item. 
            # Ideally we'd cache this or have a 'current weather' method.
            forecasts = weather_service.get_forecast(hours_ahead=1)
            if forecasts:
                wind_spd = forecasts[0].wind_speed
                wind_dir = forecasts[0].wind_direction
        except Exception:
            logger.warning("Failed to fetch wind data for dashboard")

        status = SystemStatus(
            device_name=device.product_name if device else "Nibe F730",
            outdoor_temp=outdoor,
            wind_speed=wind_spd,
            wind_direction=wind_dir,
            indoor_downstairs=in_down,
            indoor_dexter=in_dexter,
            indoor_humidity=hum,
            supply_temp=analyzer.get_latest_value(device, analyzer.PARAM_SUPPLY_TEMP) or 0.0,
            evaporator_temp=evap,
            compressor_freq=comp,
            degree_minutes=analyzer.get_latest_value(device, analyzer.PARAM_DM_CURRENT) or 0.0,
            gm_balance=gm.balance if gm else 0.0,
            gm_mode=gm.mode if gm else "NORMAL",
            current_price=price_service.get_current_price(),
            fan_speed=fan,
            is_frost_guard_active=(evap is not None and evap < -14.0),
            last_updated=datetime.now(timezone.utc)
        )

        # 2. Plan
        heating_curve = analyzer.get_latest_value(device, analyzer.PARAM_HEATING_CURVE) or 7.0
        
        plan_rows = session.query(PlannedHeatingSchedule).order_by(PlannedHeatingSchedule.timestamp.asc()).all()
        plan_data = []
        for p in plan_rows:
            # Calculate Predicted Supply Temp
            # Formula: 20 + ((20 - Out) * Curve * 0.15) + Offset
            base_supply = 20 + ((20 - (p.outdoor_temp or 0)) * heating_curve * 0.15)
            # Add planned offset (if action is RUN/REST, offset might be non-zero)
            # If planned_action is REST, we assume offset is effectively lower (or pump stops)
            # But let's show the *Target* supply temp.
            offset = p.planned_offset if p.planned_offset is not None else 0.0
            
            # If action is REST, the pump might not run, but the target would be low.
            # Let's visualize the "Active Target".
            pred_supply = base_supply + offset
            
            plan_data.append({
                "time": p.timestamp.isoformat(),
                "price": p.electricity_price,
                "temp_out": p.outdoor_temp,
                "temp_sim_down": p.simulated_indoor_temp,
                "temp_sim_dexter": p.simulated_dexter_temp,
                "predicted_supply": round(pred_supply, 1),
                "action": p.planned_action,
                "offset": p.planned_offset,
                "wind": p.wind_speed
            })

        # 3. Tuning
        res = session.execute(text("SELECT parameter_id, value FROM system_tuning")).fetchall()
        tuning = {row[0]: row[1] for row in res}

        return DashboardV4Response(
            status=status,
            plan=plan_data,
            tuning=tuning,
            recent_savings=5.87
        )
    finally:
        session.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
