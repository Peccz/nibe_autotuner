from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime

from data.database import get_db
from data.models import System, Device, ParameterReading

router = APIRouter()

@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    """Hämta systemstatus och hälsa"""
    
    # Hämta grunddata
    system = db.query(System).first()
    device = db.query(Device).first()
    
    # Hämta senaste avläsning för att avgöra om dataloggern lever
    latest_reading = db.query(ParameterReading).order_by(desc(ParameterReading.timestamp)).first()
    
    is_data_fresh = False
    last_seen = None
    
    if latest_reading:
        last_seen = latest_reading.timestamp
        # Om data är nyare än 10 minuter (600 sekunder) räknar vi det som friskt
        # Obs: Vi använder utcnow för jämförelse om timestamp i DB är UTC
        time_diff = datetime.utcnow() - last_seen
        is_data_fresh = time_diff.total_seconds() < 600

    return {
        "success": True,
        "system": {
            "name": system.name if system else "Unknown",
            "id": system.system_id if system else None
        },
        "device": {
            "product": device.product_name if device else "Unknown",
            "connection_state": device.connection_state if device else "Unknown"
        },
        "health": {
            "api_active": True,
            "data_fresh": is_data_fresh,
            "last_data_timestamp": last_seen,
            "message": "System operational" if is_data_fresh else "Warning: Old data"
        }
    }
