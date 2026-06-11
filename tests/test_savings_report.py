"""Tester för besparingsberäkningen (savings_report)."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data.models import Base, Device, Parameter, ParameterReading, System
from data.performance_model import DailyPerformance
from services.savings_report import (
    AVG_POWER_KW,
    INTERVAL_H,
    SavingsResult,
    compute_savings,
    compute_savings_for_day,
    monthly_summary,
)

DAY = datetime(2026, 1, 15)


def _hours(*pairs):
    return {DAY + timedelta(hours=h): v for h, v in pairs}


class TestComputeSavings:
    def test_energy_in_cheap_hours_gives_positive_savings(self):
        # 10 kWh kl 02 (0.50 kr), inget kl 18 (2.50 kr); kallt jämnt ute
        actual = _hours((2, 10.0))
        outdoor = _hours((2, 0.0), (18, 0.0))
        prices = _hours((2, 0.50), (18, 2.50))
        result = compute_savings(actual, outdoor, prices)
        assert result is not None
        assert result.actual_cost_sek == 5.0
        # baseline: lika vikt (samma utetemp) → snittpris 1.50 → 15.0 kr
        assert result.baseline_cost_sek == 15.0
        assert result.savings_sek == 10.0
        assert result.savings_percent == pytest.approx(66.7, abs=0.1)

    def test_energy_in_expensive_hours_gives_negative_savings(self):
        actual = _hours((18, 10.0))
        outdoor = _hours((2, 0.0), (18, 0.0))
        prices = _hours((2, 0.50), (18, 2.50))
        result = compute_savings(actual, outdoor, prices)
        assert result.savings_sek == -10.0

    def test_flat_price_gives_zero_savings(self):
        actual = _hours((2, 5.0), (18, 5.0))
        outdoor = _hours((2, 0.0), (18, 0.0))
        prices = _hours((2, 1.0), (18, 1.0))
        result = compute_savings(actual, outdoor, prices)
        assert result.savings_sek == 0.0

    def test_baseline_weights_follow_heating_demand(self):
        # Kallare timme får större baselinevikt: ute -10 (vikt 27) vs +10 (vikt 7)
        actual = _hours((2, 10.0))
        outdoor = _hours((2, -10.0), (18, 10.0))
        prices = _hours((2, 1.0), (18, 2.0))
        result = compute_savings(actual, outdoor, prices)
        expected_weighted = (27 * 1.0 + 7 * 2.0) / 34
        assert result.baseline_cost_sek == pytest.approx(10 * expected_weighted, abs=0.01)

    def test_warm_day_falls_back_to_uniform_weights(self):
        # Ingen timme under balanstemperaturen → jämn fördelning
        actual = _hours((2, 4.0))
        outdoor = _hours((2, 25.0), (18, 25.0))
        prices = _hours((2, 1.0), (18, 3.0))
        result = compute_savings(actual, outdoor, prices)
        assert result.baseline_cost_sek == pytest.approx(4.0 * 2.0, abs=0.01)

    def test_no_energy_returns_none(self):
        assert compute_savings({}, _hours((2, 0.0)), _hours((2, 1.0))) is None

    def test_insufficient_price_coverage_returns_none(self):
        # 10 kWh men bara 50 % av energin har pris (< 75 %-kravet)
        actual = _hours((2, 5.0), (3, 5.0))
        outdoor = _hours((2, 0.0), (3, 0.0))
        prices = _hours((2, 1.0))
        assert compute_savings(actual, outdoor, prices) is None


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _seed_day(session, comp_hours, outdoor_temp=0.0):
    system = System(system_id="sys1", name="test")
    session.add(system)
    session.flush()
    device = Device(device_id="dev1", system_id=system.id)
    p_comp = Parameter(parameter_id="41778")
    p_out = Parameter(parameter_id="40004")
    session.add_all([device, p_comp, p_out])
    session.flush()
    for h in range(24):
        ts_base = DAY + timedelta(hours=h)
        freq = 60.0 if h in comp_hours else 0.0
        for m in range(0, 60, 5):
            session.add(ParameterReading(
                device_id=device.id, parameter_id=p_comp.id,
                timestamp=ts_base + timedelta(minutes=m), value=freq))
        session.add(ParameterReading(
            device_id=device.id, parameter_id=p_out.id,
            timestamp=ts_base, value=outdoor_temp))
    session.commit()
    return device


class TestComputeSavingsForDay:
    def test_db_day_with_price_lookup(self, session):
        device = _seed_day(session, comp_hours={2, 3})

        def price(hour):
            return 0.5 if hour.hour in (2, 3) else 2.0

        result = compute_savings_for_day(session, device.id, DAY, price_lookup=price)
        assert result is not None
        # 2 timmar × 12 mätningar × 5 min × 1.5 kW = 3.0 kWh
        assert result.actual_kwh == pytest.approx(
            2 * 12 * INTERVAL_H * AVG_POWER_KW, abs=0.01
        )
        assert result.savings_sek > 0  # körde i de billiga timmarna

    def test_db_day_without_readings_returns_none(self, session):
        system = System(system_id="sys1", name="test")
        session.add(system)
        session.flush()
        device = Device(device_id="dev1", system_id=system.id)
        session.add(device)
        session.commit()
        assert compute_savings_for_day(session, device.id, DAY) is None

    def test_price_lookup_returning_none_excludes_hour(self, session):
        device = _seed_day(session, comp_hours={2})

        def price(hour):
            return None  # inga verkliga priser alls

        assert compute_savings_for_day(session, device.id, DAY, price_lookup=price) is None


class TestMonthlySummary:
    def test_aggregates_per_month_and_skips_null_savings(self, session):
        session.add_all([
            DailyPerformance(date=datetime(2026, 1, 1), actual_cost_sek=10.0,
                             baseline_cost_sek=14.0, savings_sek=4.0,
                             savings_percent=28.6, avg_indoor_temp=21.0,
                             avg_outdoor_temp=-2.0),
            DailyPerformance(date=datetime(2026, 1, 2), actual_cost_sek=12.0,
                             baseline_cost_sek=15.0, savings_sek=3.0,
                             savings_percent=20.0, avg_indoor_temp=21.4,
                             avg_outdoor_temp=-1.0),
            DailyPerformance(date=datetime(2026, 1, 3)),  # NULL savings
            DailyPerformance(date=datetime(2026, 2, 1), actual_cost_sek=8.0,
                             baseline_cost_sek=8.0, savings_sek=0.0,
                             savings_percent=0.0),
        ])
        session.commit()
        rows = monthly_summary(session)
        assert [r["month"] for r in rows] == ["2026-01", "2026-02"]
        jan = rows[0]
        assert jan["days"] == 3
        assert jan["days_with_savings"] == 2
        assert jan["savings_sek"] == 7.0
        assert jan["savings_percent"] == pytest.approx(7.0 / 29.0 * 100, abs=0.1)
        assert jan["avg_indoor"] == pytest.approx(21.2, abs=0.01)
