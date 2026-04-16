"""Outdoor temperature filtering for sun-exposed BT1 readings."""

from statistics import median
from typing import Optional, Sequence

SOLAR_BIAS_TRIGGER_C = 4.0
SOLAR_BIAS_MAX_DELTA_C = 2.0
SOLAR_SENSOR_MIN_C = 15.0


def effective_outdoor_temp(
    sensor_temp: Optional[float],
    reference_temp: Optional[float] = None,
    *,
    bias_trigger_c: float = SOLAR_BIAS_TRIGGER_C,
    max_delta_c: float = SOLAR_BIAS_MAX_DELTA_C,
    sensor_min_c: float = SOLAR_SENSOR_MIN_C,
) -> Optional[float]:
    """Return outdoor temp for control, damping clear sun bias on BT1.

    BT1/40004 is mounted on a west-facing facade. When it is much warmer than
    a weather/reference temperature, treat the excess as facade/solar bias but
    still allow BT1 to sit slightly above the reference because that is what
    the pump physically sees.
    """
    if sensor_temp is None:
        return reference_temp
    if reference_temp is None:
        return sensor_temp

    sensor = float(sensor_temp)
    reference = float(reference_temp)
    if sensor >= sensor_min_c and sensor - reference > bias_trigger_c:
        return reference + max_delta_c
    return sensor


def effective_outdoor_temp_from_recent_sensor_values(
    values_newest_first: Sequence[float],
) -> Optional[float]:
    """Fallback filter when only recent BT1 values are available.

    Uses the recent median as a local reference, which catches short solar
    spikes without requiring network weather data.
    """
    values = [float(v) for v in values_newest_first if v is not None]
    if not values:
        return None
    return effective_outdoor_temp(values[0], median(values))
