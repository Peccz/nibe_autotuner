"""Detect local ventilation disturbances from existing room temperature history."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


VENTILATION_TTL_HOURS = 2.0
MIN_LOCAL_DROP_C = 0.9
MIN_RELATIVE_DROP_C = 0.55
CRITICAL_ZONE_TEMP_C = 18.5


@dataclass(frozen=True)
class ZoneReading:
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class VentilationEvent:
    zone: str
    started_at: datetime
    active_until: datetime
    temp_drop: float
    confidence: float
    current_temp: float
    reference_drop: float

    @property
    def is_active(self) -> bool:
        return self.current_temp > CRITICAL_ZONE_TEMP_C


def _normalize_ts(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def _recent_stats(
    readings: Sequence[ZoneReading],
    now: datetime,
    ttl_hours: float,
) -> Optional[Tuple[float, float, datetime]]:
    now = _normalize_ts(now)
    recent = [
        ZoneReading(_normalize_ts(reading.timestamp), float(reading.value))
        for reading in readings
        if now - _normalize_ts(reading.timestamp) <= timedelta(hours=ttl_hours)
        and _normalize_ts(reading.timestamp) <= now
    ]
    if len(recent) < 2:
        return None

    recent.sort(key=lambda reading: reading.timestamp)
    latest = recent[-1]
    baseline_candidates = [
        reading.value
        for reading in recent[:-1]
        if latest.timestamp - reading.timestamp >= timedelta(minutes=15)
    ]
    if not baseline_candidates:
        baseline_candidates = [reading.value for reading in recent[:-1]]

    baseline = max(baseline_candidates)
    return baseline, latest.value, latest.timestamp


def detect_ventilation_events(
    zone_readings: Mapping[str, Sequence[ZoneReading]],
    now: datetime,
    ttl_hours: float = VENTILATION_TTL_HOURS,
    min_local_drop_c: float = MIN_LOCAL_DROP_C,
    min_relative_drop_c: float = MIN_RELATIVE_DROP_C,
) -> List[VentilationEvent]:
    """Return active local ventilation events for any measured zone.

    The detector intentionally uses relative movement, not absolute comfort.
    A fast drop in one zone is treated as ventilation only when the other
    measured zones/BT50 did not drop by nearly as much.
    """
    stats: Dict[str, Tuple[float, float, datetime]] = {}
    drops: Dict[str, float] = {}
    for zone, readings in zone_readings.items():
        zone_stats = _recent_stats(readings, now, ttl_hours)
        if zone_stats is None:
            continue
        baseline, current, latest_ts = zone_stats
        stats[zone] = zone_stats
        drops[zone] = max(0.0, baseline - current)

    events: List[VentilationEvent] = []
    for zone, drop in drops.items():
        if zone == "bt50" or drop < min_local_drop_c:
            continue
        reference_drop = max((other_drop for other, other_drop in drops.items() if other != zone), default=0.0)
        if drop - reference_drop < min_relative_drop_c:
            continue

        _, current, latest_ts = stats[zone]
        active_until = latest_ts + timedelta(hours=ttl_hours)
        if _normalize_ts(now) > active_until:
            continue

        confidence = min(1.0, 0.55 + (drop - reference_drop) / 2.0)
        events.append(
            VentilationEvent(
                zone=zone,
                started_at=latest_ts,
                active_until=active_until,
                temp_drop=drop,
                confidence=confidence,
                current_temp=current,
                reference_drop=reference_drop,
            )
        )
    return events


def event_by_zone(events: Iterable[VentilationEvent]) -> Dict[str, VentilationEvent]:
    return {event.zone: event for event in events if event.is_active}
