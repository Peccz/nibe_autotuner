import os
from datetime import datetime
from datetime import timedelta

os.environ.setdefault("MYUPLINK_CLIENT_ID", "test-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "test-secret")

from core.config import settings
from services.v15_mpc import plan_v15_shadow, plan_v16_robust, simulate_v15
from services.ventilation_guard import VentilationEvent


def test_v15_recovers_cold_morning_without_hiding_behind_heat_in_flight():
    start_utc = datetime(2026, 5, 13, 3, 0, 0)  # 05:00 Europe/Stockholm

    result = plan_v15_shadow(
        start_utc=start_utc,
        start_floor=21.16,
        start_dexter=20.89,
        outdoor_temps=[6.0] * 24,
        prices=[2.0] * 24,
        heat_in_flight=0.4,
    )

    assert any(offset > 0.0 for offset in result.offsets[:3])
    assert min(result.floor_temps[:3]) >= 21.2 - 0.12
    assert min(result.dexter_temps[:3]) >= 20.8 - 0.12


def test_v15_does_not_boost_cheap_night_when_comfort_floors_hold():
    start_utc = datetime(2026, 5, 8, 21, 0, 0)  # 23:00 Europe/Stockholm

    result = plan_v15_shadow(
        start_utc=start_utc,
        start_floor=21.0,
        start_dexter=20.5,
        outdoor_temps=[8.0] * 24,
        prices=[0.1] * 6 + [2.5] * 18,
    )

    # It may recover at 06:00 local for morning comfort, but not preheat during
    # the cheap sleep hours before the morning profile starts.
    assert not any(offset > 0.0 for offset in result.offsets[:5])


def test_v15_sheds_overheated_evening_before_sleep_window():
    start_utc = datetime(2026, 5, 8, 15, 0, 0)  # 17:00 Europe/Stockholm

    result = plan_v15_shadow(
        start_utc=start_utc,
        start_floor=22.0,
        start_dexter=21.4,
        outdoor_temps=[9.0] * 24,
        prices=[1.0] * 24,
        room_heat_surplus=0.8,
    )

    assert any(offset <= settings.OPTIMIZER_REST_THRESHOLD for offset in result.offsets[:5])
    assert min(result.floor_temps) >= 20.3 - 0.1
    assert min(result.dexter_temps) >= 19.8 - 0.1


def test_v15_radiator_cold_case_uses_positive_offset():
    start_utc = datetime(2026, 5, 8, 8, 0, 0)  # 10:00 Europe/Stockholm

    result = plan_v15_shadow(
        start_utc=start_utc,
        start_floor=21.2,
        start_dexter=19.85,
        outdoor_temps=[4.0] * 24,
        prices=[1.0] * 24,
    )

    assert any(offset > 0.0 for offset in result.offsets[:4])
    assert min(result.dexter_temps[:6]) >= 20.0 - 0.12


def test_v15_clear_sun_reduces_heat_need_against_cloudy_forecast():
    start_utc = datetime(2026, 5, 8, 8, 0, 0)  # 10:00 Europe/Stockholm
    kwargs = dict(
        start_utc=start_utc,
        start_floor=20.7,
        start_dexter=20.2,
        outdoor_temps=[12.0] * 24,
        prices=[1.0] * 24,
        wind_speeds=[1.0] * 24,
    )

    sunny = plan_v15_shadow(**kwargs, cloud_cover=[0.0] * 24)
    cloudy = plan_v15_shadow(**kwargs, cloud_cover=[8.0] * 24)

    assert sum(max(0.0, offset) for offset in sunny.offsets) <= sum(
        max(0.0, offset) for offset in cloudy.offsets
    )
    assert min(sunny.floor_temps[2:8]) >= min(cloudy.floor_temps[2:8])


def test_v15_wind_cools_more_than_calm_weather():
    start_utc = datetime(2026, 5, 8, 10, 0, 0)
    offsets = [0.0] * 8

    calm_floor, _ = simulate_v15(
        start_utc=start_utc,
        start_floor=21.2,
        start_dexter=20.6,
        outdoor_temps=[5.0] * 8,
        offsets=offsets,
        wind_speeds=[0.0] * 8,
        cloud_cover=[8.0] * 8,
    )
    windy_floor, _ = simulate_v15(
        start_utc=start_utc,
        start_floor=21.2,
        start_dexter=20.6,
        outdoor_temps=[5.0] * 8,
        offsets=offsets,
        wind_speeds=[8.0] * 8,
        cloud_cover=[8.0] * 8,
    )

    assert windy_floor[-1] < calm_floor[-1]


def test_v15_window_event_caps_local_dexter_recovery():
    start_utc = datetime(2026, 5, 15, 20, 0, 0)  # 22:00 Europe/Stockholm
    event = VentilationEvent(
        zone="dexter",
        started_at=start_utc,
        active_until=start_utc + timedelta(hours=2),
        temp_drop=1.8,
        confidence=0.95,
        current_temp=18.8,
        reference_drop=0.1,
    )

    result = plan_v15_shadow(
        start_utc=start_utc,
        start_floor=21.7,
        start_dexter=18.8,
        outdoor_temps=[9.0] * 24,
        prices=[2.0] * 24,
        ventilation_events=[event],
    )

    assert max(result.offsets[:3]) <= 1.0
    assert result.reasons["ventilation_dexter_hours"] >= 2


def test_v15_recovers_normally_after_window_event_expires():
    start_utc = datetime(2026, 5, 16, 3, 0, 0)  # 05:00 Europe/Stockholm
    event = VentilationEvent(
        zone="dexter",
        started_at=start_utc - timedelta(hours=2),
        active_until=start_utc - timedelta(minutes=10),
        temp_drop=1.8,
        confidence=0.95,
        current_temp=19.2,
        reference_drop=0.1,
    )

    result = plan_v15_shadow(
        start_utc=start_utc,
        start_floor=21.1,
        start_dexter=19.2,
        outdoor_temps=[5.0] * 24,
        prices=[1.0] * 24,
        ventilation_events=[event],
    )

    assert any(offset > 1.0 for offset in result.offsets[:3])


def test_v15_keeps_dexter_at_configured_floor_without_ventilation():
    start_utc = datetime(2026, 5, 19, 18, 0, 0)  # 20:00 Europe/Stockholm

    result = plan_v15_shadow(
        start_utc=start_utc,
        start_floor=22.7,
        start_dexter=22.43,
        outdoor_temps=[13.0, 13.0, 12.5, 12.0, 11.8, 11.5, 11.2, 11.0] + [12.0] * 16,
        prices=[
            2.01, 1.85, 1.79, 1.75, 1.65, 1.68, 1.63, 1.69,
            1.70, 1.92, 2.04, 2.08, 1.83, 1.75, 1.73, 1.59,
            1.31, 1.28, 1.12, 1.60, 1.88, 1.97, 2.13, 2.10,
        ],
        room_heat_surplus=1.6,
        heat_in_flight=1.1,
    )

    assert min(result.dexter_temps) >= settings.DEXTER_MIN_TEMP


def test_v16_overheated_house_sheds_even_when_power_is_cheap():
    start_utc = datetime(2026, 6, 6, 10, 0, 0)  # 12:00 Europe/Stockholm

    result = plan_v16_robust(
        start_utc=start_utc,
        start_floor=23.4,
        start_dexter=23.0,
        outdoor_temps=[18.0] * 24,
        prices=[0.05] * 24,
        cloud_cover=[8.0] * 24,
    )

    assert result.actions[:3].count("REST") >= 2
    assert result.actions.count("BOOST") <= 3
    assert result.offsets[0] <= settings.OPTIMIZER_REST_THRESHOLD


def test_v16_blocks_fallback_price_morning_boost():
    start_utc = datetime(2026, 5, 8, 3, 0, 0)  # 05:00 Europe/Stockholm

    result = plan_v16_robust(
        start_utc=start_utc,
        start_floor=21.4,
        start_dexter=21.0,
        outdoor_temps=[8.0] * 24,
        prices=[1.0] * 24,
        price_fallback_hours={0, 1, 2},
    )

    assert not any(offset > 0.0 for offset in result.offsets[:3])


def test_v16_allows_morning_boost_only_when_floor_would_breach():
    start_utc = datetime(2026, 5, 8, 3, 0, 0)  # 05:00 Europe/Stockholm

    result = plan_v16_robust(
        start_utc=start_utc,
        start_floor=21.05,
        start_dexter=20.65,
        outdoor_temps=[2.0] * 24,
        prices=[1.0] * 24,
    )

    assert any(offset > 0.0 for offset in result.offsets[:3])
    assert result.offsets[0] > 0.0


def test_v16_sensor_fallback_warm_house_prefers_rest_not_recovery():
    start_utc = datetime(2026, 6, 6, 18, 0, 0)  # 20:00 Europe/Stockholm

    result = plan_v16_robust(
        start_utc=start_utc,
        start_floor=22.9,
        start_dexter=22.4,
        outdoor_temps=[18.0] * 24,
        prices=[0.5] * 24,
        sensor_mode="fallback",
    )

    assert result.reasons["sensor_fallback"] == 1
    assert any(action == "REST" for action in result.actions[:4])
    assert result.actions.count("BOOST") <= 1
