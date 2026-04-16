from services.outdoor_temperature import (
    effective_outdoor_temp,
    effective_outdoor_temp_from_recent_sensor_values,
)


def test_effective_outdoor_temp_clips_clear_solar_bias():
    assert effective_outdoor_temp(32.0, 14.0) == 16.0


def test_effective_outdoor_temp_keeps_normal_reading():
    assert effective_outdoor_temp(17.0, 14.0) == 17.0


def test_effective_outdoor_temp_keeps_cold_reading():
    assert effective_outdoor_temp(-2.0, 1.0) == -2.0


def test_recent_sensor_fallback_uses_median_as_reference():
    assert effective_outdoor_temp_from_recent_sensor_values([31.0, 17.0, 16.0, 15.0, 16.0]) == 18.0
