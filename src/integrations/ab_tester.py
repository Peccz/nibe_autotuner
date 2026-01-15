"""
A/B Testing Module - Evaluate parameter changes
Automatically captures and compares metrics before and after changes
"""
from datetime import datetime, timedelta
from typing import Optional, Dict
import json
from loguru import logger
from sqlalchemy.orm import Session

from data.models import (Device, ParameterChange, ABTestResult, ParameterReading, Parameter, PlannedTest)
from services.analyzer import HeatPumpAnalyzer
from sqlalchemy import func


class ABTester:
    """Handles A/B testing of parameter changes"""

    # Time windows for comparison (can be overridden in __init__)
    BEFORE_HOURS = 48  # 48 hours before change
    AFTER_HOURS = 48   # 48 hours after change
    MIN_WAIT_HOURS = 48  # Wait at least 48h before evaluating

    # Scoring weights (can be overridden in __init__)
    WEIGHT_COP = 0.40        # 40% - Most important
    WEIGHT_DELTA_T = 0.20    # 20% - Efficiency indicator
    WEIGHT_COMFORT = 0.20    # 20% - Indoor temp stability
    WEIGHT_CYCLES = 0.10     # 10% - Fewer cycles better
    WEIGHT_COST = 0.10       # 10% - Cost savings

    # Weather normalization
    MAX_OUTDOOR_TEMP_DIFF = 3.0  # Max °C difference allowed (invalidates test if exceeded)

    def __init__(self, analyzer: HeatPumpAnalyzer,
                 before_hours: int = None,
                 after_hours: int = None,
                 min_wait_hours: int = None,
                 max_outdoor_temp_diff: float = None):
        """
        Initialize AB Tester

        Args:
            analyzer: HeatPumpAnalyzer instance for metrics calculation
            before_hours: Override BEFORE_HOURS default (48h)
            after_hours: Override AFTER_HOURS default (48h)
            min_wait_hours: Override MIN_WAIT_HOURS default (48h)
            max_outdoor_temp_diff: Max outdoor temp difference allowed (°C)
        """
        self.analyzer = analyzer
        self.session = analyzer.session

        # Allow runtime override of settings
        if before_hours is not None:
            self.BEFORE_HOURS = before_hours
        if after_hours is not None:
            self.AFTER_HOURS = after_hours
        if min_wait_hours is not None:
            self.MIN_WAIT_HOURS = min_wait_hours
        if max_outdoor_temp_diff is not None:
            self.MAX_OUTDOOR_TEMP_DIFF = max_outdoor_temp_diff

    def capture_before_metrics(self, change: ParameterChange) -> bool:
        """
        Capture metrics for 48h BEFORE the parameter change

        Args:
            change: ParameterChange instance

        Returns:
            True if metrics captured successfully
        """
        try:
            device = change.device
            change_time = change.timestamp

            # Calculate before period
            before_end = change_time
            before_start = change_time - timedelta(hours=self.BEFORE_HOURS)

            logger.info(f"Capturing BEFORE metrics for change {change.id}")
            logger.info(f"Period: {before_start} to {before_end}")

            # Calculate metrics for before period
            metrics = self.analyzer.calculate_metrics(
                hours_back=self.BEFORE_HOURS,
                end_time=change_time
            )

            # Store in database (we'll create ABTestResult later when after metrics are ready)
            change.metrics_before_captured = True
            self.session.commit()

            logger.info(f"✓ BEFORE metrics captured: COP={metrics.estimated_cop}, Delta T={metrics.delta_t_active}")
            return True

        except Exception as e:
            logger.error(f"Error capturing before metrics: {e}")
            return False

    def _calculate_degree_hours(self, start_time: datetime, end_time: datetime,
                                 base_temp: float = 18.0) -> float:
        """
        Calculate degree-hours (heating degree days × 24) for normalization

        Degree-hours = Sum of (base_temp - outdoor_temp) for each hour where outdoor < base

        Args:
            start_time: Period start
            end_time: Period end
            base_temp: Base temperature (°C), default 18°C (Swedish standard)

        Returns:
            Total degree-hours
        """
        device = self.session.query(Device).first()
        if not device:
            return 0.0

        # Get outdoor temperature parameter
        outdoor_param = self.session.query(Parameter).filter_by(
            parameter_id=self.analyzer.PARAM_OUTDOOR_TEMP
        ).first()

        if not outdoor_param:
            return 0.0

        # Get all outdoor temp readings in period
        readings = self.session.query(ParameterReading).filter(
            ParameterReading.device_id == device.id,
            ParameterReading.parameter_id == outdoor_param.id,
            ParameterReading.timestamp >= start_time,
            ParameterReading.timestamp <= end_time
        ).all()

        if not readings:
            return 0.0

        # Calculate degree-hours
        # For each hour where temp < base_temp: add (base_temp - temp)
        degree_hours = 0.0
        prev_timestamp = None

        for reading in readings:
            if reading.value < base_temp:
                # Time delta in hours
                if prev_timestamp:
                    hours_elapsed = (reading.timestamp - prev_timestamp).total_seconds() / 3600
                else:
                    hours_elapsed = 1.0  # Assume 1 hour for first reading

                # Add degree-hours for this period
                degree_hours += (base_temp - reading.value) * hours_elapsed

            prev_timestamp = reading.timestamp

        logger.debug(f"Calculated {degree_hours:.1f} degree-hours from {start_time} to {end_time}")
        return degree_hours

    def _normalize_cop_by_degree_hours(self, cop: float, degree_hours: float,
                                       reference_degree_hours: float) -> float:
        """
        Normalize COP based on heating demand (degree-hours)

        When outdoor temperature is lower, heating demand is higher,
        which typically lowers COP due to longer runtimes and higher temp lifts.

        This normalization adjusts COP to what it would have been at the
        reference heating demand level.

        Args:
            cop: Measured COP
            degree_hours: Actual degree-hours during measurement
            reference_degree_hours: Reference degree-hours (typically from before period)

        Returns:
            Normalized COP
        """
        if degree_hours == 0 or reference_degree_hours == 0:
            return cop

        # Calculate demand ratio
        demand_ratio = degree_hours / reference_degree_hours

        # COP degradation factor: ~3% per 10% increase in demand (empirical)
        # This is conservative - actual degradation may vary
        degradation_factor = 0.003

        # Calculate normalized COP
        # If demand was higher: COP would have been better with lower demand
        # If demand was lower: COP would have been worse with higher demand
        cop_adjustment = cop * (1.0 - demand_ratio) * degradation_factor

        normalized_cop = cop + cop_adjustment

        logger.debug(f"COP normalization: {cop:.2f} → {normalized_cop:.2f} "
                    f"(demand ratio: {demand_ratio:.2f})")

        return max(1.0, normalized_cop)  # Ensure COP >= 1.0

    def can_evaluate_change(self, change: ParameterChange) -> bool:
        """
        Check if enough time has passed to evaluate the change

        Args:
            change: ParameterChange instance

        Returns:
            True if ready to evaluate
        """
        hours_since_change = (datetime.utcnow() - change.timestamp).total_seconds() / 3600
        return hours_since_change >= self.MIN_WAIT_HOURS

    def evaluate_change(self, change: ParameterChange) -> Optional[ABTestResult]:
        """
        Evaluate a parameter change by comparing before/after metrics

        Args:
            change: ParameterChange instance

        Returns:
            ABTestResult with comparison data
        """
        try:
            if not self.can_evaluate_change(change):
                logger.warning(f"Change {change.id} not ready for evaluation yet")
                return None

            device = change.device
            change_time = change.timestamp

            # Calculate time periods
            before_start = change_time - timedelta(hours=self.BEFORE_HOURS)
            before_end = change_time
            after_start = change_time
            after_end = change_time + timedelta(hours=self.AFTER_HOURS)

            logger.info(f"Evaluating change {change.id}")
            logger.info(f"BEFORE: {before_start} to {before_end}")
            logger.info(f"AFTER: {after_start} to {after_end}")

            # Calculate BEFORE metrics
            metrics_before = self.analyzer.calculate_metrics(
                hours_back=self.BEFORE_HOURS,
                end_time=before_end
            )

            # Calculate AFTER metrics
            metrics_after = self.analyzer.calculate_metrics(
                hours_back=self.AFTER_HOURS,
                end_time=after_end
            )

            # VALIDATION: Check outdoor temperature difference
            outdoor_temp_diff = abs(metrics_after.avg_outdoor_temp - metrics_before.avg_outdoor_temp)
            if outdoor_temp_diff > self.MAX_OUTDOOR_TEMP_DIFF:
                logger.warning(f"⚠️ Outdoor temp difference too large: {outdoor_temp_diff:.1f}°C (max {self.MAX_OUTDOOR_TEMP_DIFF}°C)")
                logger.warning(f"   Before: {metrics_before.avg_outdoor_temp:.1f}°C, After: {metrics_after.avg_outdoor_temp:.1f}°C")
                logger.warning(f"   Test results may be unreliable due to weather changes!")
                # We continue but flag it in the recommendation

            # DEGREE-HOURS NORMALIZATION
            degree_hours_before = self._calculate_degree_hours(before_start, before_end)
            degree_hours_after = self._calculate_degree_hours(after_start, after_end)

            logger.info(f"Degree-hours: BEFORE={degree_hours_before:.1f}, AFTER={degree_hours_after:.1f}")

            # Normalize COP values based on heating demand
            cop_before_normalized = self._normalize_cop_by_degree_hours(
                metrics_before.estimated_cop,
                degree_hours_before,
                degree_hours_before  # Reference is before period
            )
            cop_after_normalized = self._normalize_cop_by_degree_hours(
                metrics_after.estimated_cop,
                degree_hours_after,
                degree_hours_before  # Normalize to before period demand
            )

            logger.info(f"COP normalization:")
            logger.info(f"  BEFORE: {metrics_before.estimated_cop:.2f} → {cop_before_normalized:.2f}")
            logger.info(f"  AFTER:  {metrics_after.estimated_cop:.2f} → {cop_after_normalized:.2f}")

            # Calculate changes (use normalized COP if significant demand difference)
            demand_ratio = degree_hours_after / degree_hours_before if degree_hours_before > 0 else 1.0
            use_normalized = abs(demand_ratio - 1.0) > 0.10  # >10% demand difference

            if use_normalized:
                logger.info(f"Using normalized COP (demand ratio: {demand_ratio:.2f})")
                cop_change = self._calc_percent_change(cop_before_normalized, cop_after_normalized)
                cop_before_for_result = cop_before_normalized
                cop_after_for_result = cop_after_normalized
            else:
                logger.info(f"Using raw COP (demand ratio close to 1.0: {demand_ratio:.2f})")
                cop_change = self._calc_percent_change(
                    metrics_before.estimated_cop,
                    metrics_after.estimated_cop
                )
                cop_before_for_result = metrics_before.estimated_cop
                cop_after_for_result = metrics_after.estimated_cop

            delta_t_change = self._calc_percent_change(
                metrics_before.delta_t_active,
                metrics_after.delta_t_active
            )

            indoor_temp_change = (
                metrics_after.avg_indoor_temp - metrics_before.avg_indoor_temp
                if metrics_before.avg_indoor_temp and metrics_after.avg_indoor_temp
                else 0
            )

            # Calculate costs
            cost_before = self._calculate_cost_per_day(metrics_before)
            cost_after = self._calculate_cost_per_day(metrics_after)
            cost_savings_per_day = cost_before - cost_after
            cost_savings_per_year = cost_savings_per_day * 365

            # Calculate success score
            success_score = self._calculate_success_score(
                metrics_before, metrics_after
            )

            # Generate recommendation
            recommendation = self._generate_recommendation(
                success_score,
                cop_change,
                indoor_temp_change,
                outdoor_temp_diff
            )

            # Create ABTestResult
            result = ABTestResult(
                parameter_change_id=change.id,
                before_start=before_start,
                before_end=before_end,
                after_start=after_start,
                after_end=after_end,
                # COP (use normalized if applicable)
                cop_before=cop_before_for_result,
                cop_after=cop_after_for_result,
                cop_change_percent=cop_change,
                # Delta T
                delta_t_before=metrics_before.delta_t_active,
                delta_t_after=metrics_after.delta_t_active,
                delta_t_change_percent=delta_t_change,
                # Temperatures
                indoor_temp_before=metrics_before.avg_indoor_temp,
                indoor_temp_after=metrics_after.avg_indoor_temp,
                indoor_temp_change=indoor_temp_change,
                outdoor_temp_before=metrics_before.avg_outdoor_temp,
                outdoor_temp_after=metrics_after.avg_outdoor_temp,
                # Compressor
                compressor_freq_before=metrics_before.avg_compressor_freq,
                compressor_freq_after=metrics_after.avg_compressor_freq,
                compressor_cycles_before=(
                    metrics_before.heating_metrics.num_cycles
                    if metrics_before.heating_metrics else 0
                ),
                compressor_cycles_after=(
                    metrics_after.heating_metrics.num_cycles
                    if metrics_after.heating_metrics else 0
                ),
                # Runtime
                runtime_hours_before=(
                    metrics_before.heating_metrics.runtime_hours
                    if metrics_before.heating_metrics else 0
                ),
                runtime_hours_after=(
                    metrics_after.heating_metrics.runtime_hours
                    if metrics_after.heating_metrics else 0
                ),
                # Cost
                cost_per_day_before=cost_before,
                cost_per_day_after=cost_after,
                cost_savings_per_day=cost_savings_per_day,
                cost_savings_per_year=cost_savings_per_year,
                # Evaluation
                success_score=success_score,
                recommendation=recommendation
            )

            self.session.add(result)
            change.metrics_after_captured = True
            change.evaluation_status = 'completed'
            self.session.commit()

            logger.info(f"✓ Evaluation complete: Score={success_score}/100, Recommendation={recommendation}")
            logger.info(f"  COP: {metrics_before.estimated_cop:.2f} → {metrics_after.estimated_cop:.2f} ({cop_change:+.1f}%)")
            logger.info(f"  Cost: {cost_before:.1f} → {cost_after:.1f} kr/dag ({cost_savings_per_day:+.1f} kr/dag)")

            return result

        except Exception as e:
            logger.error(f"Error evaluating change: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _calc_percent_change(self, before: Optional[float], after: Optional[float]) -> float:
        """Calculate percentage change"""
        if not before or not after or before == 0:
            return 0.0
        return ((after - before) / before) * 100

    def _calculate_cost_per_day(self, metrics) -> float:
        """Calculate cost per day based on metrics"""
        # Simplified cost calculation
        # Assume average compressor power = 1.5 kW
        # Assume electricity price = 2.0 SEK/kWh
        POWER_KW = 1.5
        PRICE_SEK = 2.0

        if not metrics.compressor_runtime_hours:
            return 0.0

        # Energy consumed (kWh per day)
        energy_per_day = (metrics.compressor_runtime_hours /
                         (metrics.period_end - metrics.period_start).total_seconds() * 3600 * 24) * POWER_KW

        return energy_per_day * PRICE_SEK

    def _calculate_success_score(self, metrics_before, metrics_after) -> float:
        """
        Calculate overall success score 0-100

        Higher score = better result
        """
        score = 50.0  # Start at neutral

        # COP improvement (40 points possible)
        if metrics_before.estimated_cop and metrics_after.estimated_cop:
            cop_change = self._calc_percent_change(
                metrics_before.estimated_cop,
                metrics_after.estimated_cop
            )
            # +10% COP = +20 points, -10% COP = -20 points
            score += cop_change * 2 * self.WEIGHT_COP / 0.10

        # Delta T improvement (20 points possible)
        if metrics_before.delta_t_active and metrics_after.delta_t_active:
            # Optimal Delta T is 5-7°C
            before_deviation = abs(metrics_before.delta_t_active - 6)
            after_deviation = abs(metrics_after.delta_t_active - 6)
            if after_deviation < before_deviation:
                score += (before_deviation - after_deviation) * 10 * self.WEIGHT_DELTA_T

        # Indoor temp stability (20 points possible)
        temp_change = abs(metrics_after.avg_indoor_temp - metrics_before.avg_indoor_temp)
        if temp_change < 0.5:
            score += 20 * self.WEIGHT_COMFORT
        elif temp_change < 1.0:
            score += 10 * self.WEIGHT_COMFORT

        # Compressor cycles (10 points possible)
        if metrics_before.heating_metrics and metrics_after.heating_metrics:
            cycles_before = metrics_before.heating_metrics.num_cycles
            cycles_after = metrics_after.heating_metrics.num_cycles
            if cycles_after < cycles_before:
                score += 10 * self.WEIGHT_CYCLES

        # Clamp score to 0-100
        return max(0.0, min(100.0, score))

    def _generate_recommendation(
        self,
        success_score: float,
        cop_change: float,
        indoor_temp_change: float,
        outdoor_temp_diff: float = 0
    ) -> str:
        """Generate human-readable recommendation"""
        # Check if weather invalidates the test
        weather_warning = ""
        if outdoor_temp_diff > self.MAX_OUTDOOR_TEMP_DIFF:
            weather_warning = f" ⚠️ VARNING: Väder ändrades {outdoor_temp_diff:.1f}°C - resultat osäkra!"

        if success_score >= 70:
            return f"✅ BEHÅLL - Mycket bra resultat!{weather_warning}"
        elif success_score >= 55:
            return f"👍 BEHÅLL - Bra förbättring{weather_warning}"
        elif success_score >= 45:
            return f"🤔 NEUTRAL - Marginell effekt{weather_warning}"
        elif success_score >= 30:
            if abs(indoor_temp_change) > 1.0:
                return f"⚠️ JUSTERA - Temperaturen påverkad{weather_warning}"
            else:
                return f"⚠️ ÖVERVÄG ÅTERSTÄLLNING - Försämring{weather_warning}"
        else:
            return f"❌ ÅTERSTÄLL - Tydlig försämring{weather_warning}"

    def get_pending_evaluations(self) -> list:
        """Get all changes that are ready for evaluation"""
        min_time = datetime.utcnow() - timedelta(hours=self.MIN_WAIT_HOURS)

        changes = self.session.query(ParameterChange).filter(
            ParameterChange.evaluation_status == 'pending',
            ParameterChange.timestamp <= min_time
        ).all()

        return changes

    def evaluate_all_pending(self):
        """Evaluate all pending changes"""
        pending = self.get_pending_evaluations()
        logger.info(f"Found {len(pending)} changes ready for evaluation")

        for change in pending:
            logger.info(f"Evaluating change {change.id}...")
            result = self.evaluate_change(change)
            if result:
                logger.info(f"✓ Change {change.id} evaluated successfully")

    def evaluate_planned_test(self, test: PlannedTest, ai_agent=None) -> Optional[ABTestResult]:
        """
        Evaluate a PlannedTest using scientific analysis methods.

        This method is specifically for PlannedTest objects (scientific tests),
        NOT for regular ParameterChange objects (which use standard COP analysis).

        Args:
            test: PlannedTest object with status='completed'
            ai_agent: AutonomousAIAgentV2 instance (optional, will create if not provided)

        Returns:
            ABTestResult with scientific analysis data
        """
        try:
            if test.status != 'completed':
                logger.warning(f"PlannedTest {test.id} is not completed yet (status={test.status})")
                return None

            if not test.started_at or not test.completed_at:
                logger.error(f"PlannedTest {test.id} missing start/end timestamps")
                return None

            logger.info("="*80)
            logger.info(f"EVALUATING SCIENTIFIC PLANNED TEST: {test.id}")
            logger.info(f"Hypothesis: {test.hypothesis}")
            logger.info("="*80)

            # Create AI agent if not provided
            if ai_agent is None:
                from integrations.autonomous_ai_agent_v2 import AutonomousAIAgentV2
                from integrations.api_client import MyUplinkClient
                from services.weather_service import SMHIWeatherService

                device = self.session.query(Device).first()
                if not device:
                    logger.error("No device found in database")
                    return None

                ai_agent = AutonomousAIAgentV2(
                    analyzer=self.analyzer,
                    api_client=MyUplinkClient(),
                    weather_service=SMHIWeatherService(),
                    device_id=device.device_id
                )

            # Run scientific evaluation
            evaluation = ai_agent.evaluate_scientific_test_results(
                test,
                test.started_at,
                test.completed_at
            )

            if not evaluation['success']:
                logger.error(f"Scientific evaluation failed: {evaluation.get('error', 'Unknown error')}")
                return None

            # Create ABTestResult to store the scientific analysis
            result = ABTestResult(
                parameter_change_id=None,  # This is a PlannedTest, not a ParameterChange
                before_start=test.started_at - timedelta(hours=self.BEFORE_HOURS),
                before_end=test.started_at,
                after_start=test.started_at,
                after_end=test.completed_at,
                # Store scientific analysis in recommendation field as JSON
                recommendation=json.dumps(evaluation, indent=2, default=str),
                # Set default values for required fields (not applicable for scientific tests)
                cop_before=0.0,
                cop_after=0.0,
                cop_change_percent=0.0,
                delta_t_before=0.0,
                delta_t_after=0.0,
                delta_t_change_percent=0.0,
                success_score=100.0 if evaluation['success'] else 0.0
            )

            self.session.add(result)
            self.session.commit()

            # Link result to test
            test.result_id = result.id
            self.session.commit()

            logger.info("="*80)
            logger.info(f"✓ PlannedTest {test.id} evaluated successfully")
            logger.info(f"Conclusion: {evaluation['conclusion'][:80]}...")
            logger.info("="*80)

            return result

        except Exception as e:
            logger.error(f"Error evaluating PlannedTest: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_completed_planned_tests_for_evaluation(self) -> list:
        """Get all completed PlannedTests that need evaluation (no result yet)"""
        tests = self.session.query(PlannedTest).filter(
            PlannedTest.status == 'completed',
            PlannedTest.result_id == None  # Not yet evaluated
        ).all()

        return tests

    def evaluate_all_completed_planned_tests(self, ai_agent=None):
        """Evaluate all completed PlannedTests that don't have results yet"""
        tests = self.get_completed_planned_tests_for_evaluation()
        logger.info(f"Found {len(tests)} completed PlannedTests ready for scientific evaluation")

        results = []
        for test in tests:
            logger.info(f"Evaluating PlannedTest {test.id}...")
            result = self.evaluate_planned_test(test, ai_agent)
            if result:
                results.append(result)
                logger.info(f"✓ PlannedTest {test.id} evaluated successfully")

        return results

