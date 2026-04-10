import os
from datetime import datetime

os.environ.setdefault("MYUPLINK_CLIENT_ID", "test-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "test-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.schemas import AgentAIDecisionSchema
from data.database import Base
from data.models import Device, Parameter, ParameterReading, System
from services.safety_guard import SafetyGuard


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def add_device_with_indoor_temp(db, temp=21.0):
    system = System(system_id="system-1", name="Test")
    db.add(system)
    db.flush()

    device = Device(
        device_id="device-1",
        system_id=system.id,
        min_indoor_temp_user_setting=20.5,
    )
    indoor_param = Parameter(parameter_id="40033", parameter_name="BT50")
    db.add_all([device, indoor_param])
    db.flush()

    db.add(ParameterReading(
        device_id=device.id,
        parameter_id=indoor_param.id,
        timestamp=datetime.utcnow(),
        value=temp,
    ))
    db.commit()
    return device


def test_safety_guard_caps_gm_above_max():
    db = make_session()
    device = add_device_with_indoor_temp(db)
    guard = SafetyGuard(db)

    decision = AgentAIDecisionSchema(
        action="adjust",
        parameter="40940",
        current_value=0,
        suggested_value=500,
        reasoning="unit test",
        confidence=1.0,
        expected_impact="cap high GM",
    )

    is_safe, reason, safe_value = guard.validate_decision(decision, device.device_id)

    assert is_safe is True
    assert "max 200" in reason
    assert safe_value == 200


def test_safety_guard_caps_gm_below_min():
    db = make_session()
    device = add_device_with_indoor_temp(db)
    guard = SafetyGuard(db)

    decision = AgentAIDecisionSchema(
        action="adjust",
        parameter="40940",
        current_value=0,
        suggested_value=-2500,
        reasoning="unit test",
        confidence=1.0,
        expected_impact="cap low GM",
    )

    is_safe, reason, safe_value = guard.validate_decision(decision, device.device_id)

    assert is_safe is True
    assert "min -2000" in reason
    assert safe_value == -2000


def test_safety_guard_blocks_lowering_heat_when_temp_unknown():
    db = make_session()
    system = System(system_id="system-1", name="Test")
    db.add(system)
    db.flush()
    device = Device(device_id="device-1", system_id=system.id)
    db.add(device)
    db.commit()

    guard = SafetyGuard(db)
    decision = AgentAIDecisionSchema(
        action="adjust",
        parameter="40940",
        current_value=0,
        suggested_value=-100,
        reasoning="unit test",
        confidence=1.0,
        expected_impact="lower GM with unknown temp",
    )

    is_safe, reason, safe_value = guard.validate_decision(decision, device.device_id)

    assert is_safe is False
    assert "Unknown indoor temp" in reason
    assert safe_value is None
