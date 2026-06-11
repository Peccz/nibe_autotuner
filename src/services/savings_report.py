"""
Savings Report - faktisk uppvärmningskostnad vs baseline utan prisoptimering.

Fyller daily_performance-kolumnerna baseline_kwh, baseline_cost_sek,
savings_sek och savings_percent som funnits i schemat sedan start men
aldrig populerats.

Baseline-modell (dokumenterat antagande):
  Samma totala kompressorenergi som faktiskt förbrukades under dygnet,
  men fördelad över dygnets timmar proportionellt mot värmebehovet
  max(0, BALANCE_TEMP - utomhustemp) i stället för mot elpriset.
  Det motsvarar en pump som följer sin värmekurva utan GM-styrning.
  Besparingen mäter alltså ren prisförflyttning vid lika energi —
  inte COP-effekter av att köra vid andra utetemperaturer.

  Varmvattencykler ingår i kompressorenergin på båda sidor; de är i
  praktiken inte prisstyrda, vilket gör att redovisad besparing är
  konservativ (späds ut), inte överskattad.

Kostnadssidan använder samma priskälla som resten av systemet
(planrader eller price_service, totalpris inkl. nät/skatt/moms).
Timmar utan verkligt pris exkluderas från BÅDA sidorna så att
jämförelsen alltid är symmetrisk.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

from loguru import logger

# Balanstemperatur: utetemp där huset inte längre har nettovärmebehov.
BALANCE_TEMP_C = 17.0
# Samma schablon som daily_performance-aggregeringen i data_logger.
AVG_POWER_KW = 1.5
INTERVAL_H = 5.0 / 60.0
# Minsta andel av dygnets energi som måste ha verkligt pris för att
# besparingen ska beräknas (annars None i stället för skev siffra).
MIN_PRICED_ENERGY_SHARE = 0.75


@dataclass(frozen=True)
class SavingsResult:
    actual_kwh: float
    actual_cost_sek: float
    baseline_kwh: float
    baseline_cost_sek: float
    savings_sek: float
    savings_percent: float


def compute_savings(
    actual_kwh_by_hour: Dict[datetime, float],
    outdoor_by_hour: Dict[datetime, float],
    price_by_hour: Dict[datetime, float],
) -> Optional[SavingsResult]:
    """Ren beräkning utan DB-beroende. Nycklarna är timstämplar (hela timmar).

    Returnerar None när underlaget är för tunt (ingen energi, för få
    prissatta timmar eller ingen utomhusdata).
    """
    total_kwh = sum(actual_kwh_by_hour.values())
    if total_kwh <= 0 or not outdoor_by_hour:
        return None

    priced_hours = [
        h for h in actual_kwh_by_hour if h in price_by_hour and h in outdoor_by_hour
    ]
    # Baselinefördelningen behöver alla prissatta timmar med utomhusdata,
    # även de där pumpen faktiskt stod still (dit kan energi flyttas).
    candidate_hours = [
        h for h in price_by_hour if h in outdoor_by_hour
    ]
    priced_kwh = sum(actual_kwh_by_hour.get(h, 0.0) for h in priced_hours)
    if priced_kwh < total_kwh * MIN_PRICED_ENERGY_SHARE or not candidate_hours:
        return None

    actual_cost = sum(
        actual_kwh_by_hour[h] * price_by_hour[h] for h in priced_hours
    )

    weights = {
        h: max(0.0, BALANCE_TEMP_C - outdoor_by_hour[h]) for h in candidate_hours
    }
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        # Sommarfall: inget värmebehov — fördela jämnt (varmvatten m.m.)
        weights = {h: 1.0 for h in candidate_hours}
        weight_sum = float(len(candidate_hours))

    weighted_price = sum(
        weights[h] * price_by_hour[h] for h in candidate_hours
    ) / weight_sum

    baseline_cost = priced_kwh * weighted_price
    savings = baseline_cost - actual_cost
    savings_percent = (savings / baseline_cost * 100.0) if baseline_cost > 0 else 0.0

    return SavingsResult(
        actual_kwh=round(priced_kwh, 2),
        actual_cost_sek=round(actual_cost, 2),
        baseline_kwh=round(priced_kwh, 2),
        baseline_cost_sek=round(baseline_cost, 2),
        savings_sek=round(savings, 2),
        savings_percent=round(savings_percent, 1),
    )


def _hour_floor(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def compute_savings_for_day(
    session,
    device_id: int,
    day_start: datetime,
    price_lookup: Optional[Callable[[datetime], Optional[float]]] = None,
) -> Optional[SavingsResult]:
    """Bygger timunderlag ur parameter_readings och beräknar besparing.

    price_lookup(dt) ska returnera totalpris SEK/kWh för timmen eller None
    när verkligt pris saknas. Default: planrader (electricity_price != 1.0)
    med price_service som fallback för timmar utanför planhistoriken.
    """
    from data.models import Parameter, ParameterReading

    day_end = day_start + timedelta(days=1)

    def readings(pid: str):
        p = session.query(Parameter).filter_by(parameter_id=pid).first()
        if not p:
            return []
        return (
            session.query(ParameterReading)
            .filter(
                ParameterReading.parameter_id == p.id,
                ParameterReading.device_id == device_id,
                ParameterReading.timestamp >= day_start,
                ParameterReading.timestamp < day_end,
            )
            .all()
        )

    comp = readings("41778")
    outdoor = readings("40004")
    if not comp or not outdoor:
        return None

    actual_kwh_by_hour: Dict[datetime, float] = {}
    for r in comp:
        if r.value > 5:
            h = _hour_floor(r.timestamp)
            actual_kwh_by_hour[h] = (
                actual_kwh_by_hour.get(h, 0.0) + INTERVAL_H * AVG_POWER_KW
            )

    outdoor_sums: Dict[datetime, list] = {}
    for r in outdoor:
        h = _hour_floor(r.timestamp)
        outdoor_sums.setdefault(h, []).append(r.value)
    outdoor_by_hour = {h: sum(v) / len(v) for h, v in outdoor_sums.items()}

    if price_lookup is None:
        price_lookup = _default_price_lookup(session)

    price_by_hour: Dict[datetime, float] = {}
    for h in sorted(outdoor_by_hour):
        price = price_lookup(h)
        if price is not None:
            price_by_hour[h] = price

    return compute_savings(actual_kwh_by_hour, outdoor_by_hour, price_by_hour)


def _default_price_lookup(session) -> Callable[[datetime], Optional[float]]:
    """Pris från planhistorik först, annars price_service (API, cache:at).

    Returnerar None för timmar där bara fallbackpriset 1.0 finns, så att
    fallback-timmar aldrig förorenar besparingsstatistiken
    (DNA-fallgrop: fallback 1.0 är inte ett verkligt pris).
    """
    from data.models import PlannedHeatingSchedule

    def lookup(hour: datetime) -> Optional[float]:
        row = (
            session.query(PlannedHeatingSchedule)
            .filter(
                PlannedHeatingSchedule.timestamp >= hour,
                PlannedHeatingSchedule.timestamp < hour + timedelta(hours=1),
                PlannedHeatingSchedule.electricity_price != 1.0,
            )
            .first()
        )
        if row is not None:
            return float(row.electricity_price)
        try:
            from services.price_service import price_service

            details = price_service.get_price_details_at(hour)
            if details.get("spot", 0.0) == 0.0:
                return None  # fallback, inte verkligt pris
            return float(details["total"])
        except Exception as e:  # nätverksfel får aldrig fälla aggregeringen
            logger.warning(f"Price lookup failed for {hour}: {e}")
            return None

    return lookup


def monthly_summary(session) -> list:
    """Aggregerar daily_performance per månad för rapportering.

    Returnerar rader: {month, days, days_with_savings, actual_cost,
    baseline_cost, savings_sek, savings_percent, avg_indoor, avg_outdoor}.
    """
    from data.performance_model import DailyPerformance

    rows = session.query(DailyPerformance).order_by(DailyPerformance.date).all()
    months: Dict[str, dict] = {}
    for r in rows:
        key = r.date.strftime("%Y-%m")
        m = months.setdefault(
            key,
            {
                "month": key,
                "days": 0,
                "days_with_savings": 0,
                "actual_cost": 0.0,
                "baseline_cost": 0.0,
                "savings_sek": 0.0,
                "_indoor": [],
                "_outdoor": [],
            },
        )
        m["days"] += 1
        if r.avg_indoor_temp is not None:
            m["_indoor"].append(r.avg_indoor_temp)
        if r.avg_outdoor_temp is not None:
            m["_outdoor"].append(r.avg_outdoor_temp)
        if r.savings_sek is not None and r.baseline_cost_sek is not None:
            m["days_with_savings"] += 1
            m["actual_cost"] += r.actual_cost_sek or 0.0
            m["baseline_cost"] += r.baseline_cost_sek
            m["savings_sek"] += r.savings_sek

    result = []
    for key in sorted(months):
        m = months[key]
        indoor = m.pop("_indoor")
        outdoor = m.pop("_outdoor")
        m["avg_indoor"] = round(sum(indoor) / len(indoor), 2) if indoor else None
        m["avg_outdoor"] = round(sum(outdoor) / len(outdoor), 2) if outdoor else None
        m["savings_percent"] = (
            round(m["savings_sek"] / m["baseline_cost"] * 100.0, 1)
            if m["baseline_cost"] > 0
            else None
        )
        for f in ("actual_cost", "baseline_cost", "savings_sek"):
            m[f] = round(m[f], 2)
        result.append(m)
    return result
