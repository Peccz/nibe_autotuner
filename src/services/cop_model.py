"""
Improved COP Estimation Model
Uses empirical data and manufacturer specs instead of pure Carnot theory
"""
from typing import Optional
import math


class COPModel:
    """
    Empirical COP model for Nibe F730 heat pump

    Based on:
    - Nibe F730 technical specifications
    - Real-world performance data
    - SCOP (Seasonal COP) ratings
    - Temperature-dependent efficiency curves
    """

    # Nibe F730 specifications (from manual)
    # At A7/W35 (7°C outside, 35°C water): COP ~3.5-4.0
    # At A-7/W35 (-7°C outside, 35°C water): COP ~2.5-3.0
    # At A2/W35 (2°C outside, 35°C water): COP ~3.2-3.7

    # Reference points from manufacturer data
    REFERENCE_POINTS = [
        # (outdoor_temp, water_temp, expected_cop)
        (-15, 35, 2.2),
        (-7, 35, 2.8),
        (2, 35, 3.5),
        (7, 35, 4.0),
        (10, 35, 4.3),
        (-7, 45, 2.3),
        (2, 45, 2.9),
        (7, 45, 3.3),
    ]

    # Degradation factors
    DEFROST_PENALTY = 0.85  # 15% loss during defrost conditions
    SHORT_CYCLE_PENALTY = 0.90  # 10% loss from short cycling
    LOW_FLOW_PENALTY = 0.95  # 5% loss from suboptimal flow

    @staticmethod
    def estimate_cop_empirical(
        outdoor_temp: float,
        supply_temp: float,
        return_temp: float,
        compressor_freq: Optional[float] = None,
        pump_speed: Optional[float] = None,
        num_cycles: Optional[int] = None,
        runtime_hours: Optional[float] = None
    ) -> Optional[float]:
        """
        Estimate COP using empirical model based on manufacturer data

        Args:
            outdoor_temp: Outdoor temperature (°C)
            supply_temp: Supply water temperature (°C)
            return_temp: Return water temperature (°C)
            compressor_freq: Compressor frequency (Hz), optional
            pump_speed: Circulation pump speed (%), optional
            num_cycles: Number of start/stop cycles, optional
            runtime_hours: Total runtime hours, optional

        Returns:
            Estimated COP or None if insufficient data
        """
        if not all([outdoor_temp is not None, supply_temp is not None, return_temp is not None]):
            return None

        # Average water temperature
        avg_water_temp = (supply_temp + return_temp) / 2

        # Find closest reference point
        base_cop = COPModel._interpolate_cop(outdoor_temp, avg_water_temp)

        if base_cop is None:
            return None

        # Apply degradation factors
        adjusted_cop = base_cop

        # Defrost penalty (outdoor temp near freezing with high humidity)
        if -2 <= outdoor_temp <= 7:
            adjusted_cop *= COPModel.DEFROST_PENALTY

        # Short cycling penalty
        if num_cycles and runtime_hours:
            cycles_per_hour = num_cycles / max(runtime_hours, 0.1)
            if cycles_per_hour > 3:  # More than 3 starts per hour
                adjusted_cop *= COPModel.SHORT_CYCLE_PENALTY

        # Low flow penalty (high delta T indicates low flow)
        delta_t = supply_temp - return_temp
        if delta_t > 10:  # Very high delta T
            adjusted_cop *= COPModel.LOW_FLOW_PENALTY
        elif delta_t < 2:  # Very low delta T (too much flow, wasted pump energy)
            adjusted_cop *= 0.98

        return max(1.0, min(adjusted_cop, 6.0))  # Clamp to reasonable range

    @staticmethod
    def _interpolate_cop(outdoor_temp: float, water_temp: float) -> Optional[float]:
        """
        Interpolate COP from reference points

        Uses bilinear interpolation between nearest reference points
        """
        refs = COPModel.REFERENCE_POINTS

        # Find bounding points
        lower_outdoor = None
        upper_outdoor = None
        lower_water = None
        upper_water = None

        outdoor_temps = sorted(set(r[0] for r in refs))
        water_temps = sorted(set(r[1] for r in refs))

        # Find outdoor temp bounds
        for i, temp in enumerate(outdoor_temps):
            if temp <= outdoor_temp:
                lower_outdoor = temp
            if temp >= outdoor_temp and upper_outdoor is None:
                upper_outdoor = temp
                break

        # Find water temp bounds
        for temp in water_temps:
            if temp <= water_temp:
                lower_water = temp
            if temp >= water_temp and upper_water is None:
                upper_water = temp
                break

        # If outside bounds, extrapolate with penalty
        if lower_outdoor is None:
            lower_outdoor = outdoor_temps[0]
            penalty = 0.95  # 5% penalty for extrapolation
        else:
            penalty = 1.0

        if upper_outdoor is None:
            upper_outdoor = outdoor_temps[-1]
            penalty *= 0.95

        if lower_water is None:
            lower_water = water_temps[0]
            penalty *= 0.95

        if upper_water is None:
            upper_water = water_temps[-1]
            penalty *= 0.95

        # Get COP values at the four corners
        def get_cop(out_t, wat_t):
            for ref in refs:
                if ref[0] == out_t and ref[1] == wat_t:
                    return ref[2]
            # If exact match not found, use nearest
            nearest = min(refs, key=lambda r: abs(r[0] - out_t) + abs(r[1] - wat_t))
            return nearest[2]

        cop_ll = get_cop(lower_outdoor, lower_water)  # Lower left
        cop_ul = get_cop(upper_outdoor, lower_water)  # Upper left
        cop_lr = get_cop(lower_outdoor, upper_water)  # Lower right
        cop_ur = get_cop(upper_outdoor, upper_water)  # Upper right

        # Bilinear interpolation
        if upper_outdoor == lower_outdoor:
            # Interpolate only in water temp dimension
            if upper_water == lower_water:
                result = cop_ll
            else:
                t = (water_temp - lower_water) / (upper_water - lower_water)
                result = cop_ll * (1 - t) + cop_lr * t
        elif upper_water == lower_water:
            # Interpolate only in outdoor temp dimension
            t = (outdoor_temp - lower_outdoor) / (upper_outdoor - lower_outdoor)
            result = cop_ll * (1 - t) + cop_ul * t
        else:
            # Full bilinear interpolation
            t_out = (outdoor_temp - lower_outdoor) / (upper_outdoor - lower_outdoor)
            t_wat = (water_temp - lower_water) / (upper_water - lower_water)

            # Interpolate in outdoor dimension first
            cop_low = cop_ll * (1 - t_out) + cop_ul * t_out
            cop_high = cop_lr * (1 - t_out) + cop_ur * t_out

            # Then in water dimension
            result = cop_low * (1 - t_wat) + cop_high * t_wat

        return result * penalty

    @staticmethod
    def estimate_cop_carnot(
        outdoor_temp: float,
        supply_temp: float,
        return_temp: float,
        efficiency_factor: float = 0.40  # Lower, more realistic
    ) -> Optional[float]:
        """
        Estimate COP using Carnot formula (backup method)

        Uses more conservative efficiency factor (40% instead of 45%)
        """
        if not all([outdoor_temp is not None, supply_temp is not None, return_temp is not None]):
            return None

        avg_water_temp = (supply_temp + return_temp) / 2
        temp_lift = avg_water_temp - outdoor_temp

        if temp_lift <= 0:
            return None

        # Carnot COP in Kelvin
        t_hot_k = avg_water_temp + 273.15
        t_cold_k = outdoor_temp + 273.15
        carnot_cop = t_hot_k / (t_hot_k - t_cold_k)

        # Apply conservative efficiency factor
        estimated_cop = carnot_cop * efficiency_factor

        return max(1.0, min(estimated_cop, 5.0))

    @staticmethod
    def calculate_heating_power(
        cop: float,
        electrical_power_kw: float = 1.5  # Estimated F730 power draw
    ) -> float:
        """
        Calculate heating power output

        Args:
            cop: Coefficient of Performance
            electrical_power_kw: Electrical input power (kW)

        Returns:
            Heating power output (kW)
        """
        return cop * electrical_power_kw

    @staticmethod
    def calculate_cost_per_hour(
        cop: float,
        electrical_power_kw: float = 1.5,
        electricity_price_sek_kwh: float = 2.0
    ) -> float:
        """
        Calculate running cost per hour

        Args:
            cop: Coefficient of Performance
            electrical_power_kw: Electrical input (kW)
            electricity_price_sek_kwh: Price per kWh (SEK)

        Returns:
            Cost per hour (SEK/h)
        """
        return electrical_power_kw * electricity_price_sek_kwh


def compare_models(outdoor_temp: float, supply_temp: float, return_temp: float):
    """Compare different COP estimation methods"""
    print(f"\n=== COP Model Comparison ===")
    print(f"Outdoor: {outdoor_temp}°C, Supply: {supply_temp}°C, Return: {return_temp}°C")
    print(f"Water avg: {(supply_temp + return_temp)/2:.1f}°C, Temp lift: {(supply_temp + return_temp)/2 - outdoor_temp:.1f}°C")
    print()

    # Empirical model
    cop_emp = COPModel.estimate_cop_empirical(outdoor_temp, supply_temp, return_temp)
    print(f"Empirical model (manufacturer data): COP = {cop_emp:.2f}")

    # Carnot 45% (old)
    cop_c45 = COPModel.estimate_cop_carnot(outdoor_temp, supply_temp, return_temp, 0.45)
    print(f"Carnot 45% efficiency (old):         COP = {cop_c45:.2f}")

    # Carnot 40% (new conservative)
    cop_c40 = COPModel.estimate_cop_carnot(outdoor_temp, supply_temp, return_temp, 0.40)
    print(f"Carnot 40% efficiency (conservative): COP = {cop_c40:.2f}")

    print()
    print(f"Recommendation: Use EMPIRICAL model (COP = {cop_emp:.2f})")


if __name__ == '__main__':
    # Test with current values
    compare_models(5.8, 27.5, 25.9)

    # Test with winter conditions
    compare_models(-5, 35, 32)

    # Test with summer/spring
    compare_models(15, 25, 23)

