from datetime import datetime, timedelta

from services.ventilation_guard import ZoneReading, detect_ventilation_events


def _series(start, values):
    return [
        ZoneReading(timestamp=start + timedelta(minutes=15 * index), value=value)
        for index, value in enumerate(values)
    ]


def test_detects_local_dexter_window_drop():
    start = datetime(2026, 5, 15, 20, 0, 0)
    now = start + timedelta(minutes=60)

    events = detect_ventilation_events(
        {
            "floor": _series(start, [21.7, 21.7, 21.6, 21.6, 21.6]),
            "dexter": _series(start, [20.6, 20.1, 19.4, 18.9, 18.8]),
            "bt50": _series(start, [21.5, 21.5, 21.5, 21.5, 21.5]),
        },
        now,
    )

    assert len(events) == 1
    assert events[0].zone == "dexter"
    assert events[0].temp_drop >= 1.7


def test_detects_local_downstairs_window_drop():
    start = datetime(2026, 5, 15, 20, 0, 0)
    now = start + timedelta(minutes=60)

    events = detect_ventilation_events(
        {
            "floor": _series(start, [21.7, 21.1, 20.7, 20.4, 20.3]),
            "dexter": _series(start, [20.8, 20.8, 20.7, 20.7, 20.7]),
            "bt50": _series(start, [21.4, 21.4, 21.4, 21.4, 21.4]),
        },
        now,
    )

    assert len(events) == 1
    assert events[0].zone == "floor"


def test_whole_house_cooling_is_not_classified_as_window_open():
    start = datetime(2026, 5, 15, 20, 0, 0)
    now = start + timedelta(minutes=60)

    events = detect_ventilation_events(
        {
            "floor": _series(start, [21.7, 21.3, 20.9, 20.6, 20.4]),
            "dexter": _series(start, [20.8, 20.3, 19.9, 19.6, 19.4]),
            "bt50": _series(start, [21.4, 21.0, 20.7, 20.4, 20.2]),
        },
        now,
    )

    assert events == []


def test_critical_zone_temperature_disables_ventilation_event():
    start = datetime(2026, 5, 15, 20, 0, 0)
    now = start + timedelta(minutes=60)

    events = detect_ventilation_events(
        {
            "floor": _series(start, [21.7, 21.7, 21.7, 21.7, 21.7]),
            "dexter": _series(start, [20.6, 19.6, 18.6, 18.1, 18.0]),
            "bt50": _series(start, [21.5, 21.5, 21.5, 21.5, 21.5]),
        },
        now,
    )

    assert len(events) == 1
    assert events[0].is_active is False
