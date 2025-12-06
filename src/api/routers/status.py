from fastapi import APIRouter, Depends
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
