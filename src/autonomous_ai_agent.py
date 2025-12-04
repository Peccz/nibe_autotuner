"""
Autonomous AI Agent for Nibe Autotuner
Uses Claude API to make intelligent decisions based on real-time data
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import anthropic
from loguru import logger

from analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from weather_service import SMHIWeatherService


@dataclass
class AIDecision:
    """AI decision result"""
    action: str  # 'adjust', 'hold', 'investigate'
    parameter: Optional[str]
    current_value: Optional[float]
    suggested_value: Optional[float]
    reasoning: str
    confidence: float
    expected_impact: str


class AutonomousAIAgent:
    """
    Autonomous AI agent that uses Claude to make decisions

    The agent can:
    1. Analyze system performance autonomously
    2. Detect anomalies and patterns
    3. Make optimization decisions with reasoning
    4. Learn from A/B test results
    5. Handle edge cases and unexpected situations

    Unlike rule-based Auto-Optimizer, this agent uses natural language
    understanding and can adapt to novel situations.
    """

    def __init__(
        self,
        analyzer: HeatPumpAnalyzer,
        api_client: MyUplinkClient,
        weather_service: SMHIWeatherService,
        device_id: str,
        anthropic_api_key: Optional[str] = None
    ):
        """
        Initialize autonomous AI agent

        Args:
            analyzer: HeatPumpAnalyzer instance
            api_client: MyUplink API client
            weather_service: Weather service
            device_id: Device ID
            anthropic_api_key: Claude API key (or from env ANTHROPIC_API_KEY)
        """
        self.analyzer = analyzer
        self.api_client = api_client
        self.weather_service = weather_service
        self.device_id = device_id

        # Initialize Claude client
        api_key = anthropic_api_key or os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found. Set it in .env or pass as parameter")

        self.client = anthropic.Anthropic(api_key=api_key)

    def _build_system_context(self, hours_back: int = 72) -> str:
        """
        Build comprehensive system context for AI

        Returns:
            Detailed context string with all relevant data
        """
        # Get current metrics
        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)

        # Get weather forecast
        weather_rec = self.weather_service.should_adjust_for_weather()

        # Get recent changes from database
        from models import ParameterChange
        recent_changes = self.analyzer.session.query(ParameterChange).order_by(
            ParameterChange.timestamp.desc()
        ).limit(5).all()

        # Get A/B test results
        from models import ABTestResult
        recent_tests = self.analyzer.session.query(ABTestResult).order_by(
            ABTestResult.created_at.desc()
        ).limit(3).all()

        # Build context
        context = f"""# NIBE F730 HEAT PUMP SYSTEM STATUS

## Current Date & Time
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## System Overview
- Location: Upplands Väsby, Sweden
- House: 160 sqm, 5 people (2 adults, 3 children)
- Heat Pump: Nibe F730 (exhaust air heat pump, 1.1-6.0 kW)

## Current Performance (Last {hours_back}h)

### Temperatures
- Outdoor: {metrics.avg_outdoor_temp:.1f}°C
- Indoor: {metrics.avg_indoor_temp:.1f}°C
- Supply: {metrics.avg_supply_temp:.1f}°C
- Return: {metrics.avg_return_temp:.1f}°C
- Delta T: {metrics.delta_t:.1f}°C

### Efficiency
- COP (estimated): {metrics.estimated_cop:.2f}
- COP Rating: {self.analyzer.get_cop_rating_heating(metrics.estimated_cop)['badge']}
- Delta T Rating: {self.analyzer.get_delta_t_rating(metrics.delta_t_active)['badge'] if metrics.delta_t_active else 'N/A'}

### Settings
- Heating Curve: {metrics.heating_curve}
- Curve Offset: {metrics.curve_offset}
- Degree Minutes: {metrics.degree_minutes:.0f} (target: -200)

### Operation
- Compressor Runtime: {metrics.compressor_runtime_hours:.1f}h
- Compressor Frequency: {metrics.avg_compressor_freq:.0f} Hz
"""

        # Add heating metrics if available
        if metrics.heating_metrics:
            hm = metrics.heating_metrics
            context += f"""
### Space Heating
- COP: {hm.cop:.2f if hm.cop else 'N/A'}
- Delta T: {hm.delta_t:.1f if hm.delta_t else 'N/A'}°C
- Runtime: {hm.runtime_hours:.1f if hm.runtime_hours else 'N/A'}h
- Cycles: {hm.num_cycles}
"""

        # Add hot water metrics if available
        if metrics.hot_water_metrics:
            hwm = metrics.hot_water_metrics
            context += f"""
### Hot Water Production
- COP: {hwm.cop:.2f if hwm.cop else 'N/A'}
- Runtime: {hwm.runtime_hours:.1f if hwm.runtime_hours else 'N/A'}h
- Hot Water Temp: {hwm.avg_hot_water_temp:.1f if hwm.avg_hot_water_temp else 'N/A'}°C
"""

        # Add weather
        context += f"""
## Weather Forecast (SMHI)
- Current: {metrics.avg_outdoor_temp:.1f}°C
- Needs Adjustment: {weather_rec['needs_adjustment']}
"""
        if weather_rec['needs_adjustment']:
            context += f"""- Reason: {weather_rec['reason']}
- Suggested Action: {weather_rec['suggested_action']}
- Urgency: {weather_rec['urgency']}
"""

        # Add recent changes
        if recent_changes:
            context += "\n## Recent Parameter Changes\n"
            for change in recent_changes:
                context += f"""- {change.timestamp.strftime('%Y-%m-%d %H:%M')}: {change.parameter.parameter_name}
  {change.old_value} → {change.new_value}
  Reason: {change.reason}
"""

        # Add A/B test results
        if recent_tests:
            context += "\n## Recent A/B Test Results\n"
            for test in recent_tests:
                context += f"""- Change #{test.parameter_change_id}:
  COP: {test.cop_before:.2f} → {test.cop_after:.2f} ({test.cop_change_percent:+.1f}%)
  Success Score: {test.success_score:.0f}/100
  Recommendation: {test.recommendation}
"""

        return context

    def analyze_and_decide(self, hours_back: int = 72, dry_run: bool = True) -> AIDecision:
        """
        Analyze system and make decision using Claude AI

        Args:
            hours_back: Hours of data to analyze
            dry_run: If True, only suggest (don't apply)

        Returns:
            AIDecision with action and reasoning
        """
        logger.info("="*80)
        logger.info("AUTONOMOUS AI AGENT - Analysis")
        logger.info("="*80)

        # Build context
        context = self._build_system_context(hours_back)

        # Create prompt for Claude
        prompt = f"""You are an expert HVAC engineer and data scientist analyzing a Nibe F730 heat pump system.

{context}

## Your Task

Analyze the system performance and decide if any adjustments are needed.

Consider:
1. **Efficiency**: Is COP optimal for current conditions?
2. **Comfort**: Is indoor temperature comfortable (20-22°C)?
3. **Stability**: Are there too many compressor cycles?
4. **Weather**: Should we adjust for upcoming weather?
5. **Cost**: Can we reduce energy consumption without sacrificing comfort?
6. **Learning**: What can we learn from recent A/B tests?

## Available Parameters to Adjust

1. **Heating Curve** (3-10): Main heating setting
   - Higher = More heating
   - Lower = Less heating, better efficiency

2. **Curve Offset** (-5 to +5): Fine-tuning
   - +1 = ~0.5°C warmer
   - -1 = ~0.5°C cooler

3. **Room Temperature** (19-23°C): Direct setpoint

4. **Start Compressor** (-400 to -100 DM): When compressor starts
   - Lower (more negative) = Later start
   - Higher (less negative) = Earlier start

## Safety Rules

- NEVER make indoor temp <20°C (comfort priority!)
- Max 1 parameter change at a time
- Only suggest changes with >70% confidence
- Consider 48h A/B test period (don't change too often)
- Respect min/max parameter limits

## Output Format

Respond with a JSON object:

{{
  "action": "adjust" | "hold" | "investigate",
  "parameter": "heating_curve" | "curve_offset" | "room_temp" | "start_compressor" | null,
  "current_value": <number> | null,
  "suggested_value": <number> | null,
  "reasoning": "<detailed explanation of why>",
  "confidence": <0.0-1.0>,
  "expected_impact": "<what will happen>"
}}

**Examples:**

If system is optimal:
{{
  "action": "hold",
  "parameter": null,
  "current_value": null,
  "suggested_value": null,
  "reasoning": "System is performing well. COP is good for current outdoor temperature. Indoor temperature is comfortable. No changes needed.",
  "confidence": 0.9,
  "expected_impact": "Continue stable operation"
}}

If adjustment needed:
{{
  "action": "adjust",
  "parameter": "curve_offset",
  "current_value": 0,
  "suggested_value": -1,
  "reasoning": "Indoor temperature is 22.3°C which is slightly warm. Reducing curve offset by 1 will lower temperature by ~0.5°C while improving COP by ~0.1. This will save energy without sacrificing comfort.",
  "confidence": 0.85,
  "expected_impact": "Indoor temp will decrease to ~21.8°C. COP will improve from 3.07 to ~3.17. Daily savings: ~2 kr."
}}

If more data needed:
{{
  "action": "investigate",
  "parameter": null,
  "current_value": null,
  "suggested_value": null,
  "reasoning": "Delta T is unusually low (1.6°C) which suggests high flow. Need to monitor for another 24h to see if this is temporary or persistent before adjusting pump speed.",
  "confidence": 0.75,
  "expected_impact": "Continue monitoring Delta T trends"
}}

Now analyze the system and provide your decision:"""

        # Call Claude API
        logger.info("Calling Claude API for analysis...")

        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Parse response
            response_text = message.content[0].text
            logger.info(f"Claude response:\n{response_text}")

            # Extract JSON from response
            # Claude might wrap JSON in markdown code blocks
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text.strip()

            decision_data = json.loads(json_str)

            # Create AIDecision object
            decision = AIDecision(
                action=decision_data['action'],
                parameter=decision_data.get('parameter'),
                current_value=decision_data.get('current_value'),
                suggested_value=decision_data.get('suggested_value'),
                reasoning=decision_data['reasoning'],
                confidence=decision_data['confidence'],
                expected_impact=decision_data['expected_impact']
            )

            logger.info("="*80)
            logger.info("AI DECISION")
            logger.info("="*80)
            logger.info(f"Action: {decision.action}")
            if decision.action == 'adjust':
                logger.info(f"Parameter: {decision.parameter}")
                logger.info(f"Change: {decision.current_value} → {decision.suggested_value}")
            logger.info(f"Reasoning: {decision.reasoning}")
            logger.info(f"Confidence: {decision.confidence*100:.0f}%")
            logger.info(f"Expected Impact: {decision.expected_impact}")
            logger.info("="*80)

            # Log decision to database
            self._log_decision(decision, dry_run=dry_run)

            # Apply change if not dry run and confidence is high enough
            if not dry_run and decision.action == 'adjust' and decision.confidence >= 0.70:
                self._apply_decision(decision)

            return decision

        except Exception as e:
            logger.error(f"Error calling Claude API: {e}")
            raise

    def _log_decision(self, decision: AIDecision, dry_run: bool = True):
        """
        Log AI decision to database

        Args:
            decision: AIDecision to log
            dry_run: Whether this was a dry run
        """
        from models import AIDecisionLog, Parameter

        # Get parameter if this is an adjustment
        param_id = None
        if decision.action == 'adjust' and decision.parameter:
            param_map = {
                'heating_curve': '47007',
                'curve_offset': '47011',
                'room_temp': '47015',
                'start_compressor': '47206'
            }
            parameter_api_id = param_map.get(decision.parameter)
            if parameter_api_id:
                param = self.analyzer.session.query(Parameter).filter_by(
                    parameter_id=parameter_api_id
                ).first()
                if param:
                    param_id = param.id

        # Create log entry
        log_entry = AIDecisionLog(
            action=decision.action,
            parameter_id=param_id,
            current_value=decision.current_value,
            suggested_value=decision.suggested_value,
            reasoning=decision.reasoning[:2000] if decision.reasoning else None,
            confidence=decision.confidence,
            expected_impact=decision.expected_impact[:500] if decision.expected_impact else None,
            applied=not dry_run and decision.action == 'adjust' and decision.confidence >= 0.70
        )
        self.analyzer.session.add(log_entry)
        self.analyzer.session.commit()

        logger.info(f"Logged decision to database (ID: {log_entry.id})")

    def _apply_decision(self, decision: AIDecision) -> bool:
        """
        Apply AI decision to the system

        Args:
            decision: AIDecision to apply

        Returns:
            True if successful
        """
        if decision.action != 'adjust' or not decision.parameter:
            logger.warning("Decision does not include adjustment")
            return False

        # Map parameter names to IDs
        param_map = {
            'heating_curve': '47007',
            'curve_offset': '47011',
            'room_temp': '47015',
            'start_compressor': '47206'
        }

        param_id = param_map.get(decision.parameter)
        if not param_id:
            logger.error(f"Unknown parameter: {decision.parameter}")
            return False

        try:
            logger.info(f"Applying change: {decision.parameter} = {decision.suggested_value}")

            self.api_client.set_point_value(
                self.device_id,
                param_id,
                decision.suggested_value
            )

            # Log change to database
            from models import ParameterChange, Parameter
            param = self.analyzer.session.query(Parameter).filter_by(
                parameter_id=param_id
            ).first()

            if param:
                change = ParameterChange(
                    device_id=self.analyzer.get_device().id,
                    parameter_id=param.id,
                    timestamp=datetime.utcnow(),
                    old_value=decision.current_value,
                    new_value=decision.suggested_value,
                    reason=f"Autonomous AI: {decision.reasoning[:200]}",
                    applied_by='ai'
                )
                self.analyzer.session.add(change)
                self.analyzer.session.commit()

            logger.info(f"✓ Change applied successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to apply decision: {e}")
            return False


def main():
    """Test autonomous AI agent"""
    from models import Device, init_db
    from sqlalchemy.orm import sessionmaker

    # Initialize
    engine = init_db('sqlite:///./data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()
    device = session.query(Device).first()

    if not device:
        logger.error("No device found in database")
        return

    # Check for API key
    if not os.getenv('ANTHROPIC_API_KEY'):
        logger.error("ANTHROPIC_API_KEY not set in environment")
        logger.info("Set it in .env file or export ANTHROPIC_API_KEY=your-key")
        return

    # Create agent
    api_client = MyUplinkClient()
    analyzer = HeatPumpAnalyzer()
    weather_service = SMHIWeatherService()

    agent = AutonomousAIAgent(
        analyzer=analyzer,
        api_client=api_client,
        weather_service=weather_service,
        device_id=device.device_id
    )

    # Analyze and decide (dry run)
    decision = agent.analyze_and_decide(hours_back=72, dry_run=True)

    logger.info("\n" + "="*80)
    logger.info("ANALYSIS COMPLETE")
    logger.info("="*80)
    logger.info("To apply changes, run with dry_run=False")
    logger.info("To schedule daily, add to crontab:")
    logger.info("0 4 * * * /home/peccz/nibe_autotuner/scripts/run_ai_agent.sh")


if __name__ == '__main__':
    main()
