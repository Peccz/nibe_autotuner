import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MYUPLINK_CLIENT_ID", "test-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "test-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data.database import Base
from data.models import Device, GMAccount, GMTransaction, Parameter, ParameterReading, PlannedHeatingSchedule, System
from services.gm_controller import GMController
from services.safety_guard import SafetyGuard


class FakeClient:
    def __init__(self, points):
        self.points = points
        self.writes = []

    def get_device_points(self, device_id):
        return self.points

    def set_point_value(self, device_id, parameter_id, value):
        self.writes.append((device_id, parameter_id, value))
        return {"ok": True}


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def add_param_with_reading(db, device, parameter_code, value, now):
    param = Parameter(parameter_id=parameter_code, parameter_name=parameter_code)
    db.add(param)
    db.flush()
    db.add(ParameterReading(
        device_id=device.id,
        parameter_id=param.id,
        timestamp=now.replace(tzinfo=None),
        value=value,
    ))
    db.flush()


def build_controller(db, client, now):
    ctrl = GMController.__new__(GMController)
    ctrl.db = db
    ctrl.client = client
    ctrl.analyzer = None
    ctrl.auth = None
    ctrl.safety_guard = SafetyGuard(db)
    ctrl.last_tick_time = now - timedelta(minutes=1)
    ctrl.last_written_gm = None
    ctrl.last_session_refresh = now
    ctrl._warm_override_active = False
    return ctrl


def setup_runtime(now, planned_action="RUN", floor_temp=22.5, dexter_temp=21.0):
    db = make_session()
    system = System(system_id="system-1", name="Test")
    db.add(system)
    db.flush()

    device = Device(
        device_id="device-1",
        system_id=system.id,
        min_indoor_temp_user_setting=20.5,
        target_indoor_temp_max=22.0,
        target_radiator_temp=21.0,
    )
    db.add(device)
    db.flush()

    db.add(GMAccount(balance=-900.0, mode="NORMAL"))
    db.add(PlannedHeatingSchedule(
        timestamp=now.replace(tzinfo=None),
        planned_offset=2.0,
        planned_action=planned_action,
        electricity_price=1.0,
        outdoor_temp=5.0,
    ))

    add_param_with_reading(db, device, "40033", 21.0, now)
    add_param_with_reading(db, device, "HA_TEMP_DOWNSTAIRS", floor_temp, now)
    add_param_with_reading(db, device, "HA_TEMP_DEXTER", dexter_temp, now)

    db.commit()

    points = [
        {"parameterId": "40008", "value": 28.0},
        {"parameterId": "40004", "value": 5.0},
        {"parameterId": "40033", "value": 21.0},
        {"parameterId": "40941", "value": -250.0},
    ]
    client = FakeClient(points)
    controller = build_controller(db, client, now)
    return db, device, controller, client


def test_warm_downstairs_forces_rest_and_logs_override():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="RUN", floor_temp=22.4, dexter_temp=21.1)

    controller.run_tick()

    assert client.writes == [(device.device_id, controller.PARAM_GM_WRITE, 100)]
    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "REST"
    assert tx.safety_override == "WARM_OVERRIDE_DOWNSTAIRS"


def test_warm_dexter_forces_rest_and_logs_override():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="RUN", floor_temp=21.8, dexter_temp=21.4)

    controller.run_tick()

    assert client.writes == [(device.device_id, controller.PARAM_GM_WRITE, 100)]
    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "REST"
    assert tx.safety_override == "WARM_OVERRIDE_DEXTER"


def test_warm_override_holds_until_release_margin():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="RUN", floor_temp=22.4, dexter_temp=21.0)

    controller.run_tick()
    assert controller._warm_override_active is True

    recent_floor = db.query(ParameterReading).join(Parameter).filter(
        Parameter.parameter_id == "HA_TEMP_DOWNSTAIRS"
    ).order_by(ParameterReading.id.desc()).first()
    recent_floor.value = 22.15
    db.commit()

    client.points = [
        {"parameterId": "40008", "value": 28.0},
        {"parameterId": "40004", "value": 5.0},
        {"parameterId": "40033", "value": 21.0},
        {"parameterId": "40941", "value": -250.0},
    ]
    controller.last_tick_time = now
    controller.run_tick()

    assert controller._warm_override_active is True
    assert client.writes[-1] == (device.device_id, controller.PARAM_GM_WRITE, 100)


def test_dexter_cold_override_still_forces_run():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="REST", floor_temp=21.5, dexter_temp=18.8)

    controller.run_tick()

    assert client.writes
    written_value = client.writes[-1][2]
    assert written_value < 0
    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "RUN"
    assert tx.safety_override is None
