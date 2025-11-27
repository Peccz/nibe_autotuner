"""
Heat Pump Data Analyzer
Analyzes collected data to calculate efficiency metrics and identify optimization opportunities
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from models import (
    Base, System, Device, Parameter, ParameterReading,
    ParameterChange, Recommendation, RecommendationResult,
    init_db
)
from sqlalchemy.orm import sessionmaker


@dataclass
class EfficiencyMetrics:
    """Container for calculated efficiency metrics"""
    period_start: datetime
    period_end: datetime
    avg_outdoor_temp: float
    avg_indoor_temp: float
    avg_supply_temp: float
    avg_return_temp: float
    delta_t: float  # Supply-Return temperature differential (all readings)
    delta_t_active: Optional[float]  # Delta T during active space heating only
    delta_t_hot_water: Optional[float]  # Delta T during hot water production
    avg_compressor_freq: float
    degree_minutes: float
    heating_curve: float
    curve_offset: float
    estimated_cop: Optional[float] = None
    compressor_runtime_hours: Optional[float] = None


@dataclass
class OptimizationOpportunity:
    """Represents a potential optimization"""
    parameter_id: str
    parameter_name: str
    current_value: float
    suggested_value: float
    expected_impact: str
    reasoning: str
    confidence: float  # 0.0 to 1.0


class HeatPumpAnalyzer:
    """Analyzes heat pump performance and generates optimization recommendations"""

    # Key parameter IDs for Nibe F730
    PARAM_OUTDOOR_TEMP = '40004'
    PARAM_SUPPLY_TEMP = '40008'
    PARAM_RETURN_TEMP = '40012'
    PARAM_INDOOR_TEMP = '40033'
    PARAM_COMPRESSOR_FREQ = '41778'
    PARAM_HEATING_CURVE = '47007'
    PARAM_CURVE_OFFSET = '47011'
    PARAM_DM_HEATING_START = '47206'
    PARAM_DM_HEATING_STOP = '48072'
    PARAM_DM_CURRENT = '40940'  # Current degree minutes value
    PARAM_COMPRESSOR_STATE = '43424'

    # Nibe F730 Manufacturer Specifications
    # Source: docs/NIBE_F730_BASELINE.md
    SPEC_COMPRESSOR_MIN_KW = 1.1
    SPEC_COMPRESSOR_MAX_KW = 6.0
    SPEC_EXHAUST_AIR_MIN_TEMP = -15.0  # °C
    SPEC_EXHAUST_AIR_BLOCK_TEMP = 6.0  # °C - compressor blocked below this
    SPEC_EXHAUST_AIR_FLOW_MIN = 90  # m³/h
    SPEC_EXHAUST_AIR_FLOW_STD = 180  # m³/h
    SPEC_EXHAUST_AIR_FLOW_MAX = 252  # m³/h

    # Optimal Operating Parameters (from manufacturer + research)
    TARGET_DM = -200  # Degree minutes target
    TARGET_DM_MIN = -300  # Lower comfort limit
    TARGET_DM_MAX = -100  # Upper comfort limit
    TARGET_DELTA_T_MIN = 5.0  # °C - Optimal delta T minimum
    TARGET_DELTA_T_MAX = 8.0  # °C - Optimal delta T maximum
    TARGET_COP_MIN = 3.0  # Minimum acceptable COP (seasonal/conditions dependent)
    TARGET_HOT_WATER_OPTIMAL = 45.0  # °C - Most efficient
    TARGET_HOT_WATER_MAX_EFFICIENT = 55.0  # °C - Maximum before heavy electric backup

    # Operating mode thresholds
    COMPRESSOR_ACTIVE_THRESHOLD = 20.0  # Hz - Minimum frequency for active heating
    HOT_WATER_TEMP_THRESHOLD = 45.0  # °C - Supply temp above this indicates hot water production

    # Heating curve typical ranges (system dependent)
    CURVE_UNDERFLOOR_MIN = 3
    CURVE_UNDERFLOOR_MAX = 6
    CURVE_RADIATOR_MIN = 5
    CURVE_RADIATOR_MAX = 9

    def __init__(self, db_path: str = 'data/nibe_autotuner.db'):
        """Initialize analyzer with database connection"""
        self.db_path = db_path
        database_url = f'sqlite:///./{db_path}'
        self.engine = init_db(database_url)
        SessionMaker = sessionmaker(bind=self.engine)
        self.session = SessionMaker()

    def __del__(self):
        """Clean up database connection"""
        if hasattr(self, 'session'):
            self.session.close()

    def get_device(self) -> Device:
        """Get the first (and typically only) device"""
        device = self.session.query(Device).first()
        if not device:
            raise ValueError("No device found in database")
        return device

    def get_parameter_id(self, param_id_str: str) -> int:
        """Get internal parameter ID from parameter ID string"""
        param = self.session.query(Parameter).filter_by(parameter_id=param_id_str).first()
        if not param:
            raise ValueError(f"Parameter {param_id_str} not found")
        return param.id

    def get_readings(
        self,
        device: Device,
        parameter_id_str: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Tuple[datetime, float]]:
        """Get readings for a specific parameter in a time range"""
        param_id = self.get_parameter_id(parameter_id_str)

        readings = self.session.query(
            ParameterReading.timestamp,
            ParameterReading.value
        ).filter(
            and_(
                ParameterReading.device_id == device.id,
                ParameterReading.parameter_id == param_id,
                ParameterReading.timestamp >= start_time,
                ParameterReading.timestamp <= end_time
            )
        ).order_by(ParameterReading.timestamp).all()

        return [(r.timestamp, r.value) for r in readings]

    def calculate_average(
        self,
        device: Device,
        parameter_id_str: str,
        start_time: datetime,
        end_time: datetime
    ) -> Optional[float]:
        """Calculate average value for a parameter in a time range"""
        param_id = self.get_parameter_id(parameter_id_str)

        result = self.session.query(
            func.avg(ParameterReading.value)
        ).filter(
            and_(
                ParameterReading.device_id == device.id,
                ParameterReading.parameter_id == param_id,
                ParameterReading.timestamp >= start_time,
                ParameterReading.timestamp <= end_time
            )
        ).scalar()

        return float(result) if result is not None else None

    def get_latest_value(self, device: Device, parameter_id_str: str) -> Optional[float]:
        """Get the most recent value for a parameter"""
        param_id = self.get_parameter_id(parameter_id_str)

        reading = self.session.query(ParameterReading).filter(
            and_(
                ParameterReading.device_id == device.id,
                ParameterReading.parameter_id == param_id
            )
        ).order_by(ParameterReading.timestamp.desc()).first()

        return reading.value if reading else None

    def calculate_metrics(
        self,
        hours_back: int = 24
    ) -> EfficiencyMetrics:
        """
        Calculate efficiency metrics for the specified time period

        Args:
            hours_back: Number of hours to analyze (default 24)

        Returns:
            EfficiencyMetrics object with calculated values
        """
        device = self.get_device()
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)

        logger.info(f"Calculating metrics from {start_time} to {end_time}")

        # Calculate averages for key parameters
        avg_outdoor = self.calculate_average(device, self.PARAM_OUTDOOR_TEMP, start_time, end_time)
        avg_indoor = self.calculate_average(device, self.PARAM_INDOOR_TEMP, start_time, end_time)
        avg_supply = self.calculate_average(device, self.PARAM_SUPPLY_TEMP, start_time, end_time)
        avg_return = self.calculate_average(device, self.PARAM_RETURN_TEMP, start_time, end_time)
        avg_compressor = self.calculate_average(device, self.PARAM_COMPRESSOR_FREQ, start_time, end_time)

        # Get current settings
        heating_curve = self.get_latest_value(device, self.PARAM_HEATING_CURVE)
        curve_offset = self.get_latest_value(device, self.PARAM_CURVE_OFFSET)
        degree_minutes = self.get_latest_value(device, self.PARAM_DM_CURRENT)

        # Calculate compressor runtime
        compressor_runtime = self._calculate_compressor_runtime(device, start_time, end_time)

        # Calculate delta T (supply-return differential)
        delta_t = (avg_supply or 0.0) - (avg_return or 0.0)

        # Calculate separate Delta T for active heating and hot water production
        delta_t_active, delta_t_hot_water = self._calculate_active_delta_t(
            device, start_time, end_time
        )

        # Estimate COP based on temperature differential and outdoor temp
        estimated_cop = self._estimate_cop(avg_outdoor, avg_supply, avg_return)

        metrics = EfficiencyMetrics(
            period_start=start_time,
            period_end=end_time,
            avg_outdoor_temp=avg_outdoor or 0.0,
            avg_indoor_temp=avg_indoor or 0.0,
            avg_supply_temp=avg_supply or 0.0,
            avg_return_temp=avg_return or 0.0,
            delta_t=delta_t,
            delta_t_active=delta_t_active,
            delta_t_hot_water=delta_t_hot_water,
            avg_compressor_freq=avg_compressor or 0.0,
            degree_minutes=degree_minutes or 0.0,
            heating_curve=heating_curve or 0.0,
            curve_offset=curve_offset or 0.0,
            estimated_cop=estimated_cop,
            compressor_runtime_hours=compressor_runtime
        )

        cop_str = f"{estimated_cop:.2f}" if estimated_cop else "N/A"
        dm_str = f"{degree_minutes:.0f}" if degree_minutes else "N/A"
        outdoor_str = f"{avg_outdoor:.1f}" if avg_outdoor else "N/A"
        logger.info(f"Metrics calculated: COP={cop_str}, DM={dm_str}, Outdoor={outdoor_str}°C")

        return metrics

    def _calculate_compressor_runtime(
        self,
        device: Device,
        start_time: datetime,
        end_time: datetime
    ) -> float:
        """Calculate total compressor runtime in hours"""
        # Get compressor state readings (0=off, 1=on)
        readings = self.get_readings(device, self.PARAM_COMPRESSOR_STATE, start_time, end_time)

        if not readings:
            return 0.0

        # Calculate runtime by integrating state over time
        total_seconds = 0.0
        for i in range(len(readings) - 1):
            if readings[i][1] > 0:  # Compressor is on
                time_diff = (readings[i + 1][0] - readings[i][0]).total_seconds()
                total_seconds += time_diff

        return total_seconds / 3600.0  # Convert to hours

    def _calculate_active_delta_t(
        self,
        device: Device,
        start_time: datetime,
        end_time: datetime
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculate Delta T separately for active space heating and hot water production

        Returns:
            Tuple of (delta_t_active, delta_t_hot_water)
            - delta_t_active: Delta T when compressor >20 Hz and supply <45°C (space heating)
            - delta_t_hot_water: Delta T when compressor >20 Hz and supply >45°C (hot water)
        """
        # Get readings for all relevant parameters
        supply_readings = self.get_readings(device, self.PARAM_SUPPLY_TEMP, start_time, end_time)
        return_readings = self.get_readings(device, self.PARAM_RETURN_TEMP, start_time, end_time)
        compressor_readings = self.get_readings(device, self.PARAM_COMPRESSOR_FREQ, start_time, end_time)

        if not supply_readings or not return_readings or not compressor_readings:
            return None, None

        # Collect matched readings for space heating and hot water
        space_heating_deltas = []
        hot_water_deltas = []

        # Time tolerance for matching readings (5 minutes = 300 seconds)
        time_tolerance = timedelta(seconds=300)

        # For each supply reading, find matching return and compressor readings
        for supply_ts, supply_temp in supply_readings:
            # Find closest return reading within time tolerance
            return_temp = None
            min_return_diff = time_tolerance
            for return_ts, temp in return_readings:
                diff = abs(supply_ts - return_ts)
                if diff < min_return_diff:
                    min_return_diff = diff
                    return_temp = temp

            # Find closest compressor reading within time tolerance
            comp_freq = None
            min_comp_diff = time_tolerance
            for comp_ts, freq in compressor_readings:
                diff = abs(supply_ts - comp_ts)
                if diff < min_comp_diff:
                    min_comp_diff = diff
                    comp_freq = freq

            # If we found matching readings within tolerance
            if return_temp is not None and comp_freq is not None:
                # Only include readings where compressor is actively heating
                if comp_freq > self.COMPRESSOR_ACTIVE_THRESHOLD:
                    delta = supply_temp - return_temp

                    # Separate by operating mode based on supply temperature
                    if supply_temp < self.HOT_WATER_TEMP_THRESHOLD:
                        # Space heating (lower temperature)
                        space_heating_deltas.append(delta)
                    else:
                        # Hot water production (higher temperature)
                        hot_water_deltas.append(delta)

        # Calculate averages
        delta_t_active = sum(space_heating_deltas) / len(space_heating_deltas) if space_heating_deltas else None
        delta_t_hot_water = sum(hot_water_deltas) / len(hot_water_deltas) if hot_water_deltas else None

        # Log statistics for debugging
        if space_heating_deltas or hot_water_deltas:
            logger.debug(
                f"Delta T analysis: {len(space_heating_deltas)} space heating readings, "
                f"{len(hot_water_deltas)} hot water readings"
            )

        return delta_t_active, delta_t_hot_water

    def _estimate_cop(
        self,
        outdoor_temp: Optional[float],
        supply_temp: Optional[float],
        return_temp: Optional[float]
    ) -> Optional[float]:
        """
        Estimate Coefficient of Performance (COP) based on temperatures

        This is a simplified estimation. Real COP would require energy meter data.
        Formula based on Carnot efficiency adjusted for real-world heat pump performance.

        Scientific Basis:
        - Carnot COP = T_hot / (T_hot - T_cold) where T is in Kelvin
        - Real heat pumps achieve 30-60% of Carnot efficiency (we use 45%)
        - See docs/SCIENTIFIC_BASELINE.md for references
        """
        if not all([outdoor_temp, supply_temp, return_temp]):
            return None

        # Average water temperature in heating system
        avg_water_temp = (supply_temp + return_temp) / 2

        # Temperature lift (difference between output and input)
        temp_lift = avg_water_temp - outdoor_temp

        if temp_lift <= 0:
            return None

        # Carnot COP: T_hot / (T_hot - T_cold) where T is in Kelvin
        t_hot_k = avg_water_temp + 273.15
        t_cold_k = outdoor_temp + 273.15
        carnot_cop = t_hot_k / (t_hot_k - t_cold_k)

        # Real heat pump achieves ~40-50% of Carnot efficiency
        # Better pumps at moderate temperatures can reach 50%
        efficiency_factor = 0.45
        estimated_cop = carnot_cop * efficiency_factor

        # Typical COP range for air-source heat pumps: 2.0 - 5.0
        # Clamp to reasonable bounds
        return max(2.0, min(5.0, estimated_cop))

    def analyze_heating_curve(self, metrics: EfficiencyMetrics) -> List[OptimizationOpportunity]:
        """
        Analyze heating curve effectiveness and suggest adjustments

        Target: Maintain degree minutes around -200 (slight cooling deficit)
        - If DM < -300: System is too cold, increase heating curve
        - If DM > -100: System is too warm, decrease heating curve

        Scientific Basis:
        - Recent research (2025) shows 84.42% of heating curves can be improved
        - Average energy reduction: 4.02%, COP increase: 2.59%
        - Optimal delta T for ASHPs: 5-7°C (we use 5-8°C)
        - See docs/SCIENTIFIC_BASELINE.md for full references
        """
        opportunities = []

        dm = metrics.degree_minutes
        curve = metrics.heating_curve

        # Degree minutes analysis
        if dm < -300:
            # System is running too cold
            suggested_curve = min(15.0, curve + 0.5)
            opportunities.append(OptimizationOpportunity(
                parameter_id=self.PARAM_HEATING_CURVE,
                parameter_name="Heating curve",
                current_value=curve,
                suggested_value=suggested_curve,
                expected_impact="Increase indoor temperature and comfort",
                reasoning=f"Degree minutes at {dm:.0f} indicates system is too cold. "
                         f"Target is around -200 DM for optimal comfort and efficiency.",
                confidence=0.85
            ))
        elif dm > -100:
            # System is running too warm
            suggested_curve = max(0.0, curve - 0.5)
            opportunities.append(OptimizationOpportunity(
                parameter_id=self.PARAM_HEATING_CURVE,
                parameter_name="Heating curve",
                current_value=curve,
                suggested_value=suggested_curve,
                expected_impact="Reduce energy consumption while maintaining comfort",
                reasoning=f"Degree minutes at {dm:.0f} indicates system is too warm. "
                         f"Target is around -200 DM for optimal efficiency.",
                confidence=0.85
            ))

        # Temperature differential analysis
        # Optimal ΔT for hydronic systems is typically 5-8°C
        # Too low (<3°C) = poor heat extraction, water too hot
        # Too high (>10°C) = insufficient flow or undersized system
        if metrics.delta_t < 3:
            # Small differential suggests low heat extraction
            opportunities.append(OptimizationOpportunity(
                parameter_id=self.PARAM_CURVE_OFFSET,
                parameter_name="Curve offset",
                current_value=metrics.curve_offset,
                suggested_value=max(-10.0, metrics.curve_offset - 1.0),
                expected_impact="Reduce supply temperature, improve efficiency",
                reasoning=f"Supply-return differential is only {metrics.delta_t:.1f}°C. "
                         f"Low differential suggests water is too hot, reducing efficiency. "
                         f"Target differential is 5-8°C.",
                confidence=0.70
            ))
        elif metrics.delta_t > 10:
            # Large differential suggests insufficient flow or heat output
            opportunities.append(OptimizationOpportunity(
                parameter_id=self.PARAM_CURVE_OFFSET,
                parameter_name="Curve offset",
                current_value=metrics.curve_offset,
                suggested_value=min(10.0, metrics.curve_offset + 1.0),
                expected_impact="Increase heat output to meet demand",
                reasoning=f"Supply-return differential is {metrics.delta_t:.1f}°C. "
                         f"Large differential suggests insufficient heat output. "
                         f"Target differential is 5-8°C.",
                confidence=0.70
            ))

        return opportunities

    def analyze_efficiency(self, metrics: EfficiencyMetrics) -> List[OptimizationOpportunity]:
        """
        Analyze overall system efficiency and suggest improvements
        """
        opportunities = []

        if metrics.estimated_cop and metrics.estimated_cop < 2.5:
            # Low COP suggests inefficient operation
            opportunities.append(OptimizationOpportunity(
                parameter_id=self.PARAM_HEATING_CURVE,
                parameter_name="System efficiency",
                current_value=metrics.estimated_cop,
                suggested_value=3.0,
                expected_impact="Improve overall system efficiency",
                reasoning=f"Estimated COP of {metrics.estimated_cop:.2f} is below optimal. "
                         f"This may be due to outdoor temperature, but consider reducing "
                         f"supply temperature if comfort allows. Target COP > 2.5.",
                confidence=0.60
            ))

        # Check if compressor is cycling too frequently
        if metrics.compressor_runtime_hours:
            hours_in_period = (metrics.period_end - metrics.period_start).total_seconds() / 3600
            runtime_ratio = metrics.compressor_runtime_hours / hours_in_period

            if runtime_ratio > 0.8:
                # Compressor running almost continuously
                opportunities.append(OptimizationOpportunity(
                    parameter_id=self.PARAM_HEATING_CURVE,
                    parameter_name="Compressor runtime",
                    current_value=runtime_ratio * 100,
                    suggested_value=70.0,
                    expected_impact="Reduce compressor wear and allow defrost cycles",
                    reasoning=f"Compressor running {runtime_ratio*100:.0f}% of the time. "
                             f"Continuous operation prevents efficient defrost and increases wear. "
                             f"Consider if heating demand is too high.",
                    confidence=0.75
                ))

        return opportunities

    def generate_recommendations(
        self,
        hours_back: int = 24,
        min_confidence: float = 0.6
    ) -> List[OptimizationOpportunity]:
        """
        Generate comprehensive optimization recommendations

        Args:
            hours_back: Hours of historical data to analyze
            min_confidence: Minimum confidence level to include (0.0-1.0)

        Returns:
            List of optimization opportunities sorted by confidence
        """
        logger.info(f"Generating recommendations based on last {hours_back} hours")

        # Calculate current metrics
        metrics = self.calculate_metrics(hours_back)

        # Analyze different aspects
        opportunities = []
        opportunities.extend(self.analyze_heating_curve(metrics))
        opportunities.extend(self.analyze_efficiency(metrics))

        # Filter by confidence and sort
        opportunities = [o for o in opportunities if o.confidence >= min_confidence]
        opportunities.sort(key=lambda x: x.confidence, reverse=True)

        logger.info(f"Generated {len(opportunities)} recommendations")

        return opportunities

    def save_recommendation(self, opportunity: OptimizationOpportunity) -> Recommendation:
        """Save a recommendation to the database"""
        device = self.get_device()

        # Get parameter internal ID
        param = self.session.query(Parameter).filter_by(
            parameter_id=opportunity.parameter_id
        ).first()

        recommendation = Recommendation(
            device_id=device.id,
            parameter_id=param.id if param else None,
            current_value=opportunity.current_value,
            suggested_value=opportunity.suggested_value,
            reasoning=opportunity.reasoning,
            expected_impact=opportunity.expected_impact,
            confidence_score=opportunity.confidence,
            status='pending'
        )

        self.session.add(recommendation)
        self.session.commit()

        logger.info(f"Saved recommendation: {opportunity.parameter_name} "
                   f"{opportunity.current_value:.1f} → {opportunity.suggested_value:.1f}")

        return recommendation


def main():
    """Example usage of the analyzer"""
    analyzer = HeatPumpAnalyzer()

    # Calculate and display metrics
    logger.info("="*80)
    logger.info("HEAT PUMP EFFICIENCY ANALYSIS")
    logger.info("="*80)

    metrics = analyzer.calculate_metrics(hours_back=24)

    logger.info(f"\nPeriod: {metrics.period_start} to {metrics.period_end}")
    logger.info(f"\nTemperatures:")
    logger.info(f"  Outdoor:  {metrics.avg_outdoor_temp:>6.1f}°C")
    logger.info(f"  Indoor:   {metrics.avg_indoor_temp:>6.1f}°C")
    logger.info(f"  Supply:   {metrics.avg_supply_temp:>6.1f}°C")
    logger.info(f"  Return:   {metrics.avg_return_temp:>6.1f}°C")
    logger.info(f"\nΔT (Supply-Return):")
    logger.info(f"  All readings: {metrics.delta_t:.1f}°C")
    if metrics.delta_t_active is not None:
        logger.info(f"  Space heating (active): {metrics.delta_t_active:.1f}°C  {'✅' if 3 <= metrics.delta_t_active <= 8 else '⚠️'}")
    if metrics.delta_t_hot_water is not None:
        logger.info(f"  Hot water production: {metrics.delta_t_hot_water:.1f}°C")

    logger.info(f"\nSystem Status:")
    logger.info(f"  Heating curve: {metrics.heating_curve}")
    logger.info(f"  Curve offset:  {metrics.curve_offset}")
    logger.info(f"  Degree minutes: {metrics.degree_minutes:.0f}")
    logger.info(f"  Avg compressor freq: {metrics.avg_compressor_freq:.0f} Hz")

    if metrics.estimated_cop:
        logger.info(f"  Estimated COP: {metrics.estimated_cop:.2f}")

    if metrics.compressor_runtime_hours:
        logger.info(f"  Compressor runtime: {metrics.compressor_runtime_hours:.1f} hours")

    # Generate recommendations
    logger.info("\n" + "="*80)
    logger.info("OPTIMIZATION RECOMMENDATIONS")
    logger.info("="*80 + "\n")

    opportunities = analyzer.generate_recommendations(hours_back=24)

    if opportunities:
        for i, opp in enumerate(opportunities, 1):
            logger.info(f"[{i}] {opp.parameter_name}")
            logger.info(f"    Current: {opp.current_value:.1f}")
            logger.info(f"    Suggested: {opp.suggested_value:.1f}")
            logger.info(f"    Impact: {opp.expected_impact}")
            logger.info(f"    Reasoning: {opp.reasoning}")
            logger.info(f"    Confidence: {opp.confidence*100:.0f}%")
            logger.info("")

            # Save to database
            analyzer.save_recommendation(opp)
    else:
        logger.info("No optimization opportunities identified.")
        logger.info("System appears to be operating efficiently.")

    logger.info("="*80)


if __name__ == '__main__':
    main()
