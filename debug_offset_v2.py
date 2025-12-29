from data.database import SessionLocal, init_db
from services.analyzer import HeatPumpAnalyzer
from data.models import Device, Parameter, ParameterReading
from sqlalchemy import desc

analyzer = HeatPumpAnalyzer()
session = SessionLocal()
device = session.query(Device).first()

print(f"Device: {device}")

param = session.query(Parameter).filter_by(parameter_id='47011').first()
print(f"Parameter 47011: {param}")

if device and param:
    reading = session.query(ParameterReading).filter_by(
        device_id=device.id,
        parameter_id=param.id
    ).order_by(desc(ParameterReading.timestamp)).first()
    print(f"Direct Reading Query: {reading}")
    if reading:
        print(f"Value: {reading.value}")

val = analyzer.get_latest_value(device, '47011')
print(f"Analyzer get_latest_value: {val}")
