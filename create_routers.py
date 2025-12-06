import os

# Skapa katalog
os.makedirs('src/api/routers', exist_ok=True)
with open('src/api/routers/__init__.py', 'w') as f:
    f.write("")

# 1. STATUS ROUTER
with open('src/api/routers/status.py', 'w') as f:
    f.write('''from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from data.database import get_db
from data.models import System, Device

router = APIRouter()

@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    """Get current system status"""
    system = db.query(System).first()
    device = db.query(Device).first()
    
    return {
        "system_running": True,
        "service_status": system.is_running if system else False,
        "last_updated": system.last_heartbeat if system else None,
        "device_connected": device is not None,
        "current_profile": "normal"
    }
''')

# 2. USER SETTINGS ROUTER
with open('src/api/routers/user_settings.py', 'w') as f:
    f.write('''from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from data.database import get_db
from data.models import Device
from pydantic import BaseModel, Field

router = APIRouter()

class SettingsUpdate(BaseModel):
    min_indoor_temp: float = Field(..., ge=10, le=30)
    target_indoor_temp_min: float = Field(..., ge=10, le=30)
    target_indoor_temp_max: float = Field(..., ge=10, le=30)

@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    device = db.query(Device).first()
    if not device:
        return {
            "success": True, 
            "settings": {
                "min_indoor_temp": 20.5, 
                "target_indoor_temp_min": 20.5, 
                "target_indoor_temp_max": 22.0
            }
        }
    
    # Hantera om kolumnerna inte finns (bakåtkompatibilitet)
    min_temp = getattr(device, "min_indoor_temp_user_setting", 20.5)
    target_min = getattr(device, "target_indoor_temp_min", 20.5)
    target_max = getattr(device, "target_indoor_temp_max", 22.0)

    return {
        "success": True,
        "settings": {
            "min_indoor_temp": min_temp,
            "target_indoor_temp_min": target_min,
            "target_indoor_temp_max": target_max
        }
    }

@router.post("/settings")
def update_settings(settings: SettingsUpdate, db: Session = Depends(get_db)):
    device = db.query(Device).first()
    if not device:
        raise HTTPException(status_code=404, detail="No device found")
    
    # Uppdatera värden
    device.min_indoor_temp_user_setting = settings.min_indoor_temp
    device.target_indoor_temp_min = settings.target_indoor_temp_min
    device.target_indoor_temp_max = settings.target_indoor_temp_max
    
    db.commit()
    
    return {"success": True, "restart_required": False}
''')

# 3. METRICS ROUTER
with open('src/api/routers/metrics.py', 'w') as f:
    f.write('''from fastapi import APIRouter, Depends
from services.analyzer import HeatPumpAnalyzer

router = APIRouter()

@router.get("/metrics")
def get_metrics():
    try:
        analyzer = HeatPumpAnalyzer()
        metrics = analyzer.calculate_metrics(hours=24)
        return {
            "cop": metrics.cop,
            "avg_indoor_temp": metrics.avg_indoor_temp,
            "total_energy_kwh": metrics.total_energy_kwh,
            "degree_minutes": metrics.degree_minutes
        }
    except Exception as e:
        return {"error": str(e)}
''')

print("✅ Routrar skapade i src/api/routers/")
