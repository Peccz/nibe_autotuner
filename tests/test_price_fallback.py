"""Tests for centralized price fallback (#5) and UTC-hardened hour matching (#6)."""
from datetime import datetime, timezone

from services.price_service import PriceService


def _service_with_prices(prices):
    svc = PriceService()
    svc._get_prices_for_date = lambda dt: prices  # bypass network
    return svc


def test_fallback_total_is_the_shared_constant_when_no_prices():
    svc = _service_with_prices([])
    details = svc.get_price_details_at(datetime(2026, 6, 10, 14, tzinfo=timezone.utc))
    assert details["total"] == svc.FALLBACK_PRICE_SEK


def test_fallback_total_is_the_shared_constant_on_exception():
    svc = PriceService()

    def boom(dt):
        raise RuntimeError("network down")

    svc._get_prices_for_date = boom
    details = svc.get_price_details_at(datetime(2026, 6, 10, 14, tzinfo=timezone.utc))
    assert details["total"] == svc.FALLBACK_PRICE_SEK


def test_hour_matching_is_utc_not_naive_local():
    # Price points are in CEST (+02:00). 12:00 UTC == 14:00 local.
    prices = [
        {"time_start": "2026-06-10T13:00:00+02:00", "SEK_per_kWh": 0.30},
        {"time_start": "2026-06-10T14:00:00+02:00", "SEK_per_kWh": 0.55},
        {"time_start": "2026-06-10T15:00:00+02:00", "SEK_per_kWh": 0.80},
    ]
    svc = _service_with_prices(prices)
    details = svc.get_price_details_at(datetime(2026, 6, 10, 12, tzinfo=timezone.utc))
    assert details["spot"] == 0.55  # matched the 14:00 local / 12:00 UTC slot


def test_no_matching_hour_falls_back_to_constant():
    prices = [
        {"time_start": "2026-06-10T14:00:00+02:00", "SEK_per_kWh": 0.55},
    ]
    svc = _service_with_prices(prices)
    # 23:00 UTC has no matching slot in the list → fallback
    details = svc.get_price_details_at(datetime(2026, 6, 10, 23, tzinfo=timezone.utc))
    assert details["total"] == svc.FALLBACK_PRICE_SEK
