"""
Deterministic Optimizer V14.0 — Two-Zone Model
Two-pass algorithm: enforce comfort floor for both zones, then minimize cost.

Zone 1 (floor): ground floor, underfloor heating with shunt (buffered).
Zone 2 (radiator): upper floors (Dexter's room + top floor), direct radiators.

Physics: raising supply above SHUNT_SETPOINT causes the shunt to limit floor flow,
routing the excess to radiators. Below that temperature, radiators get less benefit.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from typing import List, Optional, Sequence, Tuple
from loguru import logger

from core.config import settings
from services.cop_model import COPModel


def _get_hourly_loss_factors(hours: int) -> List[float]:
    """Parse OPTIMIZER_HOURLY_LOSS_FACTORS from config, padded/trimmed to hours."""
    try:
        factors = [float(x) for x in settings.OPTIMIZER_HOURLY_LOSS_FACTORS.split(',')]
        if len(factors) >= hours:
            return factors[:hours]
        return factors + [1.0] * (hours - len(factors))
    except Exception:
        return [1.0] * hours


def _approx_supply(outdoor: float, offset: float) -> float:
    """Approximate supply temperature from outdoor temp and offset."""
    return 20.0 + (20.0 - outdoor) * settings.DEFAULT_HEATING_CURVE * 0.12 + offset


def _expand_bounds(value, hours: int, default: float) -> List[float]:
    if value is None:
        return [default] * hours
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = [float(v) for v in value]
        if len(values) >= hours:
            return values[:hours]
        return values + [values[-1] if values else default] * (hours - len(values))
    return [float(value)] * hours


def predict_temperatures(
    start_temp: float,
    outdoor_temps: List[float],
    offsets: List[float],
    loss_factors: Optional[List[float]] = None,
    k_leak: Optional[float] = None,
    k_gain: Optional[float] = None,
) -> List[float]:
    """
    Single-zone simulation (floor zone). Used for backwards compatibility
    and as the primary constraint in the optimizer.
    k_leak / k_gain: override config defaults with calibrated values if provided.
    """
    if loss_factors is None:
        loss_factors = _get_hourly_loss_factors(len(offsets))

    k_leak = k_leak if k_leak is not None else settings.OPTIMIZER_K_LEAK
    k_gain = k_gain if k_gain is not None else settings.K_GAIN_FLOOR

    temps = []
    current_temp = start_temp

    for i in range(len(offsets)):
        outdoor = outdoor_temps[i]
        offset = offsets[i]
        lf = loss_factors[i] if i < len(loss_factors) else 1.0

        delta_t = current_temp - outdoor
        loss = k_leak * lf * delta_t
        gain = k_gain * offset

        current_temp = current_temp - loss + gain
        temps.append(current_temp)

    return temps


def predict_temperatures_two_zone(
    start_floor: float,
    start_radiator: float,
    outdoor_temps: List[float],
    offsets: List[float],
    loss_factors: Optional[List[float]] = None,
    k_leak_floor: Optional[float] = None,
    k_gain_floor: Optional[float] = None,
) -> Tuple[List[float], List[float]]:
    """
    Two-zone simulation: floor heating zone (downstairs) and radiator zone (Dexter/upstairs).

    Key physics modelled:
    - The floor heating shunt limits floor water to ~SHUNT_SETPOINT.
    - When supply > SHUNT_SETPOINT, the shunt partially closes → excess hot water
      flows to radiators → radiator zone gets extra gain (RAD_BOOST_FACTOR).
    - Below SHUNT_SETPOINT the floor gets the most benefit; radiators get baseline only.

    Empirical basis (cold weather, outdoor < 15°C, Jan-Apr 2026):
      supply=25°C: delta(dexter-downstairs)=-1.1°C
      supply=40°C: delta=-1.5°C  (worst gap, shunt fully open)
      supply=50°C: delta=-1.1°C  (gap narrows, radiators benefit from surplus)
    """
    if loss_factors is None:
        loss_factors = _get_hourly_loss_factors(len(offsets))

    k_leak_floor = k_leak_floor if k_leak_floor is not None else settings.OPTIMIZER_K_LEAK
    k_leak_rad   = settings.K_LEAK_RADIATOR
    k_gain_floor = k_gain_floor if k_gain_floor is not None else settings.K_GAIN_FLOOR
    k_gain_rad   = settings.K_GAIN_RADIATOR
    shunt        = settings.SHUNT_SETPOINT
    boost        = settings.RAD_BOOST_FACTOR

    floor_temps = []
    rad_temps   = []
    t_floor     = start_floor
    t_rad       = start_radiator

    for i in range(len(offsets)):
        outdoor = outdoor_temps[i]
        offset  = offsets[i]
        lf      = loss_factors[i] if i < len(loss_factors) else 1.0

        supply = _approx_supply(outdoor, offset)

        # Extra radiator gain above the shunt crossover temperature
        rad_boost = max(0.0, (supply - shunt) * boost)

        # Floor zone (shunt buffers it — less sensitive to offset swings)
        t_floor += -k_leak_floor * lf * (t_floor - outdoor) + k_gain_floor * offset
        floor_temps.append(t_floor)

        # Radiator zone (baseline gain + boost above shunt)
        t_rad += -k_leak_rad * lf * (t_rad - outdoor) + k_gain_rad * offset + rad_boost
        rad_temps.append(t_rad)

    return floor_temps, rad_temps


def optimize_24h_plan(
    current_temp: float,
    outdoor_temps: List[float],
    prices: List[float],
    min_temp: Optional[float] = None,
    target_temp: Optional[float] = None,
    current_radiator_temp: Optional[float] = None,
    min_radiator_temp: Optional[float] = None,
    target_radiator_temp: Optional[float] = None,
    must_run_hours: Optional[set] = None,
    boost_allowed_hours: Optional[set] = None,
    heat_in_flight: float = 0.0,
    lead_shed_hours: int = 4,
    k_leak: Optional[float] = None,
    k_gain_floor: Optional[float] = None,
) -> List[float]:
    """
    V14.0 Two-zone two-pass optimizer.

    Pass 1: Raise offsets (cheapest+best-COP first) until BOTH zones are >= their floor.
    Pass 2: Minimize cost while keeping BOTH zones >= their floor. target_temp and
    target_radiator_temp are upper comfort bounds, not minimum temperatures.

    current_radiator_temp / min_radiator_temp: Dexter's zone minimum (comfort floor).
    target_radiator_temp: Desired upstairs temperature (Pass 2 target).
      Higher than floor target → upstairs priority (optimizer keeps higher offsets to
      boost radiators via supply > SHUNT_SETPOINT).
      Lower than floor target → downstairs priority.
    If current_radiator_temp is None, falls back to single-zone V13.0 behaviour.
    """
    hours        = min(len(outdoor_temps), len(prices))
    loss_factors = _get_hourly_loss_factors(hours)
    offsets      = [0.0] * hours

    min_temps = _expand_bounds(min_temp, hours, settings.OPTIMIZER_MIN_TEMP)
    max_temps = _expand_bounds(target_temp, hours, settings.OPTIMIZER_TARGET_TEMP)
    min_rad_temps = _expand_bounds(min_radiator_temp, hours, settings.DEXTER_MIN_TEMP)
    max_rad_temps = _expand_bounds(target_radiator_temp, hours, settings.DEXTER_TARGET_TEMP)

    max_offset = settings.OPTIMIZER_MAX_OFFSET
    min_offset = settings.OPTIMIZER_MIN_OFFSET
    k_leak     = k_leak if k_leak is not None else settings.OPTIMIZER_K_LEAK
    heat_in_flight = max(0.0, float(heat_in_flight or 0.0))
    lead_shed_hours = max(0, int(lead_shed_hours or 0))

    two_zone = current_radiator_temp is not None

    def _with_residual_heat(f_temps, r_temps):
        if heat_in_flight <= 0.0:
            return f_temps, r_temps
        floor_adjusted = []
        rad_adjusted = []
        for i, ft in enumerate(f_temps):
            decay = max(0.0, 1.0 - i * 0.33)
            floor_adjusted.append(ft + heat_in_flight * decay)
            rad_adjusted.append(r_temps[i] + heat_in_flight * 0.8 * decay)
        return floor_adjusted, rad_adjusted

    def _check_temps(offsets):
        if two_zone:
            f_temps, r_temps = predict_temperatures_two_zone(
                current_temp, current_radiator_temp, outdoor_temps, offsets, loss_factors,
                k_leak_floor=k_leak, k_gain_floor=k_gain_floor
            )
        else:
            f_temps = predict_temperatures(current_temp, outdoor_temps, offsets, loss_factors,
                                           k_leak=k_leak, k_gain=k_gain_floor)
            r_temps = f_temps
        return _with_residual_heat(f_temps, r_temps)

    # --- PASS 1: Raise offsets to enforce comfort floors for both zones ---
    for _ in range(300):
        f_temps, r_temps = _check_temps(offsets)

        floor_ok = all(temp >= min_temps[i] for i, temp in enumerate(f_temps))
        rad_ok = all(temp >= min_rad_temps[i] for i, temp in enumerate(r_temps)) if two_zone else True

        if floor_ok and rad_ok:
            break

        # Find the most constrained (earliest binding minimum across both zones)
        bind_idx = 0
        bind_val = float('inf')
        for i, ft in enumerate(f_temps):
            deficit = min_temps[i] - ft
            if deficit > 0 and i < bind_val:
                bind_idx = i
                bind_val = i
                break
        if two_zone:
            for i, rt in enumerate(r_temps):
                deficit = min_rad_temps[i] - rt
                if deficit > 0 and i < bind_val:
                    bind_idx = i
                    bind_val = i
                    break

        # Among all hours up to bind_idx, pick the best (COP/price/decay)
        best_score = -999.0
        best_hour  = -1

        for h in range(bind_idx + 1):
            if offsets[h] >= max_offset:
                continue
            if (
                heat_in_flight >= 0.4
                and offsets[h] >= 0.0
                and boost_allowed_hours is not None
                and h in boost_allowed_hours
            ):
                continue

            avg_water_temp = 30.0 + offsets[h] * 2.0
            cop = COPModel._interpolate_cop(outdoor_temps[h], avg_water_temp) or 3.0
            cop = max(1.0, cop)

            price = max(0.01, prices[h])
            decay = (1.0 - k_leak) ** (bind_idx - h)
            score = (cop * decay) / price

            if score > best_score:
                best_score = score
                best_hour  = h

        if best_hour != -1:
            offsets[best_hour] += 1.0
        else:
            break

    def _floors_ok(f_temps, r_temps) -> bool:
        floor_ok = all(temp >= min_temps[i] for i, temp in enumerate(f_temps))
        rad_ok = all(temp >= min_rad_temps[i] for i, temp in enumerate(r_temps)) if two_zone else True
        return floor_ok and rad_ok

    def _hard_floors_ok(f_temps, r_temps, margin: float = 0.1) -> bool:
        floor_ok = all(temp >= min_temps[i] - margin for i, temp in enumerate(f_temps))
        rad_ok = all(temp >= min_rad_temps[i] - margin for i, temp in enumerate(r_temps)) if two_zone else True
        return floor_ok and rad_ok

    def _hard_floors_ok_window(f_temps, r_temps, start_hour: int, horizon: int = 6, margin: float = 0.1) -> bool:
        end_hour = min(hours, start_hour + horizon + 1)
        floor_ok = all(f_temps[i] >= min_temps[i] - margin for i in range(start_hour, end_hour))
        rad_ok = (
            all(r_temps[i] >= min_rad_temps[i] - margin for i in range(start_hour, end_hour))
            if two_zone else True
        )
        return floor_ok and rad_ok

    def _overheat_amount(hour: int, f_temps, r_temps) -> float:
        floor_over = max(0.0, f_temps[hour] - max_temps[hour])
        rad_over = max(0.0, r_temps[hour] - max_rad_temps[hour]) if two_zone else 0.0
        return max(floor_over, rad_over)

    def _lead_overheat_amount(hour: int, f_temps, r_temps) -> float:
        end_hour = min(hours, hour + lead_shed_hours + 1)
        if end_hour <= hour:
            return _overheat_amount(hour, f_temps, r_temps)
        return max(_overheat_amount(i, f_temps, r_temps) for i in range(hour, end_hour))

    def _objective(test_offsets) -> float:
        f_temps, r_temps = _check_temps(test_offsets)
        score = 0.0

        for i, offset in enumerate(test_offsets):
            heat_intensity = max(0.0, offset - min_offset)
            score += heat_intensity * max(0.01, prices[i])

            floor_under = max(0.0, min_temps[i] - f_temps[i])
            floor_over = max(0.0, f_temps[i] - max_temps[i])
            score += floor_under * 10000.0
            score += floor_over * floor_over * 300.0

            if two_zone:
                rad_under = max(0.0, min_rad_temps[i] - r_temps[i])
                rad_over = max(0.0, r_temps[i] - max_rad_temps[i])
                score += rad_under * 10000.0
                score += rad_over * rad_over * 300.0

            if offset > 0:
                # Positive offset is still available, but should earn its keep.
                score += offset * 0.15

        return score

    def _rest_blocked(hour: int, candidate_offset: float) -> bool:
        return (
            must_run_hours is not None
            and hour in must_run_hours
            and candidate_offset <= settings.OPTIMIZER_REST_THRESHOLD
        )

    # --- PASS 2A: Shed active overheat immediately before price optimization ---
    f_current, r_current = _check_temps(offsets)
    current_overheat = max(0.0, f_current[0] - max_temps[0])
    if two_zone:
        current_overheat = max(current_overheat, r_current[0] - max_rad_temps[0])

    if current_overheat >= 0.3:
        forced_shed_hours = 0
        for h in range(hours):
            if boost_allowed_hours is not None and h in boost_allowed_hours:
                continue
            f_temps, r_temps = _check_temps(offsets)
            if _lead_overheat_amount(h, f_temps, r_temps) <= 0.0:
                continue

            changed = True
            while changed and offsets[h] > min_offset:
                changed = False
                candidate = max(min_offset, offsets[h] - 1.0)
                if _rest_blocked(h, candidate):
                    candidate = max(settings.OPTIMIZER_REST_THRESHOLD + 0.5, min(candidate, -1.0))
                    if candidate >= offsets[h]:
                        break

                trial = offsets.copy()
                trial[h] = candidate
                trial_f, trial_r = _check_temps(trial)
                floors_safe = (
                    _hard_floors_ok_window(trial_f, trial_r, h)
                    if heat_in_flight > 0.0 else _hard_floors_ok(trial_f, trial_r)
                )
                if floors_safe:
                    offsets = trial
                    changed = True
                    forced_shed_hours += 1
                else:
                    break

        if forced_shed_hours:
            logger.debug(
                f"Forced overheat shedding: current_overheat={current_overheat:.1f}°C "
                f"reductions={forced_shed_hours}"
            )

        # Re-establish exact comfort floors after local shedding. This lets the
        # planner cool immediately and, if needed, recover later near morning.
        for _ in range(300):
            f_temps, r_temps = _check_temps(offsets)
            if _hard_floors_ok(f_temps, r_temps):
                break

            bind_idx = 0
            bind_val = float('inf')
            for i, ft in enumerate(f_temps):
                deficit = min_temps[i] - ft
                if deficit > 0 and i < bind_val:
                    bind_idx = i
                    bind_val = i
                    break
            if two_zone:
                for i, rt in enumerate(r_temps):
                    deficit = min_rad_temps[i] - rt
                    if deficit > 0 and i < bind_val:
                        bind_idx = i
                        bind_val = i
                        break

            best_score = -999.0
            best_hour = -1
            for h in range(bind_idx + 1):
                if offsets[h] >= max_offset:
                    continue
                if (
                    must_run_hours is not None
                    and h in must_run_hours
                    and offsets[h] < 0.0
                    and _overheat_amount(h, f_temps, r_temps) > 0.0
                ):
                    continue
                if offsets[h] < 0.0 and _lead_overheat_amount(h, f_temps, r_temps) > 0.0:
                    continue
                if boost_allowed_hours is not None and h not in boost_allowed_hours and offsets[h] >= 0.0:
                    continue

                candidate_offsets = offsets.copy()
                candidate_offsets[h] += 1.0
                if candidate_offsets[h] > 0.0:
                    if heat_in_flight >= 0.4:
                        continue
                    candidate_f, candidate_r = _check_temps(candidate_offsets)
                    if any(temp > max_temps[i] for i, temp in enumerate(candidate_f)):
                        continue
                    if two_zone and any(temp > max_rad_temps[i] for i, temp in enumerate(candidate_r)):
                        continue

                avg_water_temp = 30.0 + offsets[h] * 2.0
                cop = COPModel._interpolate_cop(outdoor_temps[h], avg_water_temp) or 3.0
                cop = max(1.0, cop)
                price = max(0.01, prices[h])
                decay = (1.0 - k_leak) ** (bind_idx - h)
                score = (cop * decay) / price

                if score > best_score:
                    best_score = score
                    best_hour = h

            if best_hour != -1:
                offsets[best_hour] += 1.0
            else:
                break

    # --- PASS 2B: Reduce offsets where cost/overheat improves while floors hold ---

    improved = True
    while improved:
        improved = False
        price_order = sorted(range(hours), key=lambda h: prices[h], reverse=True)

        for h in price_order:
            if offsets[h] <= min_offset:
                continue

            trial = offsets.copy()
            trial[h] -= 1.0
            if _rest_blocked(h, trial[h]):
                continue
            f_temps, r_temps = _check_temps(trial)

            if _floors_ok(f_temps, r_temps) and _objective(trial) < _objective(offsets):
                offsets  = trial
                improved = True
                break

    # When the house is above the active upper band, keep extending load shedding
    # while floors remain safe. This makes REST a primary control action instead
    # of waiting for warm override.
    improved = True
    while improved:
        improved = False
        f_temps, r_temps = _check_temps(offsets)
        overheat_order = sorted(
            range(hours),
            key=lambda h: (
                max(0.0, f_temps[h] - max_temps[h])
                + (max(0.0, r_temps[h] - max_rad_temps[h]) if two_zone else 0.0),
                prices[h],
            ),
            reverse=True,
        )
        for h in overheat_order:
            overheated = f_temps[h] > max_temps[h] or (two_zone and r_temps[h] > max_rad_temps[h])
            if not overheated or offsets[h] <= min_offset:
                continue
            trial = offsets.copy()
            trial[h] -= 1.0
            if _rest_blocked(h, trial[h]):
                continue
            trial_f, trial_r = _check_temps(trial)
            if _floors_ok(trial_f, trial_r):
                offsets = trial
                improved = True
                break

    # Cheap pre-heating/boosting may still be useful, but only if it improves the
    # same comfort/cost objective and never as a reason to exceed the upper band.
    improved = True
    while improved:
        improved = False
        price_order = sorted(range(hours), key=lambda h: prices[h])

        for h in price_order:
            if offsets[h] >= max_offset:
                continue
            if boost_allowed_hours is not None and h not in boost_allowed_hours:
                continue
            if heat_in_flight >= 0.4:
                continue

            trial = offsets.copy()
            trial[h] += 1.0
            f_temps, r_temps = _check_temps(trial)
            if any(temp > max_temps[i] for i, temp in enumerate(f_temps)):
                continue
            if two_zone and any(temp > max_rad_temps[i] for i, temp in enumerate(r_temps)):
                continue

            if _floors_ok(f_temps, r_temps) and _objective(trial) < _objective(offsets):
                offsets = trial
                improved = True
                break

    f_final, r_final = _check_temps(offsets)
    logger.debug(
        f"V14.0 Plan: min_floor={min(f_final):.1f}°C "
        f"min_offset={min(offsets):.1f}, max_offset={max(offsets):.1f}, "
        f"rest_hours={sum(1 for o in offsets if o <= settings.OPTIMIZER_REST_THRESHOLD)}"
        + (f", two_zone=True min_rad={min(r_final):.1f}°C" if two_zone else "")
        + (f", must_run={sorted(must_run_hours)}" if must_run_hours else "")
    )

    return offsets
