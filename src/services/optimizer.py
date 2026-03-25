"""
Deterministic Optimizer V13.0
Two-pass algorithm: enforce comfort floor, then minimize cost.
Uses COP model and per-hour loss factors for improved accuracy.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from typing import List, Optional
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


def predict_temperatures(
    start_temp: float,
    outdoor_temps: List[float],
    offsets: List[float],
    loss_factors: Optional[List[float]] = None
) -> List[float]:
    """
    Simulates indoor temperature for N hours given a heating offset schedule.
    Uses per-hour loss factors to account for time-of-day heat loss variations.
    """
    if loss_factors is None:
        loss_factors = _get_hourly_loss_factors(len(offsets))

    k_leak = settings.OPTIMIZER_K_LEAK
    k_gain = settings.OPTIMIZER_K_GAIN

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


def optimize_24h_plan(
    current_temp: float,
    outdoor_temps: List[float],
    prices: List[float]
) -> List[float]:
    """
    V13.0 Two-pass optimizer.

    Pass 1: Raise offsets (greedy, cheapest+best-COP first) until temp >= MIN_TEMP everywhere.
    Pass 2: Reduce offsets at expensive hours while keeping temp >= TARGET_TEMP everywhere.
    """
    hours = min(len(outdoor_temps), len(prices))
    loss_factors = _get_hourly_loss_factors(hours)
    offsets = [0.0] * hours

    min_temp = settings.OPTIMIZER_MIN_TEMP
    target_temp = settings.OPTIMIZER_TARGET_TEMP
    max_offset = settings.OPTIMIZER_MAX_OFFSET
    min_offset = settings.OPTIMIZER_MIN_OFFSET
    k_leak = settings.OPTIMIZER_K_LEAK

    # --- PASS 1: Raise offsets to enforce comfort floor ---
    for _ in range(200):
        temps = predict_temperatures(current_temp, outdoor_temps, offsets, loss_factors)

        min_val = min(temps)
        min_idx = temps.index(min_val)

        if min_val >= min_temp:
            break

        best_score = -999.0
        best_hour = -1

        for h in range(min_idx + 1):
            if offsets[h] >= max_offset:
                continue

            # COP via bilinear interpolation (supply temp approximated from offset)
            avg_water_temp = 30.0 + offsets[h] * 2.0
            cop = COPModel._interpolate_cop(outdoor_temps[h], avg_water_temp) or 3.0
            cop = max(1.0, cop)

            price = max(0.01, prices[h])
            decay = (1.0 - k_leak) ** (min_idx - h)
            score = (cop * decay) / price

            if score > best_score:
                best_score = score
                best_hour = h

        if best_hour != -1:
            offsets[best_hour] += 1.0
        else:
            break

    # --- PASS 2: Reduce offsets at expensive hours while keeping temp >= TARGET_TEMP ---
    improved = True
    while improved:
        improved = False
        price_order = sorted(range(hours), key=lambda h: prices[h], reverse=True)

        for h in price_order:
            if offsets[h] <= min_offset:
                continue

            trial = offsets.copy()
            trial[h] -= 1.0
            temps = predict_temperatures(current_temp, outdoor_temps, trial, loss_factors)

            if min(temps) >= target_temp:
                offsets = trial
                improved = True
                break  # Restart from most expensive after each reduction

    logger.debug(f"V13.0 Plan: min_offset={min(offsets):.1f}, max_offset={max(offsets):.1f}, "
                 f"rest_hours={sum(1 for o in offsets if o <= settings.OPTIMIZER_REST_THRESHOLD)}")

    return offsets
