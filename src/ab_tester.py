"""
A/B Testing Module - Evaluate parameter changes
Automatically captures and compares metrics before and after changes
"""
from datetime import datetime, timedelta
from typing import Optional, Dict
from loguru import logger
from sqlalchemy.orm import Session

from models import (
    Device, ParameterChange, ABTestResult,
    ParameterReading, Parameter
)
from analyzer import HeatPumpAnalyzer


class ABTester:
    """Handles A/B testing of parameter changes"""

    # Time windows for comparison
    BEFORE_HOURS = 48  # 48 hours before change
    AFTER_HOURS = 48   # 48 hours after change
    MIN_WAIT_HOURS = 48  # Wait at least 48h before evaluating

    # Scoring weights
    WEIGHT_COP = 0.40        # 40% - Most important
    WEIGHT_DELTA_T = 0.20    # 20% - Efficiency indicator
    WEIGHT_COMFORT = 0.20    # 20% - Indoor temp stability
    WEIGHT_CYCLES = 0.10     # 10% - Fewer cycles better
    WEIGHT_COST = 0.10       # 10% - Cost savings

    def __init__(self, analyzer: HeatPumpAnalyzer):
        """
        Initialize AB Tester

        Args:
            analyzer: HeatPumpAnalyzer instance for metrics calculation
        """
        self.analyzer = analyzer
        self.session = analyzer.session

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

            # Calculate changes
            cop_change = self._calc_percent_change(
                metrics_before.estimated_cop,
                metrics_after.estimated_cop
            )

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
                indoor_temp_change
            )

            # Create ABTestResult
            result = ABTestResult(
                parameter_change_id=change.id,
                before_start=before_start,
                before_end=before_end,
                after_start=after_start,
                after_end=after_end,
                # COP
                cop_before=metrics_before.estimated_cop,
                cop_after=metrics_after.estimated_cop,
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
        indoor_temp_change: float
    ) -> str:
        """Generate human-readable recommendation"""
        if success_score >= 70:
            return "✅ BEHÅLL - Mycket bra resultat!"
        elif success_score >= 55:
            return "👍 BEHÅLL - Bra förbättring"
        elif success_score >= 45:
            return "🤔 NEUTRAL - Marginell effekt"
        elif success_score >= 30:
            if abs(indoor_temp_change) > 1.0:
                return "⚠️ JUSTERA - Temperaturen påverkad"
            else:
                return "⚠️ ÖVERVÄG ÅTERSTÄLLNING - Försämring"
        else:
            return "❌ ÅTERSTÄLL - Tydlig försämring"

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
