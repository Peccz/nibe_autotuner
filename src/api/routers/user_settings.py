from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from data.database import get_db
from data.models import Device
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

router = APIRouter()

class SettingsUpdate(BaseModel):
    min_indoor_temp: float = Field(..., ge=10, le=30)
    target_indoor_temp_min: float = Field(..., ge=10, le=30)
    target_indoor_temp_max: float = Field(..., ge=10, le=30)
    comfort_adjustment_offset: Optional[float] = Field(0.0, ge=-10, le=10)

class ComfortOffsetUpdate(BaseModel):
    offset: float = Field(..., ge=-10, le=10)

@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    device = db.query(Device).first()
    if not device:
        return {
            "success": True, 
            "settings": {
                "min_indoor_temp": 20.5, 
                "target_indoor_temp_min": 20.5, 
                "target_indoor_temp_max": 22.0,
                "comfort_adjustment_offset": 0.0
            }
        }
    
    # Hantera om kolumnerna inte finns (bakåtkompatibilitet)
    min_temp = getattr(device, "min_indoor_temp_user_setting", 20.5)
    target_min = getattr(device, "target_indoor_temp_min", 20.5)
    target_max = getattr(device, "target_indoor_temp_max", 22.0)
    comfort_offset = getattr(device, "comfort_adjustment_offset", 0.0)

    away_enabled = getattr(device, "away_mode_enabled", False)
    away_end = getattr(device, "away_mode_end_date", None)
    # Auto-expire if end date passed
    if away_enabled and away_end and away_end <= datetime.utcnow():
        device.away_mode_enabled = False
        away_enabled = False
        db.commit()

    return {
        "success": True,
        "settings": {
            "min_indoor_temp": min_temp,
            "target_indoor_temp_min": target_min,
            "target_indoor_temp_max": target_max,
            "comfort_adjustment_offset": comfort_offset,
            "away_mode_enabled": away_enabled,
            "away_mode_end_date": away_end.isoformat() if away_end else None
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
    
    if settings.comfort_adjustment_offset is not None:
        device.comfort_adjustment_offset = settings.comfort_adjustment_offset
    
    db.commit()
    
    return {"success": True, "restart_required": False}

class AwayModeUpdate(BaseModel):
    enabled: bool
    end_date: Optional[datetime] = None

@router.post("/settings/away-mode")
def update_away_mode(update: AwayModeUpdate, db: Session = Depends(get_db)):
    device = db.query(Device).first()
    if not device:
        raise HTTPException(status_code=404, detail="No device found")
    device.away_mode_enabled = update.enabled
    device.away_mode_end_date = update.end_date
    db.commit()
    status = "aktiverat" if update.enabled else "avaktiverat"
    return {"success": True, "message": f"Borta-läge {status}"}

@router.post("/settings/comfort-offset")
def update_comfort_offset(update: ComfortOffsetUpdate, db: Session = Depends(get_db)):
    """Update only the comfort offset slider"""
    device = db.query(Device).first()
    if not device:
        raise HTTPException(status_code=404, detail="No device found")
    
    device.comfort_adjustment_offset = update.offset
    db.commit()
    
    return {
        "success": True, 
        "message": f"Comfort offset updated to {update.offset}",
        "current_offset": update.offset
    }
