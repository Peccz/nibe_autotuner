import os
from datetime import datetime, timedelta

os.environ.setdefault("MYUPLINK_CLIENT_ID", "test-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "test-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data.database import Base
from data.models import (
    CalibrationHistory,
    Device,
    Parameter,
    ParameterReading,
    PlannedHeatingSchedule,
    PredictionAccuracy,
    System,
)
from data.data_logger import DataLogger
from data.performance_model import DailyPerformance  # noqa: F401 - registers table with Base


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def add_device_and_floor_sensor(db):
    system = System(system_id="system-1", name="Test")
    db.add(system)
    db.flush()

    device = Device(device_id="device-1", system_id=system.id)
    floor_param = Parameter(parameter_id="HA_TEMP_DOWNSTAIRS", parameter_name="Floor")
    db.add_all([device, floor_param])
    db.commit()
    return device, floor_param


def make_logger(db):
    logger = DataLogger.__new__(DataLogger)
    logger.session = db
    return logger


def test_feedback_validation_backfills_and_uses_latest_duplicate_plan():
    db = make_session()
    device, floor_param = add_device_and_floor_sensor(db)
    forecast_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)

    old_plan = PlannedHeatingSchedule(
        timestamp=forecast_hour,
        planned_action="RUN",
        planned_offset=0.0,
        simulated_indoor_temp=20.0,
        outdoor_temp=5.0,
    )
    new_plan = PlannedHeatingSchedule(
        timestamp=forecast_hour,
        planned_action="RUN",
        planned_offset=2.0,
        simulated_indoor_temp=21.0,
        outdoor_temp=5.0,
    )
    db.add_all([old_plan, new_plan])
    db.flush()
    assert new_plan.id > old_plan.id

    db.add(ParameterReading(
        device_id=device.id,
        parameter_id=floor_param.id,
        timestamp=forecast_hour + timedelta(minutes=5),
        value=22.0,
    ))
    db.commit()

    make_logger(db)._validate_predictions()

    rows = db.query(PredictionAccuracy).all()
    assert len(rows) == 1
    assert rows[0].forecast_hour == forecast_hour
    assert rows[0].predicted_indoor == 21.0
    assert rows[0].planned_offset == 2.0
    assert rows[0].error_c == 1.0


def test_calibrate_due_days_runs_missing_day_when_enough_clean_samples_exist():
    db = make_session()
    logger = make_logger(db)
    today = datetime.utcnow().date()
    day_start = datetime.combine(today - timedelta(days=1), datetime.min.time())
    sample_start = day_start - timedelta(days=1)
    called = []

    for hour in range(24):
        db.add(PredictionAccuracy(
            forecast_hour=sample_start + timedelta(hours=hour),
            predicted_indoor=21.0,
            actual_indoor=21.2,
            error_c=0.2,
            planned_offset=1.0,
            outdoor_temp=5.0,
        ))
    db.commit()

    def fake_calibrate(candidate_day_start):
        called.append(candidate_day_start)
        db.add(CalibrationHistory(
            date=candidate_day_start,
            k_leak=0.002,
            k_gain_floor=0.10,
            n_rest=0,
            n_run=24,
            bias_run=0.2,
            mae_before=0.2,
        ))
        db.commit()

    logger._calibrate_thermal_model = fake_calibrate
    logger._calibrate_due_days()

    assert day_start in called
    assert db.query(CalibrationHistory).filter_by(date=day_start).first() is not None
