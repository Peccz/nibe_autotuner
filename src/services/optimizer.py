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

from typing import List, Optional, Tuple
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


def predict_temperatures(
    start_temp: float,
    outdoor_temps: List[float],
    offsets: List[float],
    loss_factors: Optional[List[float]] = None,
) -> List[float]:
    """
    Single-zone simulation (floor zone). Used for backwards compatibility
    and as the primary constraint in the optimizer.
    """
    if loss_factors is None:
        loss_factors = _get_hourly_loss_factors(len(offsets))

    k_leak = settings.OPTIMIZER_K_LEAK
    k_gain = settings.K_GAIN_FLOOR

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

    k_leak_floor = settings.OPTIMIZER_K_LEAK
    k_leak_rad   = settings.K_LEAK_RADIATOR
    k_gain_floor = settings.K_GAIN_FLOOR
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
) -> List[float]:
    """
    V14.0 Two-zone two-pass optimizer.

    Pass 1: Raise offsets (cheapest+best-COP first) until BOTH zones are >= their floor.
    Pass 2: Reduce offsets at expensive hours while keeping BOTH zones >= their target.

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

    if min_temp is None:
        min_temp = settings.OPTIMIZER_MIN_TEMP
    if target_temp is None:
        target_temp = settings.OPTIMIZER_TARGET_TEMP
    if min_radiator_temp is None:
        min_radiator_temp = settings.DEXTER_MIN_TEMP
    if target_radiator_temp is None:
        target_radiator_temp = settings.DEXTER_TARGET_TEMP

    max_offset = settings.OPTIMIZER_MAX_OFFSET
    min_offset = settings.OPTIMIZER_MIN_OFFSET
    k_leak     = settings.OPTIMIZER_K_LEAK

    two_zone = current_radiator_temp is not None

    def _check_temps(offsets):
        """Returns (floor_temps, rad_temps, binding_floor_idx, binding_rad_idx)."""
        if two_zone:
            f_temps, r_temps = predict_temperatures_two_zone(
                current_temp, current_radiator_temp, outdoor_temps, offsets, loss_factors
            )
        else:
            f_temps = predict_temperatures(current_temp, outdoor_temps, offsets, loss_factors)
            r_temps = f_temps  # single-zone fallback
        return f_temps, r_temps

    # --- PASS 1: Raise offsets to enforce comfort floors for both zones ---
    for _ in range(300):
        f_temps, r_temps = _check_temps(offsets)

        floor_ok = min(f_temps) >= min_temp
        rad_ok   = min(r_temps) >= min_radiator_temp if two_zone else True

        if floor_ok and rad_ok:
            break

        # Find the most constrained (earliest binding minimum across both zones)
        bind_idx = 0
        bind_val = float('inf')
        for i, ft in enumerate(f_temps):
            deficit = min_temp - ft
            if deficit > 0 and i < bind_val:
                bind_idx = i
                bind_val = i
                break
        if two_zone:
            for i, rt in enumerate(r_temps):
                deficit = min_radiator_temp - rt
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

    # --- PASS 2: Reduce offsets at expensive hours while keeping both zones >= target ---
    rad_target = target_radiator_temp

    improved = True
    while improved:
        improved = False
        price_order = sorted(range(hours), key=lambda h: prices[h], reverse=True)

        for h in price_order:
            if offsets[h] <= min_offset:
                continue

            trial = offsets.copy()
            trial[h] -= 1.0
            f_temps, r_temps = _check_temps(trial)

            floor_ok = min(f_temps) >= target_temp
            rad_ok   = min(r_temps) >= rad_target if two_zone else True

            if floor_ok and rad_ok:
                offsets  = trial
                improved = True
                break

    logger.debug(
        f"V14.0 Plan: min_floor={min(predict_temperatures(current_temp, outdoor_temps, offsets, loss_factors)):.1f}°C "
        f"min_offset={min(offsets):.1f}, max_offset={max(offsets):.1f}, "
        f"rest_hours={sum(1 for o in offsets if o <= settings.OPTIMIZER_REST_THRESHOLD)}"
        + (f", two_zone=True min_rad={min(predict_temperatures_two_zone(current_temp, current_radiator_temp, outdoor_temps, offsets, loss_factors)[1]):.1f}°C" if two_zone else "")
    )

    return offsets
