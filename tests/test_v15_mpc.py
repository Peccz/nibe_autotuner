import os
from datetime import datetime

os.environ.setdefault("MYUPLINK_CLIENT_ID", "test-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "test-secret")

from core.config import settings
from services.v15_mpc import plan_v15_shadow, simulate_v15


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
