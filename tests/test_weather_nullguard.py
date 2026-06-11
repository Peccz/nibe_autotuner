"""Test that a single null hour from Open-Meteo does not drop the whole forecast (#7)."""
from services import weather_service
from services.weather_service import SMHIWeatherService


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_null_hour_is_skipped_not_fatal(monkeypatch):
    # Hour index 1 has null in every secondary field and a null temperature.
    payload = {
        "hourly": {
            "time": ["2026-06-10T00:00", "2026-06-10T01:00", "2026-06-10T02:00"],
            "temperature_2m": [5.0, None, 6.0],
            "precipitation": [0.0, None, 0.1],
            "wind_speed_10m": [10.0, None, 12.0],
            "wind_direction_10m": [180, None, 200],
            "relative_humidity_2m": [80, None, 85],
            "cloud_cover": [50, None, 100],
        }
    }
    monkeypatch.setattr(
        weather_service.requests, "get", lambda *a, **k: _FakeResponse(payload)
    )

    forecasts = SMHIWeatherService().get_forecast(hours_ahead=48)

    # The null-temperature hour is skipped, the two valid hours survive.
    assert len(forecasts) == 2
    assert [round(f.temperature, 1) for f in forecasts] == [5.0, 6.0]


def test_null_secondary_fields_get_safe_defaults(monkeypatch):
    payload = {
        "hourly": {
            "time": ["2026-06-10T00:00"],
            "temperature_2m": [4.0],
            "precipitation": [None],
            "wind_speed_10m": [None],
            "wind_direction_10m": [None],
            "relative_humidity_2m": [None],
            "cloud_cover": [None],
        }
    }
    monkeypatch.setattr(
        weather_service.requests, "get", lambda *a, **k: _FakeResponse(payload)
    )

    forecasts = SMHIWeatherService().get_forecast(hours_ahead=48)
    assert len(forecasts) == 1
    f = forecasts[0]
    assert f.wind_speed == 0.0
    assert f.wind_direction == 0
    assert f.cloud_cover == 8  # 100% default → 8 octas
