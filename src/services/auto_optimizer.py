"""
Automatic Optimization Engine
Analyzes system performance and automatically adjusts parameters for optimal operation
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from loguru import logger

from services.analyzer import HeatPumpAnalyzer
from services.optimizer import SmartOptimizer
from integrations.api_client import MyUplinkClient
from integrations.auth import MyUplinkAuth
from data.models import Device, ParameterChange, init_db
from sqlalchemy.orm import sessionmaker


@dataclass
class OptimizationAction:
    """Represents a planned optimization action"""
    parameter_id: str
    parameter_name: str
    current_value: float
    new_value: float
    reason: str
    expected_cop_improvement: float
    expected_savings_yearly: float
    confidence: float
    priority: str  # 'critical', 'high', 'medium', 'low'


class AutoOptimizer:
    """
    Automatic optimization engine for Nibe F730 heat pump

    Key optimizable parameters:
    - 47007: Heating curve (0-15)
    - 47011: Curve offset (-10 to 10)
    - 47015: Room temperature setpoint (20-70°C / 200-700 in API)
    - 47206: Start compressor (-1000 to -30 DM)
    - 48132: Hot water boost (0-4)
    - 47041: Hot water demand (0-1)
    """

    # Optimization constraints
    MIN_HOURS_BETWEEN_CHANGES = 48  # Wait 48h between automatic changes
    MAX_CHANGES_PER_WEEK = 3        # Maximum automatic changes per week
    MIN_CONFIDENCE = 0.70           # Minimum confidence to auto-apply (70%)

    # Parameter limits (safety bounds)
    SAFE_LIMITS = {
        '47007': (3.0, 10.0),      # Heating curve: 3-10 (avoid extremes)
        '47011': (-5.0, 5.0),      # Offset: -5 to +5 (avoid extremes)
        '47015': (190.0, 230.0),   # Room temp: 19-23°C (comfort range)
        '47206': (-400.0, -100.0), # Start compressor: -400 to -100 DM
    }

    def __init__(self,
                 analyzer: HeatPumpAnalyzer,
                 api_client: MyUplinkClient,
                 device_id: str,
                 dry_run: bool = True):
        """
        Initialize Auto Optimizer

        Args:
            analyzer: HeatPumpAnalyzer instance
            api_client: MyUplinkClient instance
            device_id: Device ID from myUplink
            dry_run: If True, only suggest changes without applying them
        """
        self.analyzer = analyzer
        self.api_client = api_client
        self.device_id = device_id
        self.dry_run = dry_run
        self.smart_optimizer = SmartOptimizer(analyzer)

        # Database session for logging
        engine = analyzer.engine
        self.SessionMaker = sessionmaker(bind=engine)

    def can_make_change(self) -> Tuple[bool, str]:
        """
        Check if we're allowed to make an automatic change

        Returns:
            (allowed, reason)
        """
        session = self.SessionMaker()
        try:
            # Check recent changes
            cutoff_time = datetime.utcnow() - timedelta(hours=self.MIN_HOURS_BETWEEN_CHANGES)
            recent_changes = session.query(ParameterChange).filter(
                ParameterChange.timestamp >= cutoff_time,
                ParameterChange.reason.like('Auto Optimizer:%')
            ).count()

            if recent_changes > 0:
                return False, f"Recent auto-change within {self.MIN_HOURS_BETWEEN_CHANGES}h"

            # Check weekly limit
            week_ago = datetime.utcnow() - timedelta(days=7)
            weekly_changes = session.query(ParameterChange).filter(
                ParameterChange.timestamp >= week_ago,
                ParameterChange.reason.like('Auto Optimizer:%')
            ).count()

            if weekly_changes >= self.MAX_CHANGES_PER_WEEK:
                return False, f"Weekly limit reached ({weekly_changes}/{self.MAX_CHANGES_PER_WEEK})"

            return True, "OK"

        finally:
            session.close()

    def get_optimization_actions(self, hours_back: int = 72) -> List[OptimizationAction]:
        """
        Analyze system and generate optimization actions

        Args:
            hours_back: Hours of data to analyze

        Returns:
            List of OptimizationAction objects, sorted by priority
        """
        from data.database import SessionLocal
        from data.models import Device

        actions = []
        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)

        # Get user settings from database
        session = SessionLocal()
        try:
            device = session.query(Device).first()
            min_temp = device.min_indoor_temp_user_setting if device else 20.5
            target_min = device.target_indoor_temp_min if device else 20.5
            target_max = device.target_indoor_temp_max if device else 22.0
        finally:
            session.close()

        logger.info(f"Analyzing system for optimization opportunities...")
        logger.info(f"Current metrics: COP={metrics.estimated_cop:.2f}, Delta T={metrics.delta_t_active:.1f}°C, Indoor={metrics.avg_indoor_temp:.1f}°C")
        logger.info(f"User settings: Min={min_temp:.1f}°C, Target={target_min:.1f}-{target_max:.1f}°C")

        # Action 1: Low COP - Lower heating curve
        if metrics.estimated_cop and metrics.estimated_cop < 3.0:
            if metrics.avg_outdoor_temp > -5:  # Only if not too cold
                current_curve = metrics.heating_curve

                # Calculate optimal reduction
                cop_deficit = 3.5 - metrics.estimated_cop
                reduction = min(1.0, cop_deficit * 0.5)  # 0.5 step per COP point deficit
                new_curve = current_curve - reduction

                # Apply safety limits
                safe_min, safe_max = self.SAFE_LIMITS['47007']
                new_curve = max(safe_min, min(safe_max, new_curve))
                new_curve = round(new_curve)  # Integer only

                if new_curve != current_curve:
                    actions.append(OptimizationAction(
                        parameter_id='47007',
                        parameter_name='Värmekurva',
                        current_value=current_curve,
                        new_value=new_curve,
                        reason=f'COP för låg ({metrics.estimated_cop:.2f}), sänk kurva för bättre effektivitet',
                        expected_cop_improvement=0.3,
                        expected_savings_yearly=1200,
                        confidence=0.80,
                        priority='high' if metrics.estimated_cop < 2.5 else 'medium'
                    ))

        # Action 2: Indoor temperature too high - Lower offset
        if metrics.avg_indoor_temp > target_max:
            current_offset = metrics.curve_offset
            target_center = (target_min + target_max) / 2
            temp_excess = metrics.avg_indoor_temp - target_center
            reduction = round(min(2, temp_excess))  # Max 2 steps
            new_offset = current_offset - reduction

            safe_min, safe_max = self.SAFE_LIMITS['47011']
            new_offset = max(safe_min, min(safe_max, new_offset))
            new_offset = round(new_offset)

            if new_offset != current_offset:
                savings = temp_excess * 200  # Approx 200 kr/year per excess degree
                actions.append(OptimizationAction(
                    parameter_id='47011',
                    parameter_name='Kurvjustering',
                    current_value=current_offset,
                    new_value=new_offset,
                    reason=f'För varmt inne ({metrics.avg_indoor_temp:.1f}°C), sänk för energibesparing',
                    expected_cop_improvement=0.1,
                    expected_savings_yearly=savings,
                    confidence=0.85,
                    priority='medium'
                ))

        # Action 3: Indoor temperature too low - Raise offset
        elif metrics.avg_indoor_temp < min_temp:
            current_offset = metrics.curve_offset
            temp_deficit = target_min - metrics.avg_indoor_temp
            increase = round(min(2, temp_deficit * 1.5))  # Be more aggressive for comfort
            new_offset = current_offset + increase

            safe_min, safe_max = self.SAFE_LIMITS['47011']
            new_offset = max(safe_min, min(safe_max, new_offset))
            new_offset = round(new_offset)

            if new_offset != current_offset:
                actions.append(OptimizationAction(
                    parameter_id='47011',
                    parameter_name='Kurvjustering',
                    current_value=current_offset,
                    new_value=new_offset,
                    reason=f'För kallt inne ({metrics.avg_indoor_temp:.1f}°C), höj för komfort',
                    expected_cop_improvement=0.0,
                    expected_savings_yearly=0,
                    confidence=0.95,
                    priority='critical'  # Comfort is critical!
                ))

        # Action 4: High Delta T - May indicate flow issue or too low curve
        if metrics.delta_t_active and metrics.delta_t_active > 8.0:
            # This suggests we might need higher flow or the curve is too high
            # For now, suggest manual pump adjustment (not auto-optimized yet)
            logger.info(f"⚠️ High Delta T ({metrics.delta_t_active:.1f}°C) detected - consider pump speed adjustment")

        # Action 5: Many short cycles - Adjust compressor start point
        if metrics.heating_metrics and metrics.heating_metrics.num_cycles > 20:
            # Too many cycles - make compressor less sensitive
            logger.info(f"⚠️ Many cycles ({metrics.heating_metrics.num_cycles}) detected - consider adjusting start compressor (47206)")
            # This is advanced - not auto-optimized in v1

        # Sort by priority
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        actions.sort(key=lambda a: (priority_order[a.priority], -a.confidence))

        return actions

    def apply_action(self, action: OptimizationAction) -> bool:
        """
        Apply an optimization action

        Args:
            action: OptimizationAction to apply

        Returns:
            True if successful
        """
        try:
            if self.dry_run:
                logger.info(f"[DRY RUN] Would set {action.parameter_name} ({action.parameter_id}): {action.current_value} → {action.new_value}")
                logger.info(f"[DRY RUN] Reason: {action.reason}")
                return True

            # Apply the change via API
            logger.info(f"Setting {action.parameter_name} ({action.parameter_id}): {action.current_value} → {action.new_value}")
            self.api_client.set_point_value(self.device_id, action.parameter_id, action.new_value)

            # Log to database
            session = self.SessionMaker()
            try:
                change = ParameterChange(
                    device_id=self.device_id,
                    parameter_id=action.parameter_id,
                    parameter_name=action.parameter_name,
                    old_value=action.current_value,
                    new_value=action.new_value,
                    reason=f"Auto Optimizer: {action.reason}",
                    timestamp=datetime.utcnow()
                )
                session.add(change)
                session.commit()
                logger.info(f"✓ Change applied and logged (ID: {change.id})")
                return True
            finally:
                session.close()

        except Exception as e:
            logger.error(f"Failed to apply action: {e}")
            return False

    def run_optimization_cycle(self,
                               hours_back: int = 72,
                               auto_apply: bool = False,
                               max_actions: int = 1) -> Dict:
        """
        Run a full optimization cycle

        Args:
            hours_back: Hours of data to analyze
            auto_apply: If True, automatically apply high-confidence changes
            max_actions: Maximum actions to apply in one cycle

        Returns:
            Dict with results
        """
        logger.info("=" * 80)
        logger.info("AUTO OPTIMIZER - Starting optimization cycle")
        logger.info("=" * 80)

        # Check if we can make changes
        can_change, reason = self.can_make_change()
        if not can_change and auto_apply:
            logger.warning(f"Cannot make automatic changes: {reason}")
            auto_apply = False

        # Get optimization actions
        actions = self.get_optimization_actions(hours_back=hours_back)

        if not actions:
            logger.info("✓ System is already optimally configured - no actions needed!")
            return {
                'status': 'optimal',
                'actions_suggested': 0,
                'actions_applied': 0,
                'message': 'System operating optimally'
            }

        logger.info(f"Found {len(actions)} optimization opportunities:")
        for i, action in enumerate(actions, 1):
            logger.info(f"  {i}. [{action.priority.upper()}] {action.parameter_name}: {action.current_value} → {action.new_value}")
            logger.info(f"     Reason: {action.reason}")
            logger.info(f"     Confidence: {action.confidence*100:.0f}%, Expected savings: {action.expected_savings_yearly:.0f} kr/år")

        # Apply actions if requested
        applied = 0
        if auto_apply:
            logger.info(f"\nAuto-applying up to {max_actions} high-confidence action(s)...")

            for action in actions[:max_actions]:
                # Only apply if confidence is high enough
                if action.confidence >= self.MIN_CONFIDENCE:
                    if self.apply_action(action):
                        applied += 1
                    else:
                        logger.error(f"Failed to apply action for {action.parameter_name}")
                        break
                else:
                    logger.info(f"Skipping {action.parameter_name} - confidence too low ({action.confidence*100:.0f}% < {self.MIN_CONFIDENCE*100:.0f}%)")

        logger.info("=" * 80)
        logger.info(f"Cycle complete: {len(actions)} suggested, {applied} applied")
        logger.info("=" * 80)

        return {
            'status': 'optimized' if applied > 0 else 'suggestions_available',
            'actions_suggested': len(actions),
            'actions_applied': applied,
            'actions': [
                {
                    'parameter': a.parameter_name,
                    'current': a.current_value,
                    'suggested': a.new_value,
                    'reason': a.reason,
                    'confidence': a.confidence,
                    'priority': a.priority,
                    'expected_savings': a.expected_savings_yearly
                }
                for a in actions
            ]
        }


def main():
    """Run auto optimizer as standalone script"""
    import argparse

    parser = argparse.ArgumentParser(description='Nibe Auto Optimizer')
    parser.add_argument('--auto-apply', action='store_true', help='Automatically apply high-confidence changes')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Dry run mode (default)')
    parser.add_argument('--hours', type=int, default=72, help='Hours of data to analyze (default: 72)')
    parser.add_argument('--max-actions', type=int, default=1, help='Max actions to apply (default: 1)')

    args = parser.parse_args()

    # Initialize
    analyzer = HeatPumpAnalyzer('data/nibe_autotuner.db')
    auth = MyUplinkAuth()
    auth.load_tokens()
    api_client = MyUplinkClient(auth)

    # Get device
    session = analyzer.session
    device = session.query(Device).first()
    if not device:
        logger.error("No device found in database!")
        return

    # Create optimizer
    optimizer = AutoOptimizer(
        analyzer=analyzer,
        api_client=api_client,
        device_id=device.device_id,
        dry_run=args.dry_run
    )

    # Run optimization
    result = optimizer.run_optimization_cycle(
        hours_back=args.hours,
        auto_apply=args.auto_apply and not args.dry_run,
        max_actions=args.max_actions
    )

    logger.info(f"\nResult: {result}")


if __name__ == '__main__':
    main()
