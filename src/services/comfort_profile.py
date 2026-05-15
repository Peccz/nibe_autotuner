"""Time-of-day comfort profile shared by planner and GM controller."""
from datetime import datetime
from zoneinfo import ZoneInfo


LOCAL_TZ = ZoneInfo("Europe/Stockholm")

DAY_FLOOR_MIN_C = 20.5
DAY_FLOOR_MAX_C = 21.8
DAY_DEXTER_MIN_C = 20.0
DAY_DEXTER_MAX_C = 21.3

NIGHT_FLOOR_MIN_C = 20.3
NIGHT_FLOOR_MAX_C = 21.2
NIGHT_DEXTER_MIN_C = 19.8
NIGHT_DEXTER_MAX_C = 20.8

MORNING_FLOOR_MIN_C = 21.2
MORNING_FLOOR_MAX_C = 21.8
MORNING_DEXTER_MIN_C = 20.8
MORNING_DEXTER_MAX_C = 21.3

MORNING_START_HOUR = 5
MORNING_END_HOUR = 8
EVENING_PRESHED_START_HOUR = 17
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 6


def to_local(dt: datetime) -> datetime:
    """Convert aware/naive UTC datetimes to Europe/Stockholm local time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(LOCAL_TZ)


def comfort_bounds_for_time(dt: datetime) -> dict:
    local = to_local(dt)
    hour = local.hour

    planning_floor_max = DAY_FLOOR_MAX_C
    planning_dexter_max = DAY_DEXTER_MAX_C

    if MORNING_START_HOUR <= hour < MORNING_END_HOUR:
        profile = "morning"
        floor_min = MORNING_FLOOR_MIN_C
        floor_max = MORNING_FLOOR_MAX_C
        dexter_min = MORNING_DEXTER_MIN_C
        dexter_max = MORNING_DEXTER_MAX_C
        planning_floor_max = MORNING_FLOOR_MAX_C
        planning_dexter_max = MORNING_DEXTER_MAX_C
    elif hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR:
        profile = "night"
        floor_min = NIGHT_FLOOR_MIN_C
        floor_max = NIGHT_FLOOR_MAX_C
        dexter_min = NIGHT_DEXTER_MIN_C
        dexter_max = NIGHT_DEXTER_MAX_C
        planning_floor_max = NIGHT_FLOOR_MAX_C
        planning_dexter_max = NIGHT_DEXTER_MAX_C
    elif hour >= EVENING_PRESHED_START_HOUR:
        profile = "evening_preshed"
        floor_min = DAY_FLOOR_MIN_C
        floor_max = DAY_FLOOR_MAX_C
        dexter_min = DAY_DEXTER_MIN_C
        dexter_max = DAY_DEXTER_MAX_C
        planning_floor_max = NIGHT_FLOOR_MAX_C
        planning_dexter_max = NIGHT_DEXTER_MAX_C
    else:
        profile = "day"
        floor_min = DAY_FLOOR_MIN_C
        floor_max = DAY_FLOOR_MAX_C
        dexter_min = DAY_DEXTER_MIN_C
        dexter_max = DAY_DEXTER_MAX_C

    return {
        "profile": profile,
        "floor_min": floor_min,
        "floor_max": floor_max,
        "dexter_min": dexter_min,
        "dexter_max": dexter_max,
        "planning_floor_max": planning_floor_max,
        "planning_dexter_max": planning_dexter_max,
        "boost_allowed": MORNING_START_HOUR <= hour < MORNING_END_HOUR,
    }
