"""
Status API Router
Provides comprehensive system status with all key parameters
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from typing import Optional

from data.database import get_db
from data.models import System, Device, ParameterReading, Parameter

router = APIRouter()

def get_latest_parameter_value(db: Session, parameter_id: str) -> Optional[float]:
    """Helper to get latest value for a parameter"""
    param = db.query(Parameter).filter(Parameter.parameter_id == parameter_id).first()
    if not param:
        return None

    reading = db.query(ParameterReading).filter(
        ParameterReading.parameter_id == param.id
    ).order_by(desc(ParameterReading.timestamp)).first()

    return reading.value if reading else None

@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    """Hämta fullständig systemstatus med alla viktiga parametrar"""

    # Hämta grunddata
    system = db.query(System).first()
    device = db.query(Device).first()

    # Hämta senaste avläsning för att avgöra om dataloggern lever
    latest_reading = db.query(ParameterReading).order_by(desc(ParameterReading.timestamp)).first()

    is_data_fresh = False
    last_seen = None

    if latest_reading:
        last_seen = latest_reading.timestamp
        time_diff = datetime.utcnow() - last_seen
        is_data_fresh = time_diff.total_seconds() < 600

    # Hämta alla viktiga parametervärden
    outdoor_temp = get_latest_parameter_value(db, "40004")  # Outdoor temp
    indoor_temp = get_latest_parameter_value(db, "40033")   # Room temp BT50
    supply_temp = get_latest_parameter_value(db, "40008")   # Supply temp BT2
    return_temp = get_latest_parameter_value(db, "40012")   # Return temp BT3
    hot_water_temp = get_latest_parameter_value(db, "40013") # Hot water BT7
    compressor_freq = get_latest_parameter_value(db, "43424") # Compressor freq
    degree_minutes = get_latest_parameter_value(db, "43005")  # Degree minutes
    heating_curve = get_latest_parameter_value(db, "47007")   # Heating curve
    curve_offset = get_latest_parameter_value(db, "47011")    # Curve offset

    # Beräkna enkel COP-uppskattning
    estimated_cop = None
    if outdoor_temp is not None and supply_temp is not None and return_temp is not None:
        delta_t = supply_temp - return_temp
        if delta_t > 0:
            # Carnot-baserad uppskattning
            t_out_k = outdoor_temp + 273.15
            t_supply_k = supply_temp + 273.15
            carnot_cop = t_supply_k / (t_supply_k - t_out_k)
            estimated_cop = round(carnot_cop * 0.45, 2)  # 45% av Carnot-efficiency

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
        },
        "parameters": {
            "temperatures": {
                "outdoor": outdoor_temp,
                "indoor": indoor_temp,
                "supply": supply_temp,
                "return": return_temp,
                "hot_water": hot_water_temp
            },
            "operation": {
                "compressor_frequency": compressor_freq,
                "degree_minutes": degree_minutes,
                "estimated_cop": estimated_cop
            },
            "settings": {
                "heating_curve": heating_curve,
                "curve_offset": curve_offset
            }
        }
    }

