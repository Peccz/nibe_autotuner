import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

# Setup minimal ORM
Base = declarative_base()

class Parameter(Base):
    __tablename__ = 'parameters'
    id = Column(Integer, primary_key=True)
    parameter_id = Column(String)

class ParameterReading(Base):
    __tablename__ = 'parameter_readings'
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer)
    parameter_id = Column(Integer)
    timestamp = Column(DateTime)
    value = Column(Float)

# Connect
engine = create_engine('sqlite:///data/nibe_autotuner.db')
Session = sessionmaker(bind=engine)
session = Session()

# Query
param_id = 'HA_TEMP_DOWNSTAIRS'
pid = session.query(Parameter).filter_by(parameter_id=param_id).first()

if not pid:
    print(f"Parameter {param_id} NOT found!")
else:
    print(f"Parameter {param_id} found with ID {pid.id}")
    
    now = datetime.utcnow()
    history_start = now - timedelta(hours=12)
    print(f"Querying from {history_start} to {now}")
    
    count = session.query(ParameterReading).filter(
        ParameterReading.parameter_id == pid.id,
        ParameterReading.timestamp >= history_start
    ).count()
    
    print(f"Found {count} readings.")
    
    if count == 0:
        # Check latest reading time
        latest = session.query(ParameterReading).filter(
            ParameterReading.parameter_id == pid.id
        ).order_by(ParameterReading.timestamp.desc()).first()
        if latest:
            print(f"Latest reading was at: {latest.timestamp}")
        else:
            print("No readings ever.")
