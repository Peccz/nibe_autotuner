#!/bin/bash
# Ventilation Optimizer Daily Run Script
# Runs every morning at 06:00 to adjust ventilation based on outdoor temperature

cd /home/peccz/nibe_autotuner

# Run ventilation optimizer
PYTHONPATH=./src ./venv/bin/python -c "
from ventilation_optimizer import VentilationOptimizer
from api_client import MyUplinkClient
from analyzer import HeatPumpAnalyzer
from models import Device, init_db
from sqlalchemy.orm import sessionmaker

# Initialize
engine = init_db('sqlite:///./data/nibe_autotuner.db')
Session = sessionmaker(bind=engine)
session = Session()
device = session.query(Device).first()

if device:
    # Create optimizer
    api_client = MyUplinkClient()
    analyzer = HeatPumpAnalyzer()
    optimizer = VentilationOptimizer(api_client, analyzer, device.device_id)

    # Apply recommended settings
    result = optimizer.apply_recommended_settings(dry_run=False)

    if result['changed']:
        print(f'✓ Applied {len(result[\"changes\"])} ventilation changes')
    else:
        print('✓ Ventilation already optimal')
else:
    print('✗ No device found in database')
"
