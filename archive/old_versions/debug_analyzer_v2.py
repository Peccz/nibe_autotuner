import sys
import os
sys.path.insert(0, os.path.abspath('src'))

from services.analyzer import HeatPumpAnalyzer
from data.database import SessionLocal
from data.models import Device

def main():
    analyzer = HeatPumpAnalyzer()
    session = SessionLocal()
    
    device = session.query(Device).first()
    print(f"Device: {device.id} ({device.product_name})")
    
    val = analyzer.get_latest_value(device, '40033')
    print(f"Latest value for 40033: {val}")
    
    # Try getting parameter directly
    from data.models import Parameter
    param = analyzer.session.query(Parameter).filter_by(parameter_id='40033').first()
    print(f"Param 40033 in analyzer session: {param}")
    
    if param:
        from data.models import ParameterReading
        from sqlalchemy import desc
        reading = analyzer.session.query(ParameterReading).filter_by(
            device_id=device.id,
            parameter_id=param.id
        ).order_by(desc(ParameterReading.timestamp)).first()
        print(f"Manual reading check: {reading.value if reading else 'None'} at {reading.timestamp if reading else 'N/A'}")

if __name__ == "__main__":
    main()
