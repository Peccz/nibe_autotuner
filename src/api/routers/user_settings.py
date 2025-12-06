from fastapi import APIRouter, Depends, HTTPException
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
