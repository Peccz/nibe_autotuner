from data.database import SessionLocal, init_db
from services.analyzer import HeatPumpAnalyzer
from data.models import Device, Parameter, ParameterReading
from sqlalchemy import desc
import os

print(f"CWD: {os.getcwd()}")

analyzer = HeatPumpAnalyzer()
print(f"Analyzer DB URL: {analyzer.db_url}")

# Create internal session check
param_internal = analyzer.session.query(Parameter).filter_by(parameter_id='47011').first()
print(f"Analyzer Internal Param: {param_internal}")

session = SessionLocal()
device = session.query(Device).first()
print(f"Device ID: {device.id}")

if device and param_internal:
    reading = analyzer.session.query(ParameterReading).filter_by(
        device_id=device.id,
        parameter_id=param_internal.id
    ).order_by(desc(ParameterReading.timestamp)).first()
    print(f"Analyzer Internal Reading: {reading}")

val = analyzer.get_latest_value(device, '47011')
print(f"Analyzer get_latest_value: {val}")
