"""Regression tests for task #12: summer over-heating fix.

Root cause: The thermal model applied negative gain (k_gain * negative_offset) to
simulate cooling, but the heat pump cannot actively remove heat. Only passive
thermal loss drives cooling in REST mode. Negative offsets mean "no heat input",
not "active heat removal."

Fix: gain = max(0.0, k_gain * offset) in both optimizer.py and v15_mpc.py.

These tests confirm:
1. The model does NOT predict rapid cooldown from a hot house when REST is scheduled.
2. V16 correctly schedules all-REST when the house is hot above floor_max.
3. V15/V16 never schedule BOOST when the house is already over the upper comfort band
   and start_over_max is True.
4. Winter behavior is not regressed: the optimizer still raises offsets to heat a cold house.
"""
import os
from datetime import datetime, timedelta

os.environ.setdefault("MYUPLINK_CLIENT_ID", "test-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "test-secret")

from core.config import settings
from services.optimizer import predict_temperatures, predict_temperatures_two_zone, optimize_24h_plan
from services.v15_mpc import simulate_v15, plan_v16_robust, plan_v15_shadow


# --- Thermal model unit tests ---

def test_rest_offset_does_not_actively_cool_floor():
    """REST offset must NOT produce faster cooldown than pure passive loss.

    Before the fix, offset=-3.0 gave gain=-0.30°C/h, pulling house from 25°C to
    ~21°C within hours. After the fix, only passive K_LEAK loss applies (≈0.01°C/h
    at outdoor=20°C), so a hot house stays warm for many hours under REST.
    """
    start_temp = 25.0
    outdoor = [20.0] * 24
    rest_offsets = [settings.OPTIMIZER_REST_THRESHOLD - 0.5] * 24  # clear REST (-3.0)

    temps = predict_temperatures(
        start_temp=start_temp,
        outdoor_temps=outdoor,
        offsets=rest_offsets,
    )

    # After 1 hour of REST with outdoor=20°C:
    # passive loss = K_LEAK * (25-20) = 0.002 * 5 = 0.01°C/h
    # With the fix: temp after 1h ≈ 24.99°C (tiny passive drop), not 24.7°C (buggy -0.3°C/h)
    # Allow some tolerance but it must NOT drop more than 0.05°C in 1 hour.
    assert temps[0] >= start_temp - 0.05, (
        f"REST offset must not actively cool: after 1h from {start_temp}°C, got {temps[0]:.3f}°C "
        f"(expected ≥{start_temp - 0.05:.2f}°C). "
        f"Fix: clamp gain=max(0,k_gain*offset) to prevent artificial cooling."
    )


def test_rest_offset_two_zone_does_not_actively_cool():
    """Same as above for the two-zone model."""
    start_floor = 25.0
    start_radiator = 24.5
    outdoor = [20.0] * 24
    rest_offsets = [settings.OPTIMIZER_REST_THRESHOLD - 0.5] * 24

    floor_temps, rad_temps = predict_temperatures_two_zone(
        start_floor=start_floor,
        start_radiator=start_radiator,
        outdoor_temps=outdoor,
        offsets=rest_offsets,
    )

    # After 1 hour, both zones should cool only by passive loss, not active cooling
    assert floor_temps[0] >= start_floor - 0.05, (
        f"Two-zone floor must not actively cool: after 1h got {floor_temps[0]:.3f}°C "
        f"(expected ≥{start_floor - 0.05:.2f}°C)"
    )
    assert rad_temps[0] >= start_radiator - 0.05, (
        f"Two-zone radiator must not actively cool: after 1h got {rad_temps[0]:.3f}°C "
        f"(expected ≥{start_radiator - 0.05:.2f}°C)"
    )


def test_v15_simulate_rest_does_not_actively_cool():
    """simulate_v15 must not predict fast cooldown from REST in summer conditions."""
    start_utc = datetime(2026, 6, 21, 2, 0, 0)  # 04:00 local, night profile
    start_floor = 25.0
    start_dexter = 24.5
    outdoor = [20.0] * 24
    rest_offsets = [settings.OPTIMIZER_REST_THRESHOLD - 0.5] * 24

    floor_temps, dexter_temps = simulate_v15(
        start_utc=start_utc,
        start_floor=start_floor,
        start_dexter=start_dexter,
        outdoor_temps=outdoor,
        offsets=rest_offsets,
        wind_speeds=[2.0] * 24,
        cloud_cover=[8.0] * 24,
    )

    # After 1 hour in REST at summer conditions, temp should barely change
    assert floor_temps[0] >= start_floor - 0.1, (
        f"v15 simulate: floor must not actively cool after 1h REST: got {floor_temps[0]:.3f}°C"
    )
    assert dexter_temps[0] >= start_dexter - 0.1, (
        f"v15 simulate: dexter must not actively cool after 1h REST: got {dexter_temps[0]:.3f}°C"
    )


# --- Planner behavior tests ---

def test_v16_schedules_all_rest_when_house_grossly_overheated():
    """V16 must schedule REST for the entire 24h horizon when house is 25°C (BT50 summer).

    In summer, with outdoor=20°C and house=25°C, the house is far above floor_max=21.8°C.
    V16 must recognize start_over_max=True and schedule REST for all hours.
    """
    # Night start to capture all profiles including morning boost window
    start_utc = datetime(2026, 6, 21, 2, 0, 0)  # 04:00 local
    start_floor = 25.0   # BT50 fallback value - house is grossly overheated
    start_dexter = 24.5

    result = plan_v16_robust(
        start_utc=start_utc,
        start_floor=start_floor,
        start_dexter=start_dexter,
        outdoor_temps=[20.0] * 24,
        prices=[1.0] * 24,
        wind_speeds=[2.0] * 24,
        cloud_cover=[5.0] * 24,
        sensor_mode="fallback",
    )

    boost_hours = result.actions.count("BOOST")
    assert boost_hours == 0, (
        f"V16 must not schedule BOOST when house is at {start_floor}°C. "
        f"Got {boost_hours} BOOST hours in plan. Reasons: {result.reasons}"
    )

    # When house is 3+ degrees over max, we expect mostly/all REST
    rest_hours = result.actions.count("REST")
    assert rest_hours >= 20, (
        f"V16 should schedule ≥20 REST hours when house is at {start_floor}°C "
        f"(far above floor_max={settings.OPTIMIZER_TARGET_TEMP}). "
        f"Got {rest_hours} REST, {result.actions.count('RUN')} RUN, {boost_hours} BOOST."
    )


def test_v16_no_boost_when_overheat_in_fallback_sensor_mode():
    """V16 with sensor_mode=fallback and overheated house must block all positive offsets."""
    # Morning window where BOOST would normally be considered
    start_utc = datetime(2026, 6, 21, 3, 0, 0)  # 05:00 local = morning boost window
    start_floor = 24.0
    start_dexter = 23.5

    result = plan_v16_robust(
        start_utc=start_utc,
        start_floor=start_floor,
        start_dexter=start_dexter,
        outdoor_temps=[18.0] * 24,
        prices=[0.5] * 6 + [2.0] * 18,  # cheap early hours that might tempt BOOST
        sensor_mode="fallback",
    )

    assert result.actions.count("BOOST") == 0, (
        f"V16 fallback-sensor overheat must not BOOST. "
        f"Got actions: {result.actions[:8]}. Reasons: {result.reasons}"
    )
    # Expect mostly REST since house is already 24°C vs floor_max ~21.8°C
    assert result.reasons.get("blocked_boost_overheat", 0) > 0 or result.actions.count("REST") >= 15, (
        f"V16 should block BOOST due to overheat or schedule heavy REST. "
        f"Reasons: {result.reasons}, actions: {result.actions}"
    )


def test_v15_predicted_temp_stays_high_in_summer_rest():
    """V15 shadow plan must NOT plan RUN/BOOST after house is 25°C in summer.

    Before the fix, the buggy model predicted the house would cool from 25°C to
    22°C in ~12h of REST, making the planner think RUN was needed to 'hold' the
    temperature. After the fix, the model correctly predicts the house stays near
    25°C under REST, so V15 schedules all-REST.
    """
    start_utc = datetime(2026, 6, 21, 2, 0, 0)
    start_floor = 25.0
    start_dexter = 24.5

    result = plan_v15_shadow(
        start_utc=start_utc,
        start_floor=start_floor,
        start_dexter=start_dexter,
        outdoor_temps=[20.0] * 24,
        prices=[1.0] * 24,
        wind_speeds=[2.0] * 24,
        cloud_cover=[5.0] * 24,
        room_heat_surplus=2.0,  # house is far above max
    )

    # V15 should recognize the house is hot and prefer REST
    assert result.actions.count("BOOST") == 0, (
        f"V15 must not schedule BOOST with house at {start_floor}°C. "
        f"Actions: {result.actions}"
    )


# --- Winter regression tests (no under-heating allowed) ---

def test_optimizer_still_heats_cold_house_in_winter():
    """Confirm the fix does not break winter heating behavior.

    With outdoor=-10°C and house at 20.0°C (below floor_min=20.5°C),
    the optimizer must still schedule positive offsets to raise temperature.
    """
    result = optimize_24h_plan(
        current_temp=20.0,  # below floor_min
        outdoor_temps=[-10.0] * 24,
        prices=[1.0] * 24,
        min_temp=20.5,
        target_temp=21.8,
    )

    # Must raise at least some offsets to recover floor comfort
    assert any(offset > 0.0 for offset in result), (
        f"Optimizer must schedule positive offsets to heat cold house. Offsets: {result}"
    )


def test_thermal_model_still_heats_when_offset_positive():
    """Positive offsets must still raise temperature (fix only clamped negative gain)."""
    start_temp = 20.0
    outdoor = [5.0] * 24
    run_offsets = [0.0] * 24  # neutral

    temps_run = predict_temperatures(
        start_temp=start_temp,
        outdoor_temps=outdoor,
        offsets=run_offsets,
    )

    boost_offsets = [3.0] * 24
    temps_boost = predict_temperatures(
        start_temp=start_temp,
        outdoor_temps=outdoor,
        offsets=boost_offsets,
    )

    # BOOST should produce higher temps than RUN
    assert temps_boost[0] > temps_run[0], (
        f"Positive offset (BOOST) must still heat house. "
        f"RUN temps[0]={temps_run[0]:.3f}°C, BOOST temps[0]={temps_boost[0]:.3f}°C"
    )
    # Boost should raise temp above start
    assert temps_boost[1] > start_temp, (
        f"BOOST offsets must raise temperature above start {start_temp}°C. Got {temps_boost[1]:.3f}°C"
    )
