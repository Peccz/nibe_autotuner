"""
Dashboard V5 Router
Serves combined status and plan data for the modern Energy Flow dashboard.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List, Optional, Dict
from pydantic import BaseModel

from data.database import get_db
from data.models import PlannedHeatingSchedule, GMAccount
from services.analyzer import HeatPumpAnalyzer
from services.price_service import price_service
from services.weather_service import SMHIWeatherService
from loguru import logger
from sqlalchemy import text

router = APIRouter()
analyzer = HeatPumpAnalyzer()
weather_service = SMHIWeatherService()

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
    spot_price: float
    fan_speed: Optional[float]
    is_frost_guard_active: bool
    is_boost_active: bool
    indoor_temp: float
    target_temp: float
    hw_temp: Optional[float]

class DashboardPlanResponse(BaseModel):
    history: dict
    plan: dict
    table: List[dict]

# --- ENDPOINTS ---

@router.get("/status", response_model=SystemStatus)
def get_dashboard_status(db: Session = Depends(get_db)):
    """Provides real-time status for the header widgets"""
    device = analyzer.get_device()
    
    # 1. Fetch Basic Params
    outdoor = analyzer.get_latest_value(device, analyzer.PARAM_OUTDOOR_TEMP) or 0.0
    in_down = analyzer.get_latest_value(device, 'HA_TEMP_DOWNSTAIRS') or 21.0
    in_dexter = analyzer.get_latest_value(device, 'HA_TEMP_DEXTER') or 21.0
    hum = analyzer.get_latest_value(device, 'HA_HUMIDITY_DOWNSTAIRS')
    evap = analyzer.get_latest_value(device, '40020')
    comp = analyzer.get_latest_value(device, analyzer.PARAM_COMPRESSOR_FREQ) or 0.0
    fan = analyzer.get_latest_value(device, '50221')
    hw = analyzer.get_latest_value(device, '40013')
    
    gm_account = db.query(GMAccount).first()
    
    # 2. Fetch Wind (Try forecast if sensor missing)
    wind_spd = analyzer.get_latest_value(device, 'EXT_WIND_SPEED')
    if wind_spd is None:
        try:
            forecasts = weather_service.get_forecast(hours_ahead=1)
            if forecasts:
                wind_spd = forecasts[0].wind_speed
        except: pass
    
    # 3. Prices
    curr_price = price_service.get_current_price()
    
    return SystemStatus(
        device_name=device.product_name if device else "Nibe F730",
        outdoor_temp=outdoor,
        wind_speed=wind_spd,
        wind_direction=0,
        indoor_downstairs=in_down,
        indoor_dexter=in_dexter,
        indoor_humidity=hum,
        supply_temp=analyzer.get_latest_value(device, analyzer.PARAM_SUPPLY_TEMP) or 0.0,
        evaporator_temp=evap,
        compressor_freq=comp,
        degree_minutes=analyzer.get_latest_value(device, analyzer.PARAM_DM_CURRENT) or 0.0,
        gm_balance=gm_account.balance if gm_account else 0.0,
        gm_mode=gm_account.mode if gm_account else "NORMAL",
        current_price=curr_price,
        spot_price=curr_price, # Placeholder
        fan_speed=fan,
        is_frost_guard_active=(evap is not None and evap < -14.0),
        is_boost_active=(gm_account and gm_account.mode == "SPEND"),
        indoor_temp=in_down,
        target_temp=21.0, # TODO: Read from settings
        hw_temp=hw
    )

@router.get("/plan", response_model=DashboardPlanResponse)
def get_dashboard_plan(db: Session = Depends(get_db)):
    """Provides history and future plan for the chart"""
    device = analyzer.get_device()
    heating_curve = analyzer.get_latest_value(device, analyzer.PARAM_HEATING_CURVE) or 5.0
    
    # --- Future Plan ---
    plan_rows = db.query(PlannedHeatingSchedule).filter(
        PlannedHeatingSchedule.timestamp >= datetime.utcnow()
    ).order_by(PlannedHeatingSchedule.timestamp.asc()).all()
    
    p_indoor = []
    p_dexter = []
    p_outdoor = []
    p_price = []
    p_action = []
    
    table_data = []

    for row in plan_rows:
        p_indoor.append({'x': row.timestamp, 'y': row.simulated_indoor_temp})
        p_dexter.append({'x': row.timestamp, 'y': row.simulated_dexter_temp})
        p_outdoor.append({'x': row.timestamp, 'y': row.outdoor_temp})
        p_price.append({'x': row.timestamp, 'y': row.electricity_price})
        
        # Action bars (10 for RUN, 0 for REST)
        val = 0
        if row.planned_action in ['RUN', 'MUST_RUN']: val = 10
        p_action.append({'x': row.timestamp, 'y': val})
        
        table_data.append({
            "timestamp": row.timestamp,
            "action": row.planned_action,
            "hw_mode": 1, # Default
            "price": row.electricity_price,
            "indoor_sim": row.simulated_indoor_temp or 0.0,
            "dexter_sim": row.simulated_dexter_temp
        })

    # --- History (Last 24h) ---
    # Ideally we fetch from DB. For now return empty or implement a quick query.
    # To keep it fast, we skip history detailed query for now or fetch minimal.
    
    return DashboardPlanResponse(
        history={
            "indoor": [], 
            "dexter": [],
            "outdoor": [],
            "gm": [],
            "bank": []
        },
        plan={
            "indoor": p_indoor,
            "dexter": p_dexter,
            "outdoor": p_outdoor,
            "price": p_price,
            "action": p_action
        },
        table=table_data
    )
