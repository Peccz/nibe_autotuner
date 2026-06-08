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


def add_param_history(db, device, parameter_code, values, start):
    param = db.query(Parameter).filter_by(parameter_id=parameter_code).first()
    if not param:
        param = Parameter(parameter_id=parameter_code, parameter_name=parameter_code)
        db.add(param)
        db.flush()
    for index, value in enumerate(values):
        db.add(ParameterReading(
            device_id=device.id,
            parameter_id=param.id,
            timestamp=(start + timedelta(minutes=15 * index)).replace(tzinfo=None),
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
    ctrl._last_sensor_mode = "unknown"
    ctrl._last_floor_temp = None
    ctrl._last_dexter_temp = None
    ctrl._last_comfort_bounds = None
    ctrl._active_ventilation_events = {}
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


def test_profile_max_forces_rest_below_device_legacy_max(monkeypatch):
    monkeypatch.setattr(
        "services.gm_controller.comfort_bounds_for_time",
        lambda now: {
            "profile": "night",
            "floor_min": 20.3,
            "floor_max": 21.2,
            "dexter_min": 19.8,
            "dexter_max": 20.8,
            "boost_allowed": False,
        },
    )
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="RUN", floor_temp=21.4, dexter_temp=20.4)

    controller.run_tick()

    assert client.writes == [(device.device_id, controller.PARAM_GM_WRITE, 100)]
    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "REST"
    assert tx.safety_override == "WARM_OVERRIDE_DOWNSTAIRS"


def test_warm_dexter_forces_rest_and_logs_override():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="RUN", floor_temp=20.8, dexter_temp=21.4)

    controller.run_tick()

    assert client.writes == [(device.device_id, controller.PARAM_GM_WRITE, 100)]
    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "REST"
    assert tx.safety_override == "WARM_OVERRIDE_DEXTER"


def test_warm_override_resets_negative_bank_debt():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="RUN", floor_temp=20.8, dexter_temp=21.4)

    account = db.query(GMAccount).first()
    account.balance = -2000.0
    db.commit()

    client.points = [
        {"parameterId": "40008", "value": 21.0},
        {"parameterId": "40004", "value": -2.0},
        {"parameterId": "40033", "value": 21.0},
        {"parameterId": "40941", "value": -250.0},
    ]

    controller.run_tick()

    account = db.query(GMAccount).first()
    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert account.balance == 100.0
    assert tx.new_balance == 100.0
    assert tx.delta_gm == 0.0
    assert tx.action == "REST"
    assert tx.safety_override == "WARM_OVERRIDE_DEXTER"
    assert client.writes[-1] == (device.device_id, controller.PARAM_GM_WRITE, 100)


def test_stale_zone_sensors_use_bt50_gap_fallback_for_warm_override():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="RUN", floor_temp=24.0, dexter_temp=23.0)

    stale_time = (now - timedelta(hours=2)).replace(tzinfo=None)
    stale_readings = db.query(ParameterReading).join(Parameter).filter(
        Parameter.parameter_id.in_(["HA_TEMP_DOWNSTAIRS", "HA_TEMP_DEXTER"])
    ).all()
    for reading in stale_readings:
        reading.timestamp = stale_time

    bt50_param = db.query(Parameter).filter_by(parameter_id="40033").first()
    db.add(ParameterReading(
        device_id=device.id,
        parameter_id=bt50_param.id,
        timestamp=stale_time,
        value=23.8,
    ))
    db.commit()

    client.points = [
        {"parameterId": "40008", "value": 28.0},
        {"parameterId": "40004", "value": 5.0},
        {"parameterId": "40033", "value": 22.2},
        {"parameterId": "40941", "value": -250.0},
    ]

    controller.run_tick()

    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "REST"
    assert tx.safety_override == "WARM_OVERRIDE_DOWNSTAIRS"
    assert client.writes[-1] == (device.device_id, controller.PARAM_GM_WRITE, 100)


def test_bt50_downstairs_calibration_uses_bucketed_history():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, floor_temp=20.8)
    bt50_param = db.query(Parameter).filter_by(parameter_id="40033").first()
    floor_param = db.query(Parameter).filter_by(parameter_id="HA_TEMP_DOWNSTAIRS").first()
    start = now - timedelta(days=1)

    for index in range(24):
        ts = (start + timedelta(minutes=5 * index)).replace(tzinfo=None)
        db.add(ParameterReading(device_id=device.id, parameter_id=bt50_param.id, timestamp=ts, value=20.9))
        db.add(ParameterReading(
            device_id=device.id,
            parameter_id=floor_param.id,
            timestamp=ts + timedelta(seconds=30),
            value=20.7,
        ))
    db.commit()

    assert round(controller._get_bt50_downstairs_gap(), 2) == -0.20


def test_fallback_suppresses_stale_negative_bank_debt_when_comfortable(monkeypatch):
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="RUN", floor_temp=20.7, dexter_temp=20.2)
    monkeypatch.setattr(
        "services.gm_controller.comfort_bounds_for_time",
        lambda now: {
            "profile": "day",
            "floor_min": 20.5,
            "floor_max": 21.8,
            "dexter_min": 20.0,
            "dexter_max": 21.3,
            "planning_floor_max": 21.8,
            "planning_dexter_max": 21.3,
            "boost_allowed": False,
        },
    )

    stale_time = (now - timedelta(hours=2)).replace(tzinfo=None)
    stale_readings = db.query(ParameterReading).join(Parameter).filter(
        Parameter.parameter_id.in_(["HA_TEMP_DOWNSTAIRS", "HA_TEMP_DEXTER"])
    ).all()
    for reading in stale_readings:
        reading.timestamp = stale_time

    bt50_param = db.query(Parameter).filter_by(parameter_id="40033").first()
    db.add(ParameterReading(
        device_id=device.id,
        parameter_id=bt50_param.id,
        timestamp=stale_time,
        value=20.7,
    ))
    account = db.query(GMAccount).first()
    account.balance = -2000.0
    db.commit()

    client.points = [
        {"parameterId": "40008", "value": 24.0},
        {"parameterId": "40004", "value": 5.0},
        {"parameterId": "40033", "value": 20.9},
        {"parameterId": "40941", "value": -250.0},
    ]

    controller.run_tick()

    account = db.query(GMAccount).first()
    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert account.balance == 0.0
    assert tx.new_balance == 0.0
    assert tx.action == "RUN"
    assert tx.safety_override is None
    assert client.writes[-1] == (device.device_id, controller.PARAM_GM_WRITE, 0)


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
    db, device, controller, client = setup_runtime(now, planned_action="REST", floor_temp=20.8, dexter_temp=18.8)

    controller.run_tick()

    assert client.writes
    written_value = client.writes[-1][2]
    assert written_value < 0
    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "RUN"
    assert tx.safety_override is None


def test_dexter_window_event_suppresses_cold_run_override():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="REST", floor_temp=21.7, dexter_temp=18.8)
    start = now - timedelta(hours=1)
    add_param_history(db, device, "HA_TEMP_DOWNSTAIRS", [21.7, 21.7, 21.7, 21.7, 21.7], start)
    add_param_history(db, device, "HA_TEMP_DEXTER", [20.6, 20.0, 19.3, 18.9, 18.8], start)
    add_param_history(db, device, "40033", [21.5, 21.5, 21.5, 21.5, 21.5], start)
    db.commit()

    controller.run_tick()

    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "REST"
    assert client.writes[-1] == (device.device_id, controller.PARAM_GM_WRITE, 100)


def test_window_event_blocks_current_boost():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="BOOST", floor_temp=20.9, dexter_temp=18.8)
    start = now - timedelta(hours=1)
    add_param_history(db, device, "HA_TEMP_DOWNSTAIRS", [20.9, 20.9, 20.9, 20.9, 20.9], start)
    add_param_history(db, device, "HA_TEMP_DEXTER", [20.6, 20.0, 19.3, 18.9, 18.8], start)
    add_param_history(db, device, "40033", [20.9, 20.9, 20.9, 20.9, 20.9], start)
    db.commit()

    controller.run_tick()

    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "RUN"


def test_west_facade_outdoor_spike_is_filtered_against_plan_reference():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="RUN", floor_temp=21.0, dexter_temp=20.8)

    plan = db.query(PlannedHeatingSchedule).first()
    plan.planned_offset = 2.0
    plan.outdoor_temp = 14.0
    db.commit()

    client.points = [
        {"parameterId": "40008", "value": 28.0},
        {"parameterId": "40004", "value": 32.0},
        {"parameterId": "40033", "value": 21.0},
        {"parameterId": "40941", "value": -250.0},
    ]

    controller.run_tick()

    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.outdoor_temp == 16.0
    assert round(tx.supply_target, 2) == 25.36


def test_old_current_hour_uses_next_rest_when_zone_is_over_max(monkeypatch):
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="RUN", floor_temp=22.2, dexter_temp=20.8)

    plan = db.query(PlannedHeatingSchedule).first()
    plan.timestamp = (now - timedelta(minutes=50)).replace(tzinfo=None)
    plan.planned_offset = 0.0
    db.add(PlannedHeatingSchedule(
        timestamp=(now + timedelta(minutes=10)).replace(tzinfo=None),
        planned_offset=-3.0,
        planned_action="REST",
        electricity_price=1.0,
        outdoor_temp=5.0,
    ))
    db.commit()

    monkeypatch.setattr(
        controller,
        "_apply_zone_temperature_overrides",
        lambda device, now, action, bt50_indoor=None: (action, None),
    )

    controller.run_tick()

    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "REST"
    assert tx.safety_override is None
    assert client.writes[-1] == (device.device_id, controller.PARAM_GM_WRITE, 100)


def test_current_boost_is_blocked_when_supply_heat_is_in_flight(monkeypatch):
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="BOOST", floor_temp=21.0, dexter_temp=20.8)

    plan = db.query(PlannedHeatingSchedule).first()
    plan.timestamp = (now - timedelta(minutes=50)).replace(tzinfo=None)
    plan.planned_offset = 3.0
    db.commit()

    client.points = [
        {"parameterId": "40008", "value": 45.0},
        {"parameterId": "40004", "value": 5.0},
        {"parameterId": "40033", "value": 21.0},
        {"parameterId": "40941", "value": -250.0},
    ]
    monkeypatch.setattr(
        controller,
        "_apply_zone_temperature_overrides",
        lambda device, now, action, bt50_indoor=None: (action, None),
    )

    controller.run_tick()

    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "RUN"
    assert round(tx.supply_target, 2) == 32.60


def test_current_boost_is_blocked_when_room_heat_surplus_exists(monkeypatch):
    now = datetime(2026, 5, 8, 15, 30, tzinfo=timezone.utc)  # 17:30 local evening_preshed
    db, device, controller, client = setup_runtime(now, planned_action="BOOST", floor_temp=21.9, dexter_temp=21.1)

    plan = db.query(PlannedHeatingSchedule).first()
    plan.planned_offset = 3.0
    db.commit()

    monkeypatch.setattr(
        controller,
        "_apply_zone_temperature_overrides",
        lambda device, now, action, bt50_indoor=None: (action, None),
    )

    controller.run_tick()

    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "RUN"
    assert round(tx.supply_target, 2) == 32.60


def test_overheated_boost_plan_is_forced_to_rest_by_gm_controller():
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="BOOST", floor_temp=22.4, dexter_temp=21.1)

    plan = db.query(PlannedHeatingSchedule).first()
    plan.planned_offset = 3.0
    db.commit()

    controller.run_tick()

    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "REST"
    assert tx.safety_override == "WARM_OVERRIDE_DOWNSTAIRS"
    assert client.writes[-1] == (device.device_id, controller.PARAM_GM_WRITE, 100)


def test_recovery_bank_is_capped_when_zones_are_near_floors(monkeypatch):
    now = datetime.now(timezone.utc)
    db, device, controller, client = setup_runtime(now, planned_action="RUN", floor_temp=21.0, dexter_temp=20.8)
    monkeypatch.setattr(
        "services.gm_controller.comfort_bounds_for_time",
        lambda now: {
            "profile": "day",
            "floor_min": 20.5,
            "floor_max": 21.8,
            "dexter_min": 20.0,
            "dexter_max": 21.3,
            "planning_floor_max": 21.8,
            "planning_dexter_max": 21.3,
            "boost_allowed": False,
        },
    )

    account = db.query(GMAccount).first()
    account.balance = -900.0
    db.commit()

    client.points = [
        {"parameterId": "40008", "value": 21.0},
        {"parameterId": "40004", "value": 5.0},
        {"parameterId": "40033", "value": 21.0},
        {"parameterId": "40941", "value": -250.0},
    ]

    controller.run_tick()

    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.action == "RUN"
    assert tx.new_balance == -250.0
    assert client.writes[-1] == (device.device_id, controller.PARAM_GM_WRITE, -250)
