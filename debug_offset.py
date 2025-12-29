from data.database import SessionLocal, init_db
from services.analyzer import HeatPumpAnalyzer
from data.models import Device

analyzer = HeatPumpAnalyzer()
session = SessionLocal()
device = session.query(Device).first()

val = analyzer.get_latest_value(device, '47011')
print(f"Latest Offset (47011): {val}")

# Check calculate_metrics
metrics = analyzer.calculate_metrics(hours_back=1)
print(f"Metrics Offset: {metrics.curve_offset}")
print(f"Metrics Outdoor: {metrics.avg_outdoor_temp}")
