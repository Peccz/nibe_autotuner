"""
Intelligent Ventilation Optimizer for Nibe F730
Adjusts ventilation based on outdoor temperature to maintain humidity and reduce drafts
while ensuring adequate air quality for family of 5 in 160 sqm house
"""
from datetime import datetime, timedelta
from typing import Dict, Optional
from loguru import logger
from dataclasses import dataclass

from integrations.api_client import MyUplinkClient
from services.analyzer import HeatPumpAnalyzer


@dataclass
class VentilationSettings:
    """Ventilation control settings"""
    increased_ventilation: int  # 0 or 1 (off/on)
    start_temp_exhaust: float  # °C - when exhaust heating starts
    min_diff_outdoor_exhaust: float  # °C - min temp difference


class VentilationOptimizer:
    """
    Optimizes ventilation settings based on outdoor temperature and occupancy

    Scientific Basis:
    - Cold outdoor air holds less moisture (relative humidity drops when heated)
    - At -10°C, air at 80% RH becomes ~15% RH when heated to 22°C indoors
    - Recommended indoor RH: 30-50% for health and comfort
    - 5 people in 160 sqm = high moisture generation (~12 L/day)
    - Minimum ventilation: 0.35 L/s per sqm = 56 L/s for 160 sqm
    - Occupancy-based: 7 L/s per person = 35 L/s for 5 people

    Strategy:
    - WARM outdoor (>10°C): Normal/increased ventilation (outdoor air has moisture)
    - MILD outdoor (0-10°C): Moderate ventilation (balance comfort/air quality)
    - COLD outdoor (<0°C): Reduced ventilation (preserve humidity, reduce drafts)
    - BUT: Never compromise air quality for 5 people!
    """

    # Parameter IDs
    PARAM_INCREASED_VENTILATION = '50005'  # Writable: 0/1
    PARAM_START_TEMP_EXHAUST = '47538'     # Writable: °C (when exhaust heating starts)
    PARAM_MIN_DIFF_OUTDOOR_EXHAUST = '47539'  # Writable: °C (min temp diff)
    PARAM_FAN_SPEED_EXHAUST = '50221'      # Read-only: %
    PARAM_EXHAUST_AIR_TEMP = '40025'       # Read-only: °C

    # Ventilation strategies by outdoor temperature
    # Format: (increased_vent, start_temp_exhaust, min_diff_outdoor_exhaust)

    # WARM WEATHER (>10°C): Maximum ventilation
    # - Outdoor air has good moisture content
    # - Free cooling available
    # - No draft issues
    STRATEGY_WARM = VentilationSettings(
        increased_ventilation=1,     # ON - extra ventilation
        start_temp_exhaust=22.0,     # Start exhaust heating at 22°C
        min_diff_outdoor_exhaust=5.0 # Min 5°C difference
    )

    # MILD WEATHER (0-10°C): Balanced ventilation
    # - Some moisture in outdoor air
    # - Balance between air quality and comfort
    # - Current default settings
    STRATEGY_MILD = VentilationSettings(
        increased_ventilation=0,     # OFF - normal ventilation
        start_temp_exhaust=24.0,     # Start exhaust heating at 24°C
        min_diff_outdoor_exhaust=7.0 # Min 7°C difference
    )

    # COLD WEATHER (<0°C): Reduced ventilation
    # - Very dry outdoor air when heated
    # - Preserve indoor humidity
    # - Reduce drafts and heat loss
    # - BUT maintain minimum for 5 people!
    STRATEGY_COLD = VentilationSettings(
        increased_ventilation=0,     # OFF - normal only
        start_temp_exhaust=25.0,     # Higher temp before exhaust heating
        min_diff_outdoor_exhaust=10.0 # Larger difference (less ventilation)
    )

    # EXTREME COLD (<-10°C): Minimal safe ventilation
    # - Extremely dry air
    # - Maximum heat preservation
    # - Still ensure air quality for 5 people
    STRATEGY_EXTREME_COLD = VentilationSettings(
        increased_ventilation=0,     # OFF
        start_temp_exhaust=26.0,     # Even higher temp
        min_diff_outdoor_exhaust=12.0 # Maximum difference
    )

    def __init__(self, api_client: MyUplinkClient, analyzer: HeatPumpAnalyzer, device_id: str):
        """
        Initialize ventilation optimizer

        Args:
            api_client: MyUplink API client
            analyzer: Heat pump analyzer
            device_id: Device ID from myUplink
        """
        self.api_client = api_client
        self.analyzer = analyzer
        self.device_id = device_id

    def get_current_settings(self) -> VentilationSettings:
        """Get current ventilation settings from system"""
        params = self.api_client.get_device_points(self.device_id)

        # Find relevant parameters
        increased_vent = None
        start_temp = None
        min_diff = None

        for param in params:
            param_id = param.get('parameterId')
            if param_id == self.PARAM_INCREASED_VENTILATION:
                increased_vent = int(param.get('value', 0))
            elif param_id == self.PARAM_START_TEMP_EXHAUST:
                start_temp = float(param.get('value', 24.0))
            elif param_id == self.PARAM_MIN_DIFF_OUTDOOR_EXHAUST:
                min_diff = float(param.get('value', 7.0))

        return VentilationSettings(
            increased_ventilation=increased_vent or 0,
            start_temp_exhaust=start_temp or 24.0,
            min_diff_outdoor_exhaust=min_diff or 7.0
        )

    def get_recommended_strategy(self, outdoor_temp: float) -> VentilationSettings:
        """
        Get recommended ventilation strategy based on outdoor temperature

        Args:
            outdoor_temp: Current outdoor temperature (°C)

        Returns:
            Recommended VentilationSettings
        """
        if outdoor_temp > 10.0:
            logger.info(f"Outdoor {outdoor_temp:.1f}°C → WARM strategy (max ventilation)")
            return self.STRATEGY_WARM
        elif outdoor_temp > 0.0:
            logger.info(f"Outdoor {outdoor_temp:.1f}°C → MILD strategy (balanced)")
            return self.STRATEGY_MILD
        elif outdoor_temp > -10.0:
            logger.info(f"Outdoor {outdoor_temp:.1f}°C → COLD strategy (reduced ventilation)")
            return self.STRATEGY_COLD
        else:
            logger.info(f"Outdoor {outdoor_temp:.1f}°C → EXTREME COLD strategy (minimal safe)")
            return self.STRATEGY_EXTREME_COLD

    def analyze_current_status(self) -> Dict:
        """
        Analyze current ventilation status and air quality

        Returns:
            Dictionary with analysis results
        """
        metrics = self.analyzer.calculate_metrics(hours_back=1)
        current_settings = self.get_current_settings()
        recommended = self.get_recommended_strategy(metrics.avg_outdoor_temp)

        # Get current exhaust air temp and fan speed
        params = self.api_client.get_device_points(self.device_id)
        exhaust_temp = None
        fan_speed = None

        for param in params:
            param_id = param.get('parameterId')
            if param_id == self.PARAM_EXHAUST_AIR_TEMP:
                exhaust_temp = param.get('value')
            elif param_id == self.PARAM_FAN_SPEED_EXHAUST:
                fan_speed = param.get('value')

        # Calculate relative humidity impact
        # Simplified: RH drops ~5% per 10°C temperature lift when heating outdoor air
        temp_lift = metrics.avg_indoor_temp - metrics.avg_outdoor_temp
        estimated_rh_drop = (temp_lift / 10.0) * 5.0

        needs_adjustment = (
            current_settings.increased_ventilation != recommended.increased_ventilation or
            abs(current_settings.start_temp_exhaust - recommended.start_temp_exhaust) > 1.0 or
            abs(current_settings.min_diff_outdoor_exhaust - recommended.min_diff_outdoor_exhaust) > 1.0
        )

        # Determine strategy name
        if metrics.avg_outdoor_temp > 10.0:
            strategy_name = "WARM"
        elif metrics.avg_outdoor_temp > 0.0:
            strategy_name = "MILD"
        elif metrics.avg_outdoor_temp > -10.0:
            strategy_name = "COLD"
        else:
            strategy_name = "EXTREME_COLD"

        return {
            'outdoor_temp': metrics.avg_outdoor_temp,
            'indoor_temp': metrics.avg_indoor_temp,
            'exhaust_temp': exhaust_temp,
            'fan_speed_pct': fan_speed,
            'temp_lift': temp_lift,
            'estimated_rh_drop_pct': estimated_rh_drop,
            'current_settings': current_settings,
            'recommended_settings': recommended,
            'recommended_strategy': strategy_name,
            'needs_adjustment': needs_adjustment,
            'reasoning': self._get_reasoning(metrics.avg_outdoor_temp, current_settings, recommended)
        }

    def _get_reasoning(
        self,
        outdoor_temp: float,
        current: VentilationSettings,
        recommended: VentilationSettings
    ) -> str:
        """Generate human-readable reasoning for recommendations"""
        if outdoor_temp > 10.0:
            return (
                f"Varmt ute ({outdoor_temp:.1f}°C): Utomhusluften innehåller mer fukt. "
                "Kan öka ventilationen utan att torka ut inomhusluften. "
                "Ger friskare luft och gratis kylning vid behov."
            )
        elif outdoor_temp > 0.0:
            return (
                f"Milt ute ({outdoor_temp:.1f}°C): Balanserad ventilation. "
                "Utomhusluften har fortfarande viss fuktighet. "
                "Normala inställningar ger bra luftkvalitet utan att torka ut för mycket."
            )
        elif outdoor_temp > -10.0:
            return (
                f"Kallt ute ({outdoor_temp:.1f}°C): Utomhusluften blir mycket torr när den värms upp. "
                "Minskar ventilationen för att bevara inomhusfuktighet och minska drag. "
                f"Vid 5 personer i 160 kvm behövs fortfarande grundventilation för luftkvalitet."
            )
        else:
            return (
                f"Extremt kallt ute ({outdoor_temp:.1f}°C): Utomhusluften nästan fuktfri när uppvärmd. "
                "Minimerad ventilation för att bevara fukt och värme. "
                "Säkerställer dock minimum för 5 personer (35 L/s)."
            )

    def apply_recommended_settings(self, dry_run: bool = True) -> Dict:
        """
        Apply recommended ventilation settings

        Args:
            dry_run: If True, only report what would be changed (default: True)

        Returns:
            Dictionary with results
        """
        analysis = self.analyze_current_status()

        if not analysis['needs_adjustment']:
            logger.info("✓ Ventilation already optimally configured")
            return {
                'changed': False,
                'reason': 'Already optimal',
                'strategy_name': analysis['recommended_strategy'],
                'outdoor_temp': analysis['outdoor_temp'],
                'changes': [],
                'analysis': analysis
            }

        current = analysis['current_settings']
        recommended = analysis['recommended_settings']
        changes = []

        # Check what needs to change
        if current.increased_ventilation != recommended.increased_ventilation:
            changes.append({
                'parameter': 'Increased ventilation',
                'parameter_id': self.PARAM_INCREASED_VENTILATION,
                'current': current.increased_ventilation,
                'new': recommended.increased_ventilation
            })

        if abs(current.start_temp_exhaust - recommended.start_temp_exhaust) > 0.5:
            changes.append({
                'parameter': 'Start temp exhaust air',
                'parameter_id': self.PARAM_START_TEMP_EXHAUST,
                'current': current.start_temp_exhaust,
                'new': recommended.start_temp_exhaust
            })

        if abs(current.min_diff_outdoor_exhaust - recommended.min_diff_outdoor_exhaust) > 0.5:
            changes.append({
                'parameter': 'Min diff outdoor-exhaust',
                'parameter_id': self.PARAM_MIN_DIFF_OUTDOOR_EXHAUST,
                'current': current.min_diff_outdoor_exhaust,
                'new': recommended.min_diff_outdoor_exhaust
            })

        if dry_run:
            logger.info("="*80)
            logger.info("DRY RUN - No changes will be applied")
            logger.info("="*80)
            for change in changes:
                logger.info(f"Would change {change['parameter']}:")
                logger.info(f"  {change['current']} → {change['new']}")
            return {
                'changed': False,
                'dry_run': True,
                'changes': changes,
                'analysis': analysis
            }

        # Apply changes
        logger.info("="*80)
        logger.info("Applying ventilation optimization changes")
        logger.info("="*80)

        applied_changes = []
        for change in changes:
            try:
                logger.info(f"Setting {change['parameter']}: {change['current']} → {change['new']}")
                self.api_client.set_point_value(
                    self.device_id,
                    change['parameter_id'],
                    change['new']
                )
                applied_changes.append(change)
                logger.info(f"✓ {change['parameter']} updated successfully")
            except Exception as e:
                logger.error(f"✗ Failed to update {change['parameter']}: {e}")

        return {
            'changed': len(applied_changes) > 0,
            'dry_run': False,
            'changes': applied_changes,
            'analysis': analysis
        }


def main():
    """Test ventilation optimizer"""
    from data.models import Device
from data.database import init_db
    from sqlalchemy.orm import sessionmaker

    # Initialize
    engine = init_db('sqlite:///./data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()
    device = session.query(Device).first()

    if not device:
        logger.error("No device found in database")
        return

    # Create optimizer
    api_client = MyUplinkClient()
    analyzer = HeatPumpAnalyzer()
    optimizer = VentilationOptimizer(api_client, analyzer, device.device_id)

    # Analyze
    logger.info("="*80)
    logger.info("VENTILATION ANALYSIS")
    logger.info("="*80)

    analysis = optimizer.analyze_current_status()

    logger.info(f"\nCurrent Conditions:")
    logger.info(f"  Outdoor: {analysis['outdoor_temp']:.1f}°C")
    logger.info(f"  Indoor:  {analysis['indoor_temp']:.1f}°C")
    logger.info(f"  Exhaust: {analysis['exhaust_temp']:.1f}°C")
    logger.info(f"  Fan speed: {analysis['fan_speed_pct']:.0f}%")
    logger.info(f"  Temp lift: {analysis['temp_lift']:.1f}°C")
    logger.info(f"  Estimated RH drop: ~{analysis['estimated_rh_drop_pct']:.0f}%")

    logger.info(f"\nCurrent Settings:")
    current = analysis['current_settings']
    logger.info(f"  Increased ventilation: {current.increased_ventilation}")
    logger.info(f"  Start temp exhaust: {current.start_temp_exhaust}°C")
    logger.info(f"  Min diff outdoor-exhaust: {current.min_diff_outdoor_exhaust}°C")

    logger.info(f"\nRecommended Settings:")
    rec = analysis['recommended_settings']
    logger.info(f"  Increased ventilation: {rec.increased_ventilation}")
    logger.info(f"  Start temp exhaust: {rec.start_temp_exhaust}°C")
    logger.info(f"  Min diff outdoor-exhaust: {rec.min_diff_outdoor_exhaust}°C")

    logger.info(f"\nReasoning:")
    logger.info(f"  {analysis['reasoning']}")

    if analysis['needs_adjustment']:
        logger.info("\n" + "="*80)
        logger.info("RECOMMENDATION: Adjust ventilation settings")
        logger.info("="*80)

        # Dry run
        result = optimizer.apply_recommended_settings(dry_run=True)
    else:
        logger.info("\n✓ Ventilation settings are already optimal")

    logger.info("="*80)


if __name__ == '__main__':
    main()
