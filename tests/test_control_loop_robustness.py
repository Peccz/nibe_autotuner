"""Robustness fixes for the control loop (#1 timeout, #2 missing sensor,
#3 stale system mode, #4 stale BT50 in SafetyGuard)."""
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MYUPLINK_CLIENT_ID", "test-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "test-secret")

import requests

from data.models import Device, GMTransaction, Parameter, ParameterReading, System
from services.gm_controller import GMController
from services.safety_guard import SafetyGuard
from api.schemas import AgentAIDecisionSchema

# Reuse the established in-memory + FakeClient fixtures.
from test_gm_controller_warm_override import (
    FakeClient,
    make_session,
    setup_runtime,
    add_param_with_reading,
)


def _minimal_db_with_bt50(value, timestamp):
    """A fresh in-memory DB with a single device and one BT50 (40033) reading."""
    db = make_session()
    system = System(system_id="system-1", name="Test")
    db.add(system)
    db.flush()
    device = Device(
        device_id="device-1",
        system_id=system.id,
        min_indoor_temp_user_setting=20.5,
    )
    db.add(device)
    db.flush()
    add_param_with_reading(db, device, "40033", value, timestamp)
    db.commit()
    return db, device


# --- #1: API timeout -------------------------------------------------------

def test_make_request_applies_default_timeout_when_caller_omits_it():
    from integrations.api_client import MyUplinkClient, DEFAULT_TIMEOUT

    client = MyUplinkClient.__new__(MyUplinkClient)
    client.base_url = "http://example.invalid"
    client._get_headers = lambda: {}
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    class _Session:
        def request(self, method, url, headers=None, **kwargs):
            captured.update(kwargs)
            return _Resp()

    client.session = _Session()
    client._make_request("GET", "/v2/x")
    assert captured["timeout"] == DEFAULT_TIMEOUT


class _RaisingClient(FakeClient):
    def get_device_points(self, device_id):
        raise requests.Timeout("simulated hang")


def test_run_tick_survives_api_timeout_without_writing():
    now = datetime.now(timezone.utc)
    db, device, controller, _ = setup_runtime(now)
    controller.client = _RaisingClient([])

    controller.run_tick()  # must not raise

    assert controller.client.writes == []


# --- #2: missing critical sensor ------------------------------------------

def test_missing_critical_sensor_skips_tick_without_writing():
    now = datetime.now(timezone.utc)
    db, device, controller, _ = setup_runtime(now)
    # Outdoor (40004) absent from the API response.
    points = [
        {"parameterId": "40008", "value": 28.0},
        {"parameterId": "40033", "value": 21.0},
        {"parameterId": "40941", "value": -250.0},
    ]
    controller.client = FakeClient(points)

    controller.run_tick()

    assert controller.client.writes == []
    assert db.query(GMTransaction).count() == 0  # returned before logging a tx


# --- #3: stale VP_SYSTEM_MODE ---------------------------------------------

def _latest_tx(db):
    return db.query(GMTransaction).order_by(GMTransaction.timestamp.desc()).first()


def test_stale_system_mode_is_treated_as_heating():
    now = datetime.now(timezone.utc)
    db, device, controller, _ = setup_runtime(now)
    # A stale 'hot water' (2.0) reading from 2h ago must be ignored.
    add_param_with_reading(db, device, "VP_SYSTEM_MODE", 2.0, now - timedelta(hours=2))
    db.commit()

    controller.run_tick()

    tx = _latest_tx(db)
    assert tx is not None
    assert tx.system_mode == 1.0  # heating, not the stale 2.0


def test_fresh_hot_water_mode_pauses_the_bank():
    now = datetime.now(timezone.utc)
    db, device, controller, _ = setup_runtime(now)
    add_param_with_reading(db, device, "VP_SYSTEM_MODE", 2.0, now)
    db.commit()

    controller.run_tick()

    tx = _latest_tx(db)
    assert tx is not None
    assert tx.system_mode == 2.0
    assert tx.delta_gm == 0.0  # bank paused during hot water


# --- #4: stale BT50 in SafetyGuard ----------------------------------------

def _lower_gm_decision():
    return AgentAIDecisionSchema(
        action="adjust",
        parameter="40940",
        current_value=100.0,
        suggested_value=-200.0,
        reasoning="test lowering",
        confidence=1.0,
        expected_impact="lower heat",
    )


def test_stale_bt50_blocks_lowering_as_unknown_temp():
    now = datetime.now(timezone.utc)
    # Warm but STALE BT50 (2h old): with the fix this routes to the unknown-temp
    # branch, which blocks lowering. Without the fix the warm value would pass.
    db, device = _minimal_db_with_bt50(25.0, now - timedelta(hours=2))
    guard = SafetyGuard(db)

    is_safe, reason, _ = guard.validate_decision(_lower_gm_decision(), device.device_id)
    assert is_safe is False
    assert "Unknown indoor temp" in reason


def test_fresh_warm_bt50_allows_lowering():
    now = datetime.now(timezone.utc)
    db, device = _minimal_db_with_bt50(25.0, now)
    guard = SafetyGuard(db)

    is_safe, _, _ = guard.validate_decision(_lower_gm_decision(), device.device_id)
    assert is_safe is True
