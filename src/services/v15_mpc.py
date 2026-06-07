"""V15 shadow planner candidate.

This module keeps the next control model self-contained so it can run in
parallel with the deployed V14 planner before it is allowed to write schedules.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set

from core.config import settings
from services.comfort_profile import comfort_bounds_for_time, to_local
from services.cop_model import COPModel
from services.optimizer import _approx_supply
from services.ventilation_guard import VentilationEvent, event_by_zone


@dataclass(frozen=True)
class V15PlanResult:
    offsets: List[float]
    floor_temps: List[float]
    dexter_temps: List[float]
    actions: List[str]
    score: float
    reasons: Dict[str, int]


def _expand(values: Optional[Sequence[float]], hours: int, default: float) -> List[float]:
    if not values:
        return [default] * hours
    expanded = [float(v) for v in values[:hours]]
    if len(expanded) < hours:
        expanded.extend([expanded[-1] if expanded else default] * (hours - len(expanded)))
    return expanded


def _loss_factors(hours: int) -> List[float]:
    try:
        parsed = [float(x) for x in settings.OPTIMIZER_HOURLY_LOSS_FACTORS.split(",")]
    except Exception:
        parsed = []
    if len(parsed) < hours:
        parsed.extend([1.0] * (hours - len(parsed)))
    return parsed[:hours]


def _wind_loss_factor(wind_speed: float) -> float:
    return 1.0 + min(0.6, max(0.0, wind_speed) * 0.06)


def _solar_gain_for_hour(hour_utc: datetime, cloud_cover: float) -> float:
    local_hour = to_local(hour_utc).hour
    if local_hour < 9 or local_hour > 18:
        return 0.0

    cloud_factor = max(0.0, min(1.0, (8.0 - float(cloud_cover)) / 8.0))
    if 13 <= local_hour <= 17:
        exposure = 1.0
    elif local_hour in (11, 12, 18):
        exposure = 0.65
    else:
        exposure = 0.35
    return 0.10 * cloud_factor * exposure


def _actions_for_offsets(offsets: Sequence[float]) -> List[str]:
    actions = []
    for offset in offsets:
        if offset <= settings.OPTIMIZER_REST_THRESHOLD:
            actions.append("REST")
        elif offset > 0.0:
            actions.append("BOOST")
        else:
            actions.append("RUN")
    return actions


def simulate_v15(
    start_utc: datetime,
    start_floor: float,
    start_dexter: float,
    outdoor_temps: Sequence[float],
    offsets: Sequence[float],
    wind_speeds: Optional[Sequence[float]] = None,
    cloud_cover: Optional[Sequence[float]] = None,
    heat_in_flight: float = 0.0,
    room_heat_surplus: float = 0.0,
    k_leak_floor: Optional[float] = None,
    k_gain_floor: Optional[float] = None,
) -> tuple[List[float], List[float]]:
    """Predict temperatures with lag, wind loss, solar gain and shunt behavior."""
    hours = min(len(outdoor_temps), len(offsets))
    winds = _expand(wind_speeds, hours, 0.0)
    clouds = _expand(cloud_cover, hours, 8.0)
    losses = _loss_factors(hours)

    k_leak_floor = settings.OPTIMIZER_K_LEAK if k_leak_floor is None else k_leak_floor
    k_gain_floor = settings.K_GAIN_FLOOR if k_gain_floor is None else k_gain_floor
    k_leak_dexter = settings.K_LEAK_RADIATOR
    k_gain_dexter = settings.K_GAIN_RADIATOR

    floor = float(start_floor)
    dexter = float(start_dexter)
    floor_mass = floor + max(0.0, room_heat_surplus) * 0.35
    dexter_mass = dexter + max(0.0, room_heat_surplus) * 0.25
    hydronic = max(0.0, float(heat_in_flight or 0.0))

    floor_temps: List[float] = []
    dexter_temps: List[float] = []

    for i in range(hours):
        outdoor = float(outdoor_temps[i])
        offset = float(offsets[i])
        hour = start_utc + timedelta(hours=i)
        wind_factor = _wind_loss_factor(winds[i]) * losses[i]
        solar = _solar_gain_for_hour(hour, clouds[i])
        supply = _approx_supply(outdoor, offset)

        floor_gain = k_gain_floor * offset
        if supply > settings.SHUNT_SETPOINT:
            floor_gain *= 0.60

        dexter_boost = max(0.0, supply - settings.SHUNT_SETPOINT) * settings.RAD_BOOST_FACTOR
        dexter_gain = k_gain_dexter * offset + dexter_boost

        floor_loss = k_leak_floor * wind_factor * (floor - outdoor)
        dexter_loss = k_leak_dexter * wind_factor * (dexter - outdoor)

        # Hydronic lag warms rooms briefly, but decays fast so it cannot mask a
        # real morning floor deficit for several hours.
        floor += floor_gain - floor_loss + solar + hydronic * 0.18
        dexter += dexter_gain - dexter_loss + solar * 0.45 + hydronic * 0.14

        floor_mass += (floor - floor_mass) * 0.18
        dexter_mass += (dexter - dexter_mass) * 0.22
        floor += (floor_mass - floor) * 0.10
        dexter += (dexter_mass - dexter) * 0.08

        hydronic *= 0.45
        floor_temps.append(floor)
        dexter_temps.append(dexter)

    return floor_temps, dexter_temps


def _comfort_profiles(start_utc: datetime, hours: int):
    floor_min = []
    floor_max = []
    dexter_min = []
    dexter_max = []
    boost_allowed: Set[int] = set()
    for i in range(hours):
        bounds = comfort_bounds_for_time(start_utc + timedelta(hours=i))
        floor_min.append(bounds["floor_min"])
        floor_max.append(bounds.get("planning_floor_max", bounds["floor_max"]))
        dexter_min.append(max(bounds["dexter_min"], settings.DEXTER_MIN_TEMP))
        dexter_max.append(bounds.get("planning_dexter_max", bounds["dexter_max"]))
        if bounds["boost_allowed"]:
            boost_allowed.add(i)
    return floor_min, floor_max, dexter_min, dexter_max, boost_allowed


def _floor_deficit_index(floor_temps, dexter_temps, floor_min, dexter_min) -> Optional[int]:
    for i, (floor, dexter) in enumerate(zip(floor_temps, dexter_temps)):
        if floor < floor_min[i] or dexter < dexter_min[i]:
            return i
    return None


def _apply_ventilation_softening(
    start_utc: datetime,
    floor_min: List[float],
    dexter_min: List[float],
    ventilation_events: Optional[Iterable[VentilationEvent]],
) -> tuple[List[float], List[float], Dict[str, int]]:
    softened_floor = list(floor_min)
    softened_dexter = list(dexter_min)
    softened_hours = {"floor": 0, "dexter": 0}
    events = event_by_zone(ventilation_events or [])

    for zone, event in events.items():
        for i in range(len(softened_floor)):
            hour = start_utc + timedelta(hours=i)
            if hour > event.active_until:
                continue
            soft_floor = min(
                floor_min[i] if zone != "floor" else max(event.current_temp + 0.15, 18.5),
                floor_min[i],
            )
            soft_dexter = min(
                dexter_min[i] if zone != "dexter" else max(event.current_temp + 0.15, 18.5),
                dexter_min[i],
            )
            if zone == "floor" and soft_floor < softened_floor[i]:
                softened_floor[i] = soft_floor
                softened_hours["floor"] += 1
            if zone == "dexter" and soft_dexter < softened_dexter[i]:
                softened_dexter[i] = soft_dexter
                softened_hours["dexter"] += 1

    return softened_floor, softened_dexter, softened_hours


def _score_plan(
    offsets: Sequence[float],
    floor_temps: Sequence[float],
    dexter_temps: Sequence[float],
    prices: Sequence[float],
    floor_min: Sequence[float],
    floor_max: Sequence[float],
    dexter_min: Sequence[float],
    dexter_max: Sequence[float],
) -> float:
    score = 0.0
    min_offset = settings.OPTIMIZER_MIN_OFFSET
    for i, offset in enumerate(offsets):
        score += max(0.0, offset - min_offset) * max(0.01, prices[i])

        floor_under = max(0.0, floor_min[i] - floor_temps[i])
        dexter_under = max(0.0, dexter_min[i] - dexter_temps[i])
        floor_over = max(0.0, floor_temps[i] - floor_max[i])
        dexter_over = max(0.0, dexter_temps[i] - dexter_max[i])
        score += (floor_under + dexter_under) * 12000.0
        score += (floor_over * floor_over + dexter_over * dexter_over) * 450.0

        if offset > 0.0:
            score += offset * 0.25
    return score


def _floors_ok(floor_temps, dexter_temps, floor_min, dexter_min, margin: float = 0.0) -> bool:
    return all(
        floor_temps[i] >= floor_min[i] - margin and dexter_temps[i] >= dexter_min[i] - margin
        for i in range(len(floor_temps))
    )


def plan_v15_shadow(
    start_utc: datetime,
    start_floor: float,
    start_dexter: float,
    outdoor_temps: Sequence[float],
    prices: Sequence[float],
    wind_speeds: Optional[Sequence[float]] = None,
    cloud_cover: Optional[Sequence[float]] = None,
    must_run_hours: Optional[Set[int]] = None,
    heat_in_flight: float = 0.0,
    room_heat_surplus: float = 0.0,
    k_leak_floor: Optional[float] = None,
    k_gain_floor: Optional[float] = None,
    ventilation_events: Optional[Iterable[VentilationEvent]] = None,
) -> V15PlanResult:
    """Build a complete V15 candidate plan for logging/backtest only."""
    hours = min(24, len(outdoor_temps), len(prices))
    outdoor = [float(v) for v in outdoor_temps[:hours]]
    price_list = [float(v) for v in prices[:hours]]
    winds = _expand(wind_speeds, hours, 0.0)
    clouds = _expand(cloud_cover, hours, 8.0)
    raw_floor_min, floor_max, raw_dexter_min, dexter_max, boost_allowed = _comfort_profiles(start_utc, hours)
    floor_min, dexter_min, softened_hours = _apply_ventilation_softening(
        start_utc, raw_floor_min, raw_dexter_min, ventilation_events
    )
    ventilation_cap_hours: Set[int] = set()
    for event in event_by_zone(ventilation_events or []).values():
        for i in range(hours):
            if start_utc + timedelta(hours=i) <= event.active_until:
                ventilation_cap_hours.add(i)
    must_run_hours = must_run_hours or set()

    offsets = [0.0] * hours
    reasons: Dict[str, int] = {
        "floor_recovery": 0,
        "shed_overheat": 0,
        "price_shift": 0,
        "ventilation_floor_hours": softened_hours["floor"],
        "ventilation_dexter_hours": softened_hours["dexter"],
    }

    def simulate(test_offsets):
        return simulate_v15(
            start_utc,
            start_floor,
            start_dexter,
            outdoor,
            test_offsets,
            winds,
            clouds,
            heat_in_flight=heat_in_flight,
            room_heat_surplus=room_heat_surplus,
            k_leak_floor=k_leak_floor,
            k_gain_floor=k_gain_floor,
        )

    def recover_candidate(base_offsets):
        candidate_offsets = base_offsets.copy()
        additions = 0
        for _ in range(120):
            floor_temps, dexter_temps = simulate(candidate_offsets)
            bind = _floor_deficit_index(floor_temps, dexter_temps, floor_min, dexter_min)
            if bind is None:
                break

            best_hour = None
            best_score = float("inf")
            start_local_hour = to_local(start_utc + timedelta(hours=bind)).hour
            urgent = bind <= 2 or start_local_hour in (5, 6, 7)
            for h in range(bind + 1):
                if candidate_offsets[h] >= settings.OPTIMIZER_MAX_OFFSET:
                    continue
                if h in ventilation_cap_hours and candidate_offsets[h] >= 1.0:
                    continue
                if h not in boost_allowed and not urgent and bind - h > 2:
                    continue

                water_temp = 30.0 + candidate_offsets[h] * 2.0
                cop = COPModel._interpolate_cop(outdoor[h], water_temp) or 3.0
                delay_penalty = 1.0 + max(0, bind - h) * 0.08
                score = max(0.01, price_list[h]) * delay_penalty / max(1.0, cop)
                if score < best_score:
                    best_score = score
                    best_hour = h

            if best_hour is None:
                break
            candidate_offsets[best_hour] += 1.0
            additions += 1
        return candidate_offsets, additions

    def recover_floors():
        nonlocal offsets
        offsets, additions = recover_candidate(offsets)
        reasons["floor_recovery"] += additions

    def floors_ok_window(floor_temps, dexter_temps, start_hour: int, length: int = 6) -> bool:
        end = min(hours, start_hour + length)
        return all(
            floor_temps[i] >= floor_min[i] and dexter_temps[i] >= dexter_min[i]
            for i in range(start_hour, end)
        )

    # Pass 1: secure floors. Morning comfort is recovered in the morning window
    # or close to the binding hour, not by broad cheap-night preheating.
    recover_floors()

    # Pass 2A: if the house starts above the active upper band, make cooling an
    # explicit control action instead of waiting for the price objective to
    # discover it incrementally.
    start_overheat = max(
        0.0,
        float(start_floor) - floor_max[0],
        float(start_dexter) - dexter_max[0],
        float(room_heat_surplus or 0.0),
    )
    if start_overheat >= 0.3:
        for h in range(min(hours, 6)):
            if h in must_run_hours:
                continue
            forced_target = (
                settings.OPTIMIZER_REST_THRESHOLD
                if h == 0 and start_overheat >= 0.5
                else settings.OPTIMIZER_MIN_OFFSET
            )
            while offsets[h] > settings.OPTIMIZER_MIN_OFFSET:
                candidate = offsets.copy()
                candidate[h] -= 1.0
                cand_floor, cand_dexter = simulate(candidate)
                if floors_ok_window(cand_floor, cand_dexter, h):
                    offsets = candidate
                    reasons["shed_overheat"] += 1
                else:
                    break
                if offsets[h] <= forced_target:
                    break
            floor_temps, dexter_temps = simulate(offsets)
            if floor_temps[h] <= floor_max[h] and dexter_temps[h] <= dexter_max[h]:
                break
        recover_floors()

    # Pass 2: shed overheat and high-price hours while floors stay safe.
    improved = True
    while improved:
        improved = False
        floor_temps, dexter_temps = simulate(offsets)
        overheat_order = sorted(
            range(hours),
            key=lambda h: (
                max(0.0, floor_temps[h] - floor_max[h])
                + max(0.0, dexter_temps[h] - dexter_max[h])
                + max(0.0, price_list[h] - min(price_list))
            ),
            reverse=True,
        )
        for h in overheat_order:
            if offsets[h] <= settings.OPTIMIZER_MIN_OFFSET:
                continue
            candidate = offsets.copy()
            candidate[h] -= 1.0
            if h in must_run_hours and candidate[h] <= settings.OPTIMIZER_REST_THRESHOLD:
                continue
            candidate, recovery_additions = recover_candidate(candidate)
            cand_floor, cand_dexter = simulate(candidate)
            if _floors_ok(cand_floor, cand_dexter, floor_min, dexter_min):
                old_score = _score_plan(offsets, floor_temps, dexter_temps, price_list, floor_min, floor_max, dexter_min, dexter_max)
                new_score = _score_plan(candidate, cand_floor, cand_dexter, price_list, floor_min, floor_max, dexter_min, dexter_max)
                if new_score < old_score:
                    offsets = candidate
                    reasons["floor_recovery"] += recovery_additions
                    if floor_temps[h] > floor_max[h] or dexter_temps[h] > dexter_max[h]:
                        reasons["shed_overheat"] += 1
                    else:
                        reasons["price_shift"] += 1
                    improved = True
                    break

    floor_temps, dexter_temps = simulate(offsets)
    score = _score_plan(offsets, floor_temps, dexter_temps, price_list, floor_min, floor_max, dexter_min, dexter_max)
    return V15PlanResult(
        offsets=offsets,
        floor_temps=floor_temps,
        dexter_temps=dexter_temps,
        actions=_actions_for_offsets(offsets),
        score=score,
        reasons=reasons,
    )


def plan_v16_robust(
    start_utc: datetime,
    start_floor: float,
    start_dexter: float,
    outdoor_temps: Sequence[float],
    prices: Sequence[float],
    wind_speeds: Optional[Sequence[float]] = None,
    cloud_cover: Optional[Sequence[float]] = None,
    must_run_hours: Optional[Set[int]] = None,
    heat_in_flight: float = 0.0,
    room_heat_surplus: float = 0.0,
    k_leak_floor: Optional[float] = None,
    k_gain_floor: Optional[float] = None,
    ventilation_events: Optional[Iterable[VentilationEvent]] = None,
    price_fallback_hours: Optional[Set[int]] = None,
    sensor_mode: str = "normal",
) -> V15PlanResult:
    """Build the V16 live plan: comfort first, overheat shed second, price last."""
    hours = min(24, len(outdoor_temps), len(prices))
    outdoor = [float(v) for v in outdoor_temps[:hours]]
    price_list = [float(v) for v in prices[:hours]]
    winds = _expand(wind_speeds, hours, 0.0)
    clouds = _expand(cloud_cover, hours, 8.0)
    price_fallback_hours = price_fallback_hours or set()
    must_run_hours = must_run_hours or set()

    raw_floor_min, floor_max, raw_dexter_min, dexter_max, boost_allowed = _comfort_profiles(start_utc, hours)
    floor_min, dexter_min, softened_hours = _apply_ventilation_softening(
        start_utc, raw_floor_min, raw_dexter_min, ventilation_events
    )

    ventilation_cap_hours: Set[int] = set()
    for event in event_by_zone(ventilation_events or []).values():
        for i in range(hours):
            if start_utc + timedelta(hours=i) <= event.active_until:
                ventilation_cap_hours.add(i)

    reasons: Dict[str, int] = {
        "morning_recovery": 0,
        "shed_overheat": 0,
        "price_shed": 0,
        "blocked_boost_overheat": 0,
        "blocked_boost_price_fallback": 0,
        "ventilation_floor_hours": softened_hours["floor"],
        "ventilation_dexter_hours": softened_hours["dexter"],
        "sensor_fallback": 1 if sensor_mode == "fallback" else 0,
    }
    seed = plan_v15_shadow(
        start_utc=start_utc,
        start_floor=start_floor,
        start_dexter=start_dexter,
        outdoor_temps=outdoor,
        prices=price_list,
        wind_speeds=winds,
        cloud_cover=clouds,
        must_run_hours=must_run_hours,
        heat_in_flight=heat_in_flight,
        room_heat_surplus=room_heat_surplus,
        k_leak_floor=k_leak_floor,
        k_gain_floor=k_gain_floor,
        ventilation_events=ventilation_events,
    )
    offsets = list(seed.offsets)

    def simulate(test_offsets):
        return simulate_v15(
            start_utc,
            start_floor,
            start_dexter,
            outdoor,
            test_offsets,
            winds,
            clouds,
            heat_in_flight=heat_in_flight,
            room_heat_surplus=room_heat_surplus,
            k_leak_floor=k_leak_floor,
            k_gain_floor=k_gain_floor,
        )

    def floors_hold(test_offsets, start_hour: int = 0, length: Optional[int] = None, margin: float = 0.0) -> bool:
        floor_temps, dexter_temps = simulate(test_offsets)
        end = hours if length is None else min(hours, start_hour + length)
        return all(
            floor_temps[i] >= floor_min[i] - margin and dexter_temps[i] >= dexter_min[i] - margin
            for i in range(start_hour, end)
        )

    start_over_max = start_floor > floor_max[0] + 0.2 or start_dexter > dexter_max[0] + 0.2
    start_overheat = max(
        0.0,
        float(start_floor) - floor_max[0],
        float(start_dexter) - dexter_max[0],
        float(room_heat_surplus or 0.0),
    )

    def shed_hour(hour: int, reason: str) -> bool:
        nonlocal offsets
        if hour >= hours:
            return False
        lower_limit = -2.0 if hour in must_run_hours else settings.OPTIMIZER_MIN_OFFSET
        changed = False
        while offsets[hour] > lower_limit:
            candidate = offsets.copy()
            candidate[hour] = max(lower_limit, candidate[hour] - 1.0)
            if floors_hold(candidate, hour, length=6, margin=0.03):
                offsets = candidate
                reasons[reason] += 1
                changed = True
            else:
                break
        return changed

    # 1. If the house is already warm, force the first hours to shed heat before
    # any cost optimization is considered.
    if start_overheat > 0.2:
        for h in range(min(3, hours)):
            shed_hour(h, "shed_overheat")

    def recover_morning() -> None:
        nonlocal offsets
        if start_over_max:
            reasons["blocked_boost_overheat"] += len(boost_allowed)
            return

        for _ in range(80):
            floor_temps, dexter_temps = simulate(offsets)
            bind = None
            for i, (floor, dexter) in enumerate(zip(floor_temps, dexter_temps)):
                if i not in boost_allowed:
                    continue
                if floor < floor_min[i] or dexter < dexter_min[i]:
                    bind = i
                    break
            if bind is None:
                return

            best_hour = None
            best_score = float("inf")
            for h in sorted(boost_allowed):
                if h > bind or bind - h > 3:
                    continue
                if h in ventilation_cap_hours and offsets[h] >= 1.0:
                    continue
                if h in price_fallback_hours:
                    reasons["blocked_boost_price_fallback"] += 1
                    continue
                if offsets[h] >= settings.OPTIMIZER_MAX_OFFSET:
                    continue
                candidate = offsets.copy()
                candidate[h] += 1.0
                cand_floor, cand_dexter = simulate(candidate)
                remaining_deficit = max(0.0, floor_min[bind] - cand_floor[bind]) + max(
                    0.0, dexter_min[bind] - cand_dexter[bind]
                )
                score = remaining_deficit * 1000.0 + price_list[h]
                if score < best_score:
                    best_score = score
                    best_hour = h

            if best_hour is None:
                return
            offsets[best_hour] += 1.0
            reasons["morning_recovery"] += 1

    # 2. Recover only the explicit morning comfort window. No cheap-night
    # preheat and no fallback-price BOOST.
    recover_morning()

    # 3. Continue reducing heat in over-max and expensive hours as long as the
    # forecast remains above floors after any allowed morning recovery.
    for _ in range(72):
        floor_temps, dexter_temps = simulate(offsets)
        min_price = min(price_list) if price_list else 0.0
        ordered_hours = sorted(
            range(hours),
            key=lambda h: (
                max(0.0, floor_temps[h] - floor_max[h]) * 3.0
                + max(0.0, dexter_temps[h] - dexter_max[h]) * 3.0
                + max(0.0, price_list[h] - min_price),
            ),
            reverse=True,
        )
        changed = False
        for h in ordered_hours:
            if offsets[h] <= settings.OPTIMIZER_MIN_OFFSET:
                continue
            candidate = offsets.copy()
            lower_limit = -2.0 if h in must_run_hours else settings.OPTIMIZER_MIN_OFFSET
            candidate[h] = max(lower_limit, candidate[h] - 1.0)
            if candidate[h] == offsets[h]:
                continue

            candidate_floor, candidate_dexter = simulate(candidate)
            if not _floors_ok(candidate_floor, candidate_dexter, floor_min, dexter_min, margin=0.02):
                continue

            over_now = floor_temps[h] > floor_max[h] or dexter_temps[h] > dexter_max[h]
            price_shed_ok = price_list[h] > min_price and h not in price_fallback_hours
            if over_now or price_shed_ok:
                offsets = candidate
                if over_now:
                    reasons["shed_overheat"] += 1
                else:
                    reasons["price_shed"] += 1
                recover_morning()
                changed = True
                break
        if not changed:
            break

    # Final invariant: V16 never schedules positive offsets outside the morning
    # window, during current overheat, during active ventilation caps, or on
    # fallback price hours.
    for h, offset in enumerate(list(offsets)):
        if offset <= 0.0:
            continue
        blocked = (
            h not in boost_allowed
            or start_over_max
            or h in ventilation_cap_hours
            or h in price_fallback_hours
        )
        if blocked:
            candidate = offsets.copy()
            candidate[h] = 0.0
            cand_floor, cand_dexter = simulate(candidate)
            if _floors_ok(cand_floor, cand_dexter, floor_min, dexter_min, margin=0.02):
                offsets = candidate
                if start_over_max:
                    reasons["blocked_boost_overheat"] += 1
                if h in price_fallback_hours:
                    reasons["blocked_boost_price_fallback"] += 1

    floor_temps, dexter_temps = simulate(offsets)
    score = _score_plan(offsets, floor_temps, dexter_temps, price_list, floor_min, floor_max, dexter_min, dexter_max)
    return V15PlanResult(
        offsets=offsets,
        floor_temps=floor_temps,
        dexter_temps=dexter_temps,
        actions=_actions_for_offsets(offsets),
        score=score,
        reasons=reasons,
    )


def compare_shadow_summary(
    v14_offsets: Sequence[float],
    v15: V15PlanResult,
    prices: Sequence[float],
) -> Dict[str, float]:
    hours = min(len(v14_offsets), len(v15.offsets), len(prices))
    if hours == 0:
        return {}

    def weighted_price(offsets):
        load = [max(0.0, float(offset) - settings.OPTIMIZER_MIN_OFFSET) for offset in offsets[:hours]]
        total_load = sum(load)
        if total_load <= 0.0:
            return 0.0
        return sum(load[i] * float(prices[i]) for i in range(hours)) / total_load

    return {
        "v14_rest": sum(1 for offset in v14_offsets[:hours] if offset <= settings.OPTIMIZER_REST_THRESHOLD),
        "v15_rest": v15.actions[:hours].count("REST"),
        "v14_boost": sum(1 for offset in v14_offsets[:hours] if offset > 0.0),
        "v15_boost": v15.actions[:hours].count("BOOST"),
        "v15_min_floor": min(v15.floor_temps[:hours]),
        "v15_min_dexter": min(v15.dexter_temps[:hours]),
        "v14_weighted_price": weighted_price(v14_offsets),
        "v15_weighted_price": weighted_price(v15.offsets),
        "v15_score": v15.score,
    }
