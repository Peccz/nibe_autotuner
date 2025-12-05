"""
Test Proposer - AI-driven test proposal generation
Analyzes recent data and proposes prioritized tests
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import anthropic
from loguru import logger

from analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from weather_service import SMHIWeatherService
from models import Device, ABTestResult, ParameterChange, Parameter, PlannedTest, init_db
from sqlalchemy.orm import sessionmaker
from config import settings


@dataclass
class TestProposal:
    """Proposed test"""
    parameter: str  # Parameter name
    parameter_id: str  # myUplink parameter ID
    current_value: float
    proposed_value: float
    hypothesis: str
    expected_improvement: str
    priority: str  # 'high', 'medium', 'low'
    confidence: float
    reasoning: str


class TestProposer:
    """
    Proposes and prioritizes tests based on system analysis

    This component:
    1. Analyzes last 24h of data each morning
    2. Identifies optimization opportunities
    3. Proposes specific tests with hypotheses
    4. Prioritizes tests by expected impact
    5. Stores proposals in database for GUI display
    """

    def __init__(
        self,
        analyzer: HeatPumpAnalyzer,
        api_client: MyUplinkClient,
        weather_service: SMHIWeatherService,
        device_id: str,
        anthropic_api_key: Optional[str] = None
    ):
        self.analyzer = analyzer
        self.api_client = api_client
        self.weather_service = weather_service
        self.device_id = device_id

        # Initialize Claude client if key provided
        api_key = anthropic_api_key or settings.ANTHROPIC_API_KEY
        if api_key:
            self.client = anthropic.Anthropic(api_key=api_key)
            self.use_ai = True
        else:
            self.client = None
            self.use_ai = False
            logger.warning("No ANTHROPIC_API_KEY found - using rule-based proposer")

    def propose_tests(self, hours_back: int = 24) -> List[TestProposal]:
        """
        Analyze system and propose prioritized tests

        Args:
            hours_back: Hours of data to analyze

        Returns:
            List of test proposals sorted by priority
        """
        logger.info("="*80)
        logger.info("TEST PROPOSER - Analyzing System")
        logger.info("="*80)

        if self.use_ai:
            proposals = self._propose_with_ai(hours_back)
        else:
            proposals = self._propose_with_rules(hours_back)

        # Store in database
        self._store_proposals(proposals)

        logger.info(f"Generated {len(proposals)} test proposals")
        for i, prop in enumerate(proposals, 1):
            logger.info(f"{i}. [{prop.priority.upper()}] {prop.parameter}: {prop.hypothesis}")

        return proposals

    def _propose_with_ai(self, hours_back: int) -> List[TestProposal]:
        """Use Claude AI to propose tests"""
        logger.info("Using AI-driven test proposal...")

        # Build context
        context = self._build_context(hours_back)

        # Create prompt
        prompt = f"""You are an expert HVAC engineer analyzing a Nibe F730 heat pump system.
Your task is to propose specific tests to optimize the system.

{context}

## Available Parameters to Test

1. **Heating Curve** (47007): Currently {context.get('heating_curve', 'unknown')}
   - Range: 3-10
   - Effect: Higher = More heating

2. **Curve Offset** (47011): Currently {context.get('curve_offset', 'unknown')}
   - Range: -5 to +5
   - Effect: +1 = ~0.5°C warmer

3. **Room Temperature** (47015): Currently {context.get('room_temp', 'unknown')}°C
   - Range: 19-23°C
   - Effect: Direct setpoint

4. **Start Compressor** (47206): Currently {context.get('start_compressor', 'unknown')} DM
   - Range: -400 to -100
   - Effect: Lower = Starts later

5. **Increased Ventilation** (50005): Currently {context.get('ventilation', 'unknown')}
   - Values: 0 (Normal), 1 (Increased)
   - Effect: More ventilation = Drier but cooler exhaust air

6. **Start Temp Exhaust** (47538): Currently {context.get('start_temp_exhaust', 'unknown')}°C
   - Range: 15-30°C
   - Effect: Temp when exhaust warming starts

## Your Task

Based on the data, propose 3-5 specific tests to run. For each test:

1. Identify the parameter to test
2. Propose the new value
3. State your hypothesis
4. Estimate expected improvement
5. Assign priority (high/medium/low)
6. Give confidence (0.0-1.0)
7. Explain reasoning

**Output as JSON array:**

```json
[
  {{
    "parameter": "curve_offset",
    "parameter_id": "47011",
    "current_value": 0,
    "proposed_value": -1,
    "hypothesis": "Reducing curve offset will maintain comfort while improving COP",
    "expected_improvement": "+0.1 COP (~3%), saves ~50 kr/month",
    "priority": "high",
    "confidence": 0.85,
    "reasoning": "Indoor temp is 22.3°C which is higher than needed. Recent A/B test showed -1 offset maintained 21.8°C. Weather is mild so good time to test."
  }},
  ...
]
```

**Guidelines:**
- Only propose tests with >60% confidence
- Prioritize based on safety + impact + confidence
- Consider recent tests (don't repeat failed tests)
- Consider weather (avoid risky tests in extreme cold)
- Prefer smaller changes for safety
- Don't propose tests that would make indoor temp <20°C

Now propose tests:"""

        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text
            logger.info(f"AI response:\n{response_text}")

            # Extract JSON
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text.strip()

            import json
            proposals_data = json.loads(json_str)

            # Convert to TestProposal objects
            proposals = []
            for data in proposals_data:
                proposals.append(TestProposal(
                    parameter=data['parameter'],
                    parameter_id=data['parameter_id'],
                    current_value=data['current_value'],
                    proposed_value=data['proposed_value'],
                    hypothesis=data['hypothesis'],
                    expected_improvement=data['expected_improvement'],
                    priority=data['priority'],
                    confidence=data['confidence'],
                    reasoning=data['reasoning']
                ))

            # Sort by priority
            priority_order = {'high': 0, 'medium': 1, 'low': 2}
            proposals.sort(key=lambda x: (priority_order[x.priority], -x.confidence))

            return proposals

        except Exception as e:
            logger.error(f"AI proposal failed: {e}")
            logger.info("Falling back to rule-based proposer")
            return self._propose_with_rules(hours_back)

    def _propose_with_rules(self, hours_back: int) -> List[TestProposal]:
        """Use rule-based logic to propose tests"""
        logger.info("Using rule-based test proposal...")

        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)
        proposals = []

        # Rule 1: Indoor temp too high
        if metrics.avg_indoor_temp > 22.0:
            proposals.append(TestProposal(
                parameter="curve_offset",
                parameter_id="47011",
                current_value=metrics.curve_offset,
                proposed_value=metrics.curve_offset - 1,
                hypothesis="Reducing curve offset will maintain comfort while improving COP",
                expected_improvement="+0.1 COP (~3%), saves ~50 kr/month",
                priority="high",
                confidence=0.80,
                reasoning=f"Indoor temp is {metrics.avg_indoor_temp:.1f}°C which is warmer than needed"
            ))

        # Rule 2: COP too low for conditions
        expected_cop = self._estimate_cop_for_temp(metrics.avg_outdoor_temp)
        if metrics.estimated_cop and metrics.estimated_cop < expected_cop - 0.15:
            proposals.append(TestProposal(
                parameter="heating_curve",
                parameter_id="47007",
                current_value=metrics.heating_curve,
                proposed_value=max(3, metrics.heating_curve - 1),
                hypothesis="Reducing heating curve will improve efficiency",
                expected_improvement="+0.15 COP (~5%), saves ~80 kr/month",
                priority="medium",
                confidence=0.70,
                reasoning=f"COP is {metrics.estimated_cop:.2f} but expected ~{expected_cop:.2f} for {metrics.avg_outdoor_temp:.1f}°C"
            ))

        # Rule 3: Cold weather - optimize ventilation
        if metrics.avg_outdoor_temp < 0:
            proposals.append(TestProposal(
                parameter="increased_ventilation",
                parameter_id="50005",
                current_value=1,  # Assume current is increased
                proposed_value=0,
                hypothesis="Reducing ventilation in cold weather will improve COP via warmer exhaust air",
                expected_improvement="+0.2 COP (~7%), saves ~100 kr/month",
                priority="high",
                confidence=0.85,
                reasoning=f"Outdoor temp is {metrics.avg_outdoor_temp:.1f}°C - reducing ventilation keeps exhaust warmer"
            ))

        # Sort by priority
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        proposals.sort(key=lambda x: (priority_order[x.priority], -x.confidence))

        return proposals

    def _build_context(self, hours_back: int) -> Dict:
        """Build context for AI or rules"""
        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)
        weather_rec = self.weather_service.should_adjust_for_weather()

        # Get recent A/B tests
        recent_tests = self.analyzer.session.query(ABTestResult).order_by(
            ABTestResult.created_at.desc()
        ).limit(5).all()

        context = {
            'avg_outdoor_temp': metrics.avg_outdoor_temp,
            'avg_indoor_temp': metrics.avg_indoor_temp,
            'avg_supply_temp': metrics.avg_supply_temp,
            'avg_return_temp': metrics.avg_return_temp,
            'estimated_cop': metrics.estimated_cop,
            'heating_curve': metrics.heating_curve,
            'curve_offset': metrics.curve_offset,
            'degree_minutes': metrics.degree_minutes,
            'weather_needs_adjustment': weather_rec['needs_adjustment'],
            'recent_tests': [
                {
                    'parameter': t.parameter_change.parameter.parameter_name,
                    'success': t.success_score > 70,
                    'cop_change': t.cop_change_percent
                }
                for t in recent_tests
            ]
        }

        return context

    def _estimate_cop_for_temp(self, outdoor_temp: float) -> float:
        """Estimate expected COP for outdoor temperature"""
        # Simple empirical model
        if outdoor_temp >= 0:
            return 3.5 - (outdoor_temp * 0.02)
        else:
            return 3.5 - (outdoor_temp * 0.04)

    def _store_proposals(self, proposals: List[TestProposal]):
        """Store proposals in database"""
        session = self.analyzer.session

        # Delete old pending proposals
        session.query(PlannedTest).filter_by(status='pending').delete()

        # Add new proposals
        for prop in proposals:
            param = session.query(Parameter).filter_by(
                parameter_id=prop.parameter_id
            ).first()

            if param:
                planned_test = PlannedTest(
                    parameter_id=param.id,
                    current_value=prop.current_value,
                    proposed_value=prop.proposed_value,
                    hypothesis=prop.hypothesis,
                    expected_improvement=prop.expected_improvement,
                    priority=prop.priority,
                    confidence=prop.confidence,
                    reasoning=prop.reasoning,
                    status='pending',
                    proposed_at=datetime.utcnow()
                )
                session.add(planned_test)

        session.commit()
        logger.info(f"Stored {len(proposals)} proposals in database")


def main():
    """Run test proposer"""
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

    # Create proposer
    api_client = MyUplinkClient()
    analyzer = HeatPumpAnalyzer()
    weather_service = SMHIWeatherService()

    proposer = TestProposer(
        analyzer=analyzer,
        api_client=api_client,
        weather_service=weather_service,
        device_id=device.device_id
    )

    # Propose tests
    proposals = proposer.propose_tests(hours_back=24)

    logger.info("\n" + "="*80)
    logger.info("TEST PROPOSALS")
    logger.info("="*80)
    for i, prop in enumerate(proposals, 1):
        logger.info(f"\n{i}. [{prop.priority.upper()}] {prop.parameter}")
        logger.info(f"   Change: {prop.current_value} → {prop.proposed_value}")
        logger.info(f"   Hypothesis: {prop.hypothesis}")
        logger.info(f"   Expected: {prop.expected_improvement}")
        logger.info(f"   Confidence: {prop.confidence*100:.0f}%")


if __name__ == '__main__':
    main()
