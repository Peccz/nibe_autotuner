"""
Tests for GM 40940 write retry/backoff logic in GMController.

Design principle: a single timeout must NOT miss the GM write (retry succeeds);
all attempts timing out must fail safe — pump holds last setpoint, no crash,
no exception leaking out of run_tick, and last_written_gm is NOT updated
so the next tick will retry the full write.
"""
import os
import time

os.environ.setdefault("MYUPLINK_CLIENT_ID", "test-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "test-secret")

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data.database import Base
from data.models import (
    Device,
    GMAccount,
    GMTransaction,
    Parameter,
    ParameterReading,
    PlannedHeatingSchedule,
    System,
)
from services.gm_controller import GMController
from services.safety_guard import SafetyGuard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def add_param_reading(db, device, param_code, value, now):
    param = Parameter(parameter_id=param_code, parameter_name=param_code)
    db.add(param)
    db.flush()
    db.add(ParameterReading(
        device_id=device.id,
        parameter_id=param.id,
        timestamp=now.replace(tzinfo=None),
        value=value,
    ))
    db.flush()


def build_runtime(now, planned_action="RUN", balance=-500.0):
    """Set up an in-memory runtime with a RUN plan at balance that will trigger a write."""
    db = make_session()
    system = System(system_id="sys-1", name="Test")
    db.add(system)
    db.flush()

    device = Device(
        device_id="dev-1",
        system_id=system.id,
        min_indoor_temp_user_setting=20.5,
        target_indoor_temp_max=22.0,
        target_radiator_temp=21.0,
    )
    db.add(device)
    db.flush()

    db.add(GMAccount(balance=balance, mode="NORMAL"))
    db.add(PlannedHeatingSchedule(
        timestamp=now.replace(tzinfo=None),
        planned_offset=0.0,
        planned_action=planned_action,
        electricity_price=1.0,
        outdoor_temp=5.0,
    ))

    add_param_reading(db, device, "40033", 21.0, now)
    add_param_reading(db, device, "HA_TEMP_DOWNSTAIRS", 21.0, now)
    add_param_reading(db, device, "HA_TEMP_DEXTER", 21.0, now)

    db.commit()
    return db, device


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


GOOD_POINTS = [
    {"parameterId": "40008", "value": 30.0},
    {"parameterId": "40004", "value": 5.0},
    {"parameterId": "40033", "value": 21.0},
    {"parameterId": "40941", "value": -250.0},
]


# ---------------------------------------------------------------------------
# _write_gm_with_retry unit tests
# ---------------------------------------------------------------------------

class SingleSuccessClient:
    """Succeeds on first call."""
    def __init__(self):
        self.call_count = 0

    def set_point_value(self, device_id, parameter_id, value):
        self.call_count += 1
        return {"40940": "modified"}


class TimeoutThenSuccessClient:
    """Times out on first attempt, succeeds on second."""
    def __init__(self):
        self.call_count = 0

    def set_point_value(self, device_id, parameter_id, value):
        self.call_count += 1
        if self.call_count == 1:
            raise requests.exceptions.Timeout("read timeout")
        return {"40940": "modified"}


class AlwaysTimeoutClient:
    """Always times out."""
    def __init__(self):
        self.call_count = 0

    def set_point_value(self, device_id, parameter_id, value):
        self.call_count += 1
        raise requests.exceptions.Timeout("read timeout")


class OtherErrorClient:
    """Raises a non-timeout error (should propagate without retry)."""
    def __init__(self):
        self.call_count = 0

    def set_point_value(self, device_id, parameter_id, value):
        self.call_count += 1
        raise ValueError("unexpected error")


def make_bare_controller():
    """Minimal controller stub for unit-testing _write_gm_with_retry in isolation."""
    ctrl = GMController.__new__(GMController)
    ctrl.PARAM_GM_WRITE = "40940"
    ctrl.GM_WRITE_MAX_ATTEMPTS = 2
    ctrl.GM_WRITE_BACKOFF_SECONDS = 0  # no sleep in unit tests
    return ctrl


def test_retry_helper_succeeds_on_first_attempt():
    ctrl = make_bare_controller()
    client = SingleSuccessClient()
    ctrl.client = client

    result = ctrl._write_gm_with_retry("dev-1", -500)

    assert result == {"40940": "modified"}
    assert client.call_count == 1


def test_retry_helper_retry_then_success():
    """First attempt times out, second succeeds — result returned, two calls made."""
    ctrl = make_bare_controller()
    client = TimeoutThenSuccessClient()
    ctrl.client = client

    with patch("time.sleep"):  # suppress real sleep
        result = ctrl._write_gm_with_retry("dev-1", -500)

    assert result == {"40940": "modified"}
    assert client.call_count == 2


def test_retry_helper_all_timeouts_raises():
    """All GM_WRITE_MAX_ATTEMPTS time out — Timeout is re-raised."""
    ctrl = make_bare_controller()
    client = AlwaysTimeoutClient()
    ctrl.client = client

    with patch("time.sleep"):
        with pytest.raises(requests.exceptions.Timeout):
            ctrl._write_gm_with_retry("dev-1", -500)

    assert client.call_count == ctrl.GM_WRITE_MAX_ATTEMPTS


def test_retry_helper_non_timeout_does_not_retry():
    """Non-timeout errors should propagate on the first attempt without retry."""
    ctrl = make_bare_controller()
    client = OtherErrorClient()
    ctrl.client = client

    with pytest.raises(ValueError):
        ctrl._write_gm_with_retry("dev-1", -500)

    assert client.call_count == 1


# ---------------------------------------------------------------------------
# Integration: run_tick with retry
# ---------------------------------------------------------------------------

def test_run_tick_retry_then_success_updates_last_written_gm():
    """
    run_tick where the first GM write times out but the second succeeds:
    - last_written_gm IS updated (write was confirmed)
    - A GMTransaction is logged
    - No exception escapes run_tick
    """
    now = datetime.now(timezone.utc)
    db, device = build_runtime(now, balance=-500.0)

    class FakeClientTimeoutThenOk:
        def __init__(self):
            self.call_count = 0
            self.writes = []

        def get_device_points(self, device_id):
            return GOOD_POINTS

        def set_point_value(self, device_id, parameter_id, value):
            self.call_count += 1
            if self.call_count == 1:
                raise requests.exceptions.Timeout("read timeout")
            self.writes.append((device_id, parameter_id, value))
            return {"40940": "modified"}

    client = FakeClientTimeoutThenOk()
    ctrl = build_controller(db, client, now)
    ctrl.GM_WRITE_BACKOFF_SECONDS = 0  # no real sleep in test

    with patch("time.sleep"):
        ctrl.run_tick()

    assert ctrl.last_written_gm is not None, "last_written_gm should be set after retry success"
    assert len(client.writes) == 1, "write should have been called exactly once after retry"
    assert client.call_count == 2, "two attempts: 1 timeout + 1 success"

    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx is not None, "GMTransaction should be logged"
    assert tx.gm_written == ctrl.last_written_gm


def test_run_tick_all_timeouts_fails_safe():
    """
    run_tick where ALL GM write attempts time out:
    - No exception escapes run_tick (pump holds last setpoint silently)
    - last_written_gm is NOT updated (next tick will retry)
    - GMTransaction is still logged (with gm_written=None)
    """
    now = datetime.now(timezone.utc)
    db, device = build_runtime(now, balance=-500.0)

    class FakeClientAlwaysTimeout:
        def __init__(self):
            self.call_count = 0

        def get_device_points(self, device_id):
            return GOOD_POINTS

        def set_point_value(self, device_id, parameter_id, value):
            self.call_count += 1
            raise requests.exceptions.Timeout("read timeout")

    client = FakeClientAlwaysTimeout()
    ctrl = build_controller(db, client, now)
    ctrl.GM_WRITE_BACKOFF_SECONDS = 0

    with patch("time.sleep"):
        ctrl.run_tick()  # must NOT raise

    assert ctrl.last_written_gm is None, "last_written_gm must remain None after all timeouts"
    assert client.call_count == ctrl.GM_WRITE_MAX_ATTEMPTS

    # Bank balance should still be updated (GM accounting continues)
    account = db.query(GMAccount).first()
    assert account is not None

    # GMTransaction is logged (gm_written=None = no write confirmed)
    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx is not None
    assert tx.gm_written is None


def test_run_tick_safety_logic_unaffected_by_retry(monkeypatch):
    """
    BASTU-VAKT (BT50 > 23.5) must still trigger even when the write itself would retry.
    The bank must be reset to 100 and action forced to MUST_REST regardless of API retries.
    """
    now = datetime.now(timezone.utc)
    db, device = build_runtime(now, balance=-500.0)

    hot_points = [
        {"parameterId": "40008", "value": 30.0},
        {"parameterId": "40004", "value": 5.0},
        {"parameterId": "40033", "value": 24.0},  # > 23.5 triggers BASTU-VAKT
        {"parameterId": "40941", "value": -250.0},
    ]

    class FakeClientCapture:
        def __init__(self):
            self.writes = []

        def get_device_points(self, device_id):
            return hot_points

        def set_point_value(self, device_id, parameter_id, value):
            self.writes.append((device_id, parameter_id, value))
            return {"40940": "modified"}

    client = FakeClientCapture()
    ctrl = build_controller(db, client, now)

    ctrl.run_tick()

    # BASTU-VAKT forces GM = 100
    assert client.writes == [(device.device_id, ctrl.PARAM_GM_WRITE, 100)]
    tx = db.query(GMTransaction).order_by(GMTransaction.id.desc()).first()
    assert tx.safety_override == "BASTU_VAKT"
    account = db.query(GMAccount).first()
    assert account.balance == 100.0
