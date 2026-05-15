import os
import sqlite3
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MYUPLINK_CLIENT_ID", "test-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "test-secret")

from core.config import settings
from services.optimizer import optimize_24h_plan, predict_temperatures_two_zone
from services.smart_planner import (
    _build_comfort_profiles,
    _calculate_heat_in_flight,
    _calculate_room_heat_surplus,
    _get_vv_must_run_hours,
    _resolve_zone_temperatures,
    DEXTER_COMFORT_MAX_C,
    DEXTER_COMFORT_MIN_C,
    FLOOR_COMFORT_MAX_C,
    FLOOR_COMFORT_MIN_C,
)
from services.comfort_profile import comfort_bounds_for_time


def test_optimizer_creates_rest_when_house_starts_above_upper_band():
    outdoor = [14.0] * 24
    prices = [1.0] * 24

    offsets = optimize_24h_plan(
        current_temp=22.4,
        outdoor_temps=outdoor,
        prices=prices,
        min_temp=FLOOR_COMFORT_MIN_C,
        target_temp=FLOOR_COMFORT_MAX_C,
        current_radiator_temp=21.7,
        min_radiator_temp=DEXTER_COMFORT_MIN_C,
        target_radiator_temp=DEXTER_COMFORT_MAX_C,
    )
    floor_temps, dexter_temps = predict_temperatures_two_zone(22.4, 21.7, outdoor, offsets)

    assert any(offset <= -2.5 for offset in offsets)
    assert min(floor_temps) >= FLOOR_COMFORT_MIN_C
    assert min(dexter_temps) >= DEXTER_COMFORT_MIN_C


def test_time_profile_has_sval_natt_and_early_morning_warmth():
    night = comfort_bounds_for_time(datetime(2026, 5, 8, 21, 30, tzinfo=timezone.utc))
    morning = comfort_bounds_for_time(datetime(2026, 5, 8, 4, 30, tzinfo=timezone.utc))

    assert night["profile"] == "night"
    assert night["floor_max"] == 21.2
    assert night["dexter_max"] == 20.8
    assert morning["profile"] == "morning"
    assert morning["floor_min"] == 21.2
    assert morning["dexter_min"] == 20.8


def test_evening_preshed_uses_night_upper_band_for_planning():
    evening = comfort_bounds_for_time(datetime(2026, 5, 8, 16, 30, tzinfo=timezone.utc))

    assert evening["profile"] == "evening_preshed"
    assert evening["floor_min"] == 20.5
    assert evening["floor_max"] == 21.8
    assert evening["planning_floor_max"] == 21.2
    assert evening["planning_dexter_max"] == 20.8
    assert evening["boost_allowed"] is False


def test_room_heat_surplus_uses_planning_upper_band():
    evening = comfort_bounds_for_time(datetime(2026, 5, 8, 16, 30, tzinfo=timezone.utc))

    surplus = _calculate_room_heat_surplus(21.9, 21.1, evening)

    assert round(surplus, 2) == 0.70


def test_profiled_optimizer_sheds_heat_through_night_without_floor_breach():
    start_utc = datetime(2026, 5, 8, 18, 0, 0)  # 20:00 Europe/Stockholm
    floor_min, floor_max, dexter_min, dexter_max, boost_allowed, _ = _build_comfort_profiles(start_utc, 24)

    offsets = optimize_24h_plan(
        current_temp=23.5,
        outdoor_temps=[6.0] * 24,
        prices=[1.0] * 24,
        min_temp=floor_min,
        target_temp=floor_max,
        current_radiator_temp=22.8,
        min_radiator_temp=dexter_min,
        target_radiator_temp=dexter_max,
        boost_allowed_hours=boost_allowed,
    )
    floor_temps, dexter_temps = predict_temperatures_two_zone(23.5, 22.8, [6.0] * 24, offsets)

    assert any(offset <= -2.5 for offset in offsets[:8])
    assert all(temp >= floor_min[i] - 0.1 for i, temp in enumerate(floor_temps))
    assert all(temp >= dexter_min[i] - 0.1 for i, temp in enumerate(dexter_temps))
    assert not any(offset > 0.0 for i, offset in enumerate(offsets) if i not in boost_allowed)


def test_evening_room_heat_surplus_starts_preshed_before_sleep_window():
    start_utc = datetime(2026, 5, 8, 15, 0, 0)  # 17:00 Europe/Stockholm
    floor_min, floor_max, dexter_min, dexter_max, boost_allowed, _ = _build_comfort_profiles(start_utc, 24)

    offsets = optimize_24h_plan(
        current_temp=21.9,
        outdoor_temps=[8.0] * 24,
        prices=[1.0] * 24,
        min_temp=floor_min,
        target_temp=floor_max,
        current_radiator_temp=21.8,
        min_radiator_temp=dexter_min,
        target_radiator_temp=dexter_max,
        boost_allowed_hours=boost_allowed,
        room_heat_surplus=0.7,
    )

    assert any(offset < 0.0 for offset in offsets[:4])
    floor_temps, dexter_temps = predict_temperatures_two_zone(21.9, 21.8, [8.0] * 24, offsets)
    assert all(temp >= floor_min[i] - 0.1 for i, temp in enumerate(floor_temps[:4]))
    assert all(temp >= dexter_min[i] - 0.1 for i, temp in enumerate(dexter_temps[:4]))


def test_cheap_night_does_not_boost_before_morning_window_when_floors_hold():
    start_utc = datetime(2026, 5, 8, 21, 0, 0)  # 23:00 Europe/Stockholm
    floor_min, floor_max, dexter_min, dexter_max, boost_allowed, _ = _build_comfort_profiles(start_utc, 24)
    prices = [0.1] * 6 + [2.5] * 18

    offsets = optimize_24h_plan(
        current_temp=20.9,
        outdoor_temps=[8.0] * 24,
        prices=prices,
        min_temp=floor_min,
        target_temp=floor_max,
        current_radiator_temp=20.4,
        min_radiator_temp=dexter_min,
        target_radiator_temp=dexter_max,
        boost_allowed_hours=boost_allowed,
    )

    assert not any(offset > 0.0 for i, offset in enumerate(offsets) if i not in boost_allowed)


def test_overheated_evening_gets_immediate_night_shedding():
    start_utc = datetime(2026, 5, 8, 18, 0, 0)  # 20:00 Europe/Stockholm
    floor_min, floor_max, dexter_min, dexter_max, boost_allowed, _ = _build_comfort_profiles(start_utc, 24)

    offsets = optimize_24h_plan(
        current_temp=23.4,
        outdoor_temps=[6.0] * 24,
        prices=[1.0] * 24,
        min_temp=floor_min,
        target_temp=floor_max,
        current_radiator_temp=22.0,
        min_radiator_temp=dexter_min,
        target_radiator_temp=dexter_max,
        boost_allowed_hours=boost_allowed,
    )
    floor_temps, dexter_temps = predict_temperatures_two_zone(23.4, 22.0, [6.0] * 24, offsets)

    assert offsets[0] < 0.0
    assert any(offset <= -2.5 for offset in offsets[:2])
    assert all(temp >= floor_min[i] - 0.1 for i, temp in enumerate(floor_temps))
    assert all(temp >= dexter_min[i] - 0.1 for i, temp in enumerate(dexter_temps))


def test_overheated_evening_uses_mild_negative_offset_when_rest_is_blocked():
    start_utc = datetime(2026, 5, 8, 18, 0, 0)  # 20:00 Europe/Stockholm
    floor_min, floor_max, dexter_min, dexter_max, boost_allowed, _ = _build_comfort_profiles(start_utc, 24)

    offsets = optimize_24h_plan(
        current_temp=23.4,
        outdoor_temps=[6.0] * 24,
        prices=[1.0] * 24,
        min_temp=floor_min,
        target_temp=floor_max,
        current_radiator_temp=22.0,
        min_radiator_temp=dexter_min,
        target_radiator_temp=dexter_max,
        must_run_hours={0},
        boost_allowed_hours=boost_allowed,
    )

    assert settings.OPTIMIZER_REST_THRESHOLD < offsets[0] < 0.0


def test_profiled_optimizer_allows_early_morning_boost_when_needed():
    start_utc = datetime(2026, 5, 8, 2, 0, 0)  # 04:00 Europe/Stockholm
    floor_min, floor_max, dexter_min, dexter_max, boost_allowed, _ = _build_comfort_profiles(start_utc, 24)

    offsets = optimize_24h_plan(
        current_temp=21.0,
        outdoor_temps=[4.0] * 24,
        prices=[1.0] * 24,
        min_temp=floor_min,
        target_temp=floor_max,
        current_radiator_temp=20.6,
        min_radiator_temp=dexter_min,
        target_radiator_temp=dexter_max,
        boost_allowed_hours=boost_allowed,
    )

    assert any(offset > 0.0 for i, offset in enumerate(offsets) if i in boost_allowed)


def test_heat_in_flight_does_not_block_morning_floor_recovery():
    start_utc = datetime(2026, 5, 13, 3, 0, 0)  # 05:00 Europe/Stockholm
    floor_min, floor_max, dexter_min, dexter_max, boost_allowed, _ = _build_comfort_profiles(start_utc, 24)

    offsets = optimize_24h_plan(
        current_temp=21.16,
        outdoor_temps=[6.0] * 24,
        prices=[2.0] * 24,
        min_temp=floor_min,
        target_temp=floor_max,
        current_radiator_temp=20.89,
        min_radiator_temp=dexter_min,
        target_radiator_temp=dexter_max,
        boost_allowed_hours=boost_allowed,
        heat_in_flight=0.4,
    )
    floor_temps, dexter_temps = predict_temperatures_two_zone(21.16, 20.89, [6.0] * 24, offsets)

    assert any(offset > 0.0 for i, offset in enumerate(offsets[:3]) if i in boost_allowed)
    assert all(temp >= floor_min[i] - 0.12 for i, temp in enumerate(floor_temps[:3]))
    assert all(temp >= dexter_min[i] - 0.1 for i, temp in enumerate(dexter_temps[:3]))


def test_heat_in_flight_starts_shedding_before_night_profile():
    start_utc = datetime(2026, 5, 8, 15, 0, 0)  # 17:00 Europe/Stockholm
    floor_min, floor_max, dexter_min, dexter_max, boost_allowed, _ = _build_comfort_profiles(start_utc, 24)

    offsets = optimize_24h_plan(
        current_temp=21.7,
        outdoor_temps=[8.0] * 24,
        prices=[1.0] * 24,
        min_temp=floor_min,
        target_temp=floor_max,
        current_radiator_temp=21.1,
        min_radiator_temp=dexter_min,
        target_radiator_temp=dexter_max,
        boost_allowed_hours=boost_allowed,
        heat_in_flight=0.7,
    )

    assert any(offset < 0.0 for offset in offsets[:4])


def test_profiled_optimizer_does_not_boost_when_already_overheated():
    start_utc = datetime(2026, 5, 8, 2, 0, 0)  # 04:00 Europe/Stockholm
    floor_min, floor_max, dexter_min, dexter_max, boost_allowed, _ = _build_comfort_profiles(start_utc, 24)

    offsets = optimize_24h_plan(
        current_temp=23.0,
        outdoor_temps=[8.0] * 24,
        prices=[0.1] * 24,
        min_temp=floor_min,
        target_temp=floor_max,
        current_radiator_temp=22.5,
        min_radiator_temp=dexter_min,
        target_radiator_temp=dexter_max,
        boost_allowed_hours=boost_allowed,
    )

    assert not any(offset > 0.0 for offset in offsets)


def test_optimizer_treats_upper_band_as_overheat_penalty_not_floor():
    outdoor = [10.0] * 24
    prices = [1.0] * 24

    offsets = optimize_24h_plan(
        current_temp=21.0,
        outdoor_temps=outdoor,
        prices=prices,
        min_temp=FLOOR_COMFORT_MIN_C,
        target_temp=FLOOR_COMFORT_MAX_C,
        current_radiator_temp=20.4,
        min_radiator_temp=DEXTER_COMFORT_MIN_C,
        target_radiator_temp=DEXTER_COMFORT_MAX_C,
    )
    floor_temps, dexter_temps = predict_temperatures_two_zone(21.0, 20.4, outdoor, offsets)

    assert min(floor_temps) >= FLOOR_COMFORT_MIN_C
    assert min(dexter_temps) >= DEXTER_COMFORT_MIN_C
    assert min(floor_temps) < FLOOR_COMFORT_MAX_C


def _make_hw_conn():
    conn = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute("""
        CREATE TABLE hot_water_usage (
            start_time timestamp,
            end_time timestamp,
            duration_minutes integer,
            weekday integer,
            hour integer
        )
    """)
    return conn


def test_vv_preheat_ignores_weak_patterns_and_caps_blocks():
    now = datetime(2026, 5, 7, 0, 0, 0)
    conn = _make_hw_conn()

    # Weak: only two observations, should not block.
    for _ in range(2):
        conn.execute(
            "INSERT INTO hot_water_usage VALUES (?, ?, ?, ?, ?)",
            (now, now + timedelta(minutes=20), 20, now.weekday(), 3),
        )

    # Strong patterns across many hours; result is capped to four blocked hours.
    for hour in range(5, 11):
        for _ in range(3):
            conn.execute(
                "INSERT INTO hot_water_usage VALUES (?, ?, ?, ?, ?)",
                (now, now + timedelta(minutes=20), 20, now.weekday(), hour),
            )

    blocked = _get_vv_must_run_hours(conn, now)

    assert 3 not in blocked
    assert len(blocked) <= 4
    assert blocked


def _make_sensor_conn(now):
    conn = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute("CREATE TABLE parameters (id integer primary key, parameter_id text)")
    conn.execute("""
        CREATE TABLE parameter_readings (
            parameter_id integer,
            timestamp timestamp,
            value real
        )
    """)
    for idx, parameter_id in enumerate(["HA_TEMP_DOWNSTAIRS", "HA_TEMP_DEXTER", "40033"], start=1):
        conn.execute("INSERT INTO parameters VALUES (?, ?)", (idx, parameter_id))

    historical = now - timedelta(days=1)
    conn.execute("INSERT INTO parameter_readings VALUES (1, ?, ?)", (historical, 21.0))
    conn.execute("INSERT INTO parameter_readings VALUES (2, ?, ?)", (historical, 20.2))
    conn.execute("INSERT INTO parameter_readings VALUES (3, ?, ?)", (historical, 20.8))

    stale = now - timedelta(hours=2)
    conn.execute("INSERT INTO parameter_readings VALUES (1, ?, ?)", (stale, 22.8))
    conn.execute("INSERT INTO parameter_readings VALUES (2, ?, ?)", (stale, 22.0))

    fresh = now - timedelta(minutes=5)
    conn.execute("INSERT INTO parameter_readings VALUES (3, ?, ?)", (fresh, 20.9))
    return conn


def test_stale_ha_sensors_fallback_to_bt50_and_historical_zone_gap():
    now = datetime(2026, 5, 7, 12, 0, 0)
    conn = _make_sensor_conn(now)

    downstairs, dexter, sensor_mode = _resolve_zone_temperatures(conn, now, FLOOR_COMFORT_MAX_C)

    assert sensor_mode == "fallback"
    assert round(downstairs, 2) == 21.10
    assert round(dexter, 2) == 20.30


def test_heat_in_flight_uses_recent_supply_and_boost_history():
    now = datetime(2026, 5, 11, 10, 0, 0)
    conn = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute("""
        CREATE TABLE gm_transactions (
            timestamp timestamp,
            supply_actual real,
            supply_target real,
            action text,
            gm_written integer
        )
    """)
    conn.execute("""
        CREATE TABLE planned_heating_schedule (
            timestamp timestamp,
            planned_offset real
        )
    """)
    for minutes_ago in (10, 20, 30):
        conn.execute(
            "INSERT INTO gm_transactions VALUES (?, ?, ?, ?, ?)",
            (now - timedelta(minutes=minutes_ago), 48.0, 30.0, "BOOST", -350),
        )
    conn.execute(
        "INSERT INTO planned_heating_schedule VALUES (?, ?)",
        (now - timedelta(hours=1), 3.0),
    )

    heat_in_flight = _calculate_heat_in_flight(conn, now)

    assert heat_in_flight >= 1.0
