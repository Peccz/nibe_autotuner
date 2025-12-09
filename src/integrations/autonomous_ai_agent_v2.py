"""
Autonomous AI Agent V2 - Optimized & Safe
Uses Google Gemini API with fallback models and strict safety guardrails.
"""
import json
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, GoogleAPIError
from loguru import logger
from services.safety_guard import SafetyGuard
from pydantic import BaseModel, Field, ValidationError, ConfigDict

# Reuse existing classes
from integrations.autonomous_ai_agent import AIDecision, AutonomousAIAgent
from core.config import settings
from data.models import AIDecisionLog, Parameter, ParameterChange, PlannedTest, ABTestResult
from data.evaluation_model import AIEvaluation
from services.price_service import price_service
from services.hw_analyzer import HotWaterPatternAnalyzer
from services.scientific_analyzer import ScientificTestAnalyzer

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

class ModelConfig:
    """Configuration for AI models with fallback support"""

    # Model priority list - tries in order until one succeeds
    # Priority: Fast & cheap models first, then fallback to more capable ones
    # Priority: Next-Gen Reasoning -> Stable Pro -> Balanced -> Infinite Lite
    FALLBACK_MODELS = [
        {
            'provider': 'gemini',
            'model': 'gemini-3.0-pro-preview',
            'name': 'Gemini 3.0 Pro (Next-Gen Reasoning)',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-2.5-pro',
            'name': 'Gemini 2.5 Pro (Senior Consultant)',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-2.5-flash',
            'name': 'Gemini 2.5 Flash (Balanced)',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-2.5-flash-lite',
            'name': 'Gemini 2.5 Flash-Lite (High Availability)',
            'requires_api_key': 'GOOGLE_API_KEY',
        }
    ]

class ParameterConfig:
    """Central configuration for parameter names and their API IDs"""
    # Parameter name mappings (logical name -> API parameter ID)
    PARAMETER_IDS = {
        'heating_curve': '47007',
        'curve_offset': '47011',
        'room_temp': '47015',
        'start_compressor': '47206',
        'hot_water_demand': '47041',
        'increased_ventilation': '50005',
    }

    # Safety bounds for each parameter
    BOUNDS = {
        'heating_curve': (1, 15),           # Nibe curve range
        'curve_offset': (-10, 10),          # Nibe offset range
        'start_compressor': (-1000, -60),   # DM range
        'room_temp': (18, 25),              # Reasonable indoor temp range
        'hot_water_demand': (0, 2),         # 0=Small, 1=Medium, 2=Large
        'increased_ventilation': (0, 4),    # 0=Normal
    }

    # Maximum step size changes to prevent aggressive adjustments
    MAX_STEP_SIZES = {
        'curve_offset': 3,      # Max ±3 steps - allows reaching baseline faster
        'heating_curve': 1,     # Max ±1 step
        'room_temp': 1,         # Max ±1°C
    }

    # Normal operating range for curve_offset (empirically determined)
    NORMAL_OFFSET_RANGE = (-5, 0)  # Typical range, warn if outside

    # Target offset values for different scenarios (outdoor temp 3-5°C)
    OFFSET_BASELINE = -3     # Normal operation (night/cheap electricity)
    OFFSET_REDUCED = -5      # Maximum reduction (expensive electricity)
    OFFSET_BUFFERED = -1     # Buffering heat (before expensive period)

    # Confidence thresholds
    MIN_CONFIDENCE_TO_APPLY = 0.70

# ============================================================================
# PYDANTIC MODELS FOR ROBUST JSON PARSING
# ============================================================================

class AIDecisionModel(BaseModel):
    """Pydantic model for AI decision JSON validation"""
    model_config = ConfigDict(extra="ignore")  # Ignore unknown fields

    action: str = Field(..., pattern="^(adjust|hold|investigate)$")
    parameter: Optional[str] = None
    current_value: Optional[float] = None
    suggested_value: Optional[float] = None
    reasoning: str = Field(default="", min_length=0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_impact: str = Field(default="", min_length=0)

class AutonomousAIAgentV2(AutonomousAIAgent):
    """
    Improved version of AutonomousAIAgent with:
    1. Hardcoded Safety Guardrails (cannot be overridden by LLM)
    2. Optimized Prompts (lower cost)
    3. Explicit Token Tracking
    4. Electricity Price Awareness (Fas 2)
    5. Powered by Google Gemini 2.5 Flash
    6. Smart Hot Water Control (Usage Pattern Analysis)
    """
    
    def __init__(self, analyzer, api_client, weather_service, device_id, anthropic_api_key=None):
        """
        Initialize autonomous AI agent with Gemini and fallback models
        """
        self.analyzer = analyzer
        self.api_client = api_client
        self.weather_service = weather_service
        # Initialize Safety Guard
        from data.database import SessionLocal
        self.db = SessionLocal()
        self.safety_guard = SafetyGuard(self.db)
        self.device_id = device_id

        # Initialize Price Service (defaults to SE3 Stockholm)
        self.price_service = price_service

        # Initialize HW Usage Analyzer
        self.hw_analyzer = HotWaterPatternAnalyzer()

        # Initialize Scientific Test Analyzer
        self.scientific_analyzer = ScientificTestAnalyzer()

        # Configure Gemini with available models
        self.available_models = []

        if settings.GOOGLE_API_KEY:
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            # Initialize all available Gemini models
            for model_config in ModelConfig.FALLBACK_MODELS:
                if model_config['provider'] == 'gemini':
                    try:
                        model = genai.GenerativeModel(model_config['model'])
                        self.available_models.append({
                            'model': model,
                            'config': model_config,
                        })
                        logger.info(f"Initialized fallback model: {model_config['name']}")
                    except Exception as e:
                        logger.warning(f"Failed to initialize {model_config['name']}: {e}")

        if not self.available_models:
            raise ValueError("No AI models available. Please set GOOGLE_API_KEY in environment")

        logger.info(f"Total available models: {len(self.available_models)}")

    def _call_ai_with_fallback(self, prompt: str) -> str:
        """
        Try calling AI models in priority order with automatic fallback.
        Returns the response text from the first successful model.
        """
        last_error = None

        for i, model_entry in enumerate(self.available_models):
            model = model_entry['model']
            config = model_entry['config']

            try:
                logger.info(f"Trying model {i+1}/{len(self.available_models)}: {config['name']}")

                response = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )

                logger.info(f"✓ Success with {config['name']}")
                return response.text

            except ResourceExhausted as e:
                logger.warning(f"✗ {config['name']}: Rate limit exceeded (429)")
                last_error = e
                # Continue to next model

            except GoogleAPIError as e:
                logger.warning(f"✗ {config['name']}: API error - {str(e)}")
                last_error = e
                # Continue to next model

            except Exception as e:
                logger.warning(f"✗ {config['name']}: Unexpected error - {str(e)}")
                last_error = e
                # Continue to next model

        # All models failed
        error_msg = f"All {len(self.available_models)} models failed. Last error: {str(last_error)}"
        logger.error(error_msg)
        raise Exception(error_msg)

    def analyze_and_decide(self, hours_back: int = 72, dry_run: bool = True, mode: str = "tactical") -> AIDecision:
        logger.info("="*80)
        logger.info(f"AUTONOMOUS AI AGENT V2 (GEMINI) - Analysis [Mode: {mode.upper()}]")
        logger.info("="*80)

        # Check if any PlannedTest is currently active and blocking optimization
        blocking_test = self._check_for_blocking_test()
        if blocking_test:
            logger.warning(f"⚠️ PlannedTest {blocking_test.id} is ACTIVE - Skipping optimization to preserve test integrity")
            logger.info(f"   Test: {blocking_test.hypothesis}")
            logger.info(f"   Parameter: {blocking_test.parameter.parameter_name}")
            logger.info(f"   Started: {blocking_test.started_at}")
            return AIDecision(
                action='hold',
                parameter=None,
                current_value=None,
                suggested_value=None,
                reasoning=f"Holding: PlannedTest {blocking_test.id} ({blocking_test.parameter.parameter_name}) is active. AI optimization paused to preserve test integrity.",
                confidence=1.0,
                expected_impact="No changes until test completes"
            )

        # Train HW analyzer (lightweight, uses cached data if available)
        try:
            self.hw_analyzer.train_on_history(days_back=14)
        except Exception as e:
            logger.warning(f"HW Analyzer training failed: {e}")

        # 1. Get device settings from database
        from data.database import SessionLocal
        from data.models import Device

        session = SessionLocal()
        try:
            device = session.query(Device).filter(Device.device_id == self.device_id).first()
            if device:
                # Apply Comfort Offset
                offset = getattr(device, 'comfort_adjustment_offset', 0.0)
                
                min_temp = device.min_indoor_temp_user_setting + offset
                target_min = device.target_indoor_temp_min + offset
                target_max = device.target_indoor_temp_max + offset
            else:
                # Fallback values if device not found
                min_temp, target_min, target_max = 20.5, 20.5, 22.0
                logger.warning(f"Device {self.device_id} not found, using fallback temps: {min_temp}-{target_max}°C")
        finally:
            session.close()

        # 2. Build Optimized Context
        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)
        # --- FIX: USE LATEST TEMP FOR AI CONTEXT ---
        # Hämta senaste värdet istället för snittet, så AI agerar på nutid
        real_time_indoor = self.analyzer.get_latest_value(self.analyzer.get_device(), self.analyzer.PARAM_INDOOR_TEMP)
        if real_time_indoor is not None:
            logger.info(f"Overriding avg indoor ({metrics.avg_indoor_temp}) with latest ({real_time_indoor}) for AI context")
            metrics.avg_indoor_temp = real_time_indoor
        # ---------------------------------------------
        context = self._build_optimized_context(metrics)

        # 3. Create Optimized Prompt with user settings and MODE restriction
        # Skicka metrics direkt för att slippa regex-parsing
        prompt = self._create_optimized_prompt(context, min_temp, target_min, target_max, mode, metrics)

        # 3. Call AI with automatic fallback
        try:
            logger.info("Calling AI with fallback support...")

            # Try models in priority order until one succeeds
            response_text = self._call_ai_with_fallback(prompt)
            decision_model = self._parse_json_response_robust(response_text)

            decision = AIDecision(
                action=decision_model.action,
                parameter=decision_model.parameter,
                current_value=decision_model.current_value,
                suggested_value=decision_model.suggested_value,
                reasoning=decision_model.reasoning,
                confidence=decision_model.confidence,
                expected_impact=decision_model.expected_impact
            )

            # 4. SAFETY CHECK
            is_safe, safety_reason = self._is_decision_safe(decision)
            
            if not is_safe:
                logger.warning(f"⚠️ SAFETY GUARDRAIL TRIGGERED: {safety_reason}")
                
                decision.action = 'hold'
                decision.reasoning = f"[BLOCKED BY SAFETY] {decision.reasoning}. Reason: {safety_reason}"
                decision.suggested_value = None

            # 5. Log & Apply
            self._log_decision(decision, dry_run=dry_run)

            if not dry_run and decision.action == 'adjust' and decision.confidence >= ParameterConfig.MIN_CONFIDENCE_TO_APPLY:
                self._apply_decision(decision)

            return decision

        except Exception as e:
            logger.error(f"Error in AI Agent V2: {e}")
            import traceback
            traceback.print_exc()
            return AIDecision('hold', None, None, None, f"Error: {str(e)}", 0.0, "None")

    def _get_current_parameter_value(self, parameter_name: str) -> Optional[float]:
        """
        Get current value of a parameter from database.
        Used when AI decision has null current_value.

        Args:
            parameter_name: Logical parameter name (e.g., 'curve_offset')

        Returns:
            Current value or None if not found
        """
        if parameter_name not in ParameterConfig.PARAMETER_IDS:
            return None

        param_id = ParameterConfig.PARAMETER_IDS[parameter_name]
        param = self.analyzer.get_parameter(param_id)

        if not param:
            return None

        device = self.analyzer.get_device()
        return self.analyzer.get_latest_value(device, param_id)

    def _predict_indoor_temp_after_offset_change(
        self,
        current_offset: float,
        new_offset: float,
        current_indoor_temp: float
    ) -> float:
        """
        Predict indoor temperature after offset change.

        Empirical model: Each offset step ≈ 0.5°C change

        Args:
            current_offset: Current curve offset
            new_offset: Proposed new offset
            current_indoor_temp: Current indoor temperature

        Returns:
            Predicted indoor temperature
        """
        offset_change = new_offset - current_offset
        temp_change = offset_change * 0.5  # Each step ≈ 0.5°C
        predicted_temp = current_indoor_temp + temp_change

        logger.info(f"Temperature prediction: {current_indoor_temp:.1f}°C + ({offset_change:.1f} steps × 0.5°C) = {predicted_temp:.1f}°C")

        return predicted_temp

    def _is_decision_safe(self, decision: AIDecision) -> Tuple[bool, str]:
        """
        Deterministic safety checks that override the AI.
        Uses centralized ParameterConfig for all bounds and limits.
        Reads MIN_INDOOR_TEMP from database (device-specific user setting).

        Enhanced with:
        - Null value handling: fetches current value from DB if missing
        - Predictive temperature check: forecasts indoor temp after offset changes
        """
        if decision.action != 'adjust':
            return True, ""

        if decision.suggested_value is None or decision.parameter is None:
            return False, "Missing required fields: parameter or suggested_value"

        # Get user settings from database
        from data.database import SessionLocal
        from data.models import Device

        session = SessionLocal()
        try:
            device = session.query(Device).filter(Device.device_id == self.device_id).first()
            if device:
                comfort_offset = getattr(device, 'comfort_adjustment_offset', 0.0)
                min_temp = device.min_indoor_temp_user_setting + comfort_offset
            else:
                min_temp = 20.5
                logger.warning(f"Device {self.device_id} not found in DB, using fallback min_temp={min_temp}°C")
        finally:
            session.close()

        # Rule 1: Minimum Indoor Temperature (Safety over Cost)
        if decision.parameter == 'room_temp':
            if decision.suggested_value < min_temp:
                return False, f"Suggested room temp {decision.suggested_value}°C is below safety limit ({min_temp}°C)"

        # Rule 2: Parameter Bounds
        if decision.parameter in ParameterConfig.BOUNDS:
            min_val, max_val = ParameterConfig.BOUNDS[decision.parameter]
            if not (min_val <= decision.suggested_value <= max_val):
                return False, f"Value {decision.suggested_value} for {decision.parameter} is out of bounds ({min_val}-{max_val})"

        # Rule 3: Step Size Limits (Prevent drastic changes)
        # Enhanced: Fetch current value from DB if null
        current_value = decision.current_value
        if current_value is None and decision.parameter in ParameterConfig.MAX_STEP_SIZES:
            current_value = self._get_current_parameter_value(decision.parameter)
            logger.info(f"Fetched current value from DB: {decision.parameter} = {current_value}")

        if decision.parameter in ParameterConfig.MAX_STEP_SIZES and current_value is not None:
            max_step = ParameterConfig.MAX_STEP_SIZES[decision.parameter]
            diff = abs(decision.suggested_value - current_value)
            if diff > max_step:
                return False, f"Change of {diff:.1f} steps for {decision.parameter} exceeds max ({max_step})"

        # Rule 4: Predictive Temperature Check for Offset Changes
        # Ensures offset changes won't drop indoor temp below minimum
        if decision.parameter == 'curve_offset':
            # Get current indoor temperature
            device = self.analyzer.get_device()
            current_indoor = self.analyzer.get_latest_value(device, self.analyzer.PARAM_INDOOR_TEMP)

            if current_indoor is not None and current_value is not None:
                predicted_indoor = self._predict_indoor_temp_after_offset_change(
                    current_value,
                    decision.suggested_value,
                    current_indoor
                )

                # Safety margin: require 0.3°C buffer above minimum
                safety_margin = 0.3
                if predicted_indoor < (min_temp + safety_margin):
                    return False, (
                        f"PREDICTIVE SAFETY BLOCK: Offset change would drop indoor temp to "
                        f"{predicted_indoor:.1f}°C (below {min_temp + safety_margin:.1f}°C safe minimum). "
                        f"Current: {current_indoor:.1f}°C, Offset: {current_value:.1f} → {decision.suggested_value:.1f}"
                    )

                logger.info(f"✓ Predictive check passed: {predicted_indoor:.1f}°C > {min_temp + safety_margin:.1f}°C")

        # Rule 5: Curve Offset Empirical Limits (outdoor temp 3-5°C)
        if decision.parameter == 'curve_offset':
            if decision.suggested_value < ParameterConfig.OFFSET_REDUCED:
                return False, f"Offset {decision.suggested_value} is below empirical minimum ({ParameterConfig.OFFSET_REDUCED}) for current outdoor temps. No additional savings, risks discomfort."

        return True, ""

    def _check_for_blocking_test(self) -> Optional[PlannedTest]:
        """
        Check if any PlannedTest is currently active and would conflict with optimization.

        Tests that block optimization:
        - curve_offset tests (conflicts with AI offset adjustments)
        - heating_curve tests (conflicts with AI curve adjustments)
        - start_compressor tests (conflicts with AI compressor logic)

        Tests that DON'T block:
        - hot_water_demand (different parameter, no conflict)
        - increased_ventilation (different parameter, no conflict)

        Returns:
            PlannedTest if blocking test is active, None otherwise
        """
        # Parameters that conflict with AI optimization
        BLOCKING_PARAMETER_IDS = ['47007', '47011', '47206']  # heating_curve, curve_offset, start_compressor

        # Check for active tests
        active_tests = self.analyzer.session.query(PlannedTest).filter(
            PlannedTest.status == 'active'
        ).all()

        for test in active_tests:
            if test.parameter and test.parameter.parameter_id in BLOCKING_PARAMETER_IDS:
                logger.info(f"Found blocking PlannedTest {test.id}: {test.parameter.parameter_name} (status={test.status})")
                return test

        return None

    def _get_recent_learning_history(self, hours_back: int = 24) -> str:
        """
        Fetch recent parameter changes and their outcomes for AI learning.
        Returns a compact summary of what worked and what didn't.
        """
        try:
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)

            # Get recent parameter changes
            recent_changes = self.analyzer.session.query(ParameterChange).filter(
                ParameterChange.timestamp >= cutoff_time
            ).order_by(ParameterChange.timestamp.desc()).limit(10).all()

            if not recent_changes:
                return "HISTORY: No recent changes"

            # Build compact history summary
            history_lines = []
            for change in recent_changes:
                # Get parameter name
                param = self.analyzer.session.query(Parameter).filter_by(
                    id=change.parameter_id
                ).first()

                if not param:
                    continue

                # Find parameter logical name
                param_name = None
                for name, pid in ParameterConfig.PARAMETER_IDS.items():
                    if pid == param.parameter_id:
                        param_name = name
                        break

                if not param_name:
                    continue

                # Calculate time since change
                hours_ago = (datetime.utcnow() - change.timestamp).total_seconds() / 3600

                # Try to get COP before/after (simplified - just check nearby metrics)
                try:
                    # Get metrics 6h before and 6h after change
                    before_metrics = self.analyzer.calculate_metrics(
                        hours_back=6,
                        end_time=change.timestamp
                    )
                    after_start = change.timestamp + timedelta(hours=1)
                    after_end = change.timestamp + timedelta(hours=7)

                    # Only calculate if enough time has passed
                    if datetime.utcnow() > after_end:
                        after_metrics = self.analyzer.calculate_metrics(
                            hours_back=6,
                            end_time=after_end
                        )
                        cop_change = after_metrics.estimated_cop - before_metrics.estimated_cop
                        result = f"COP:{cop_change:+.2f}"
                    else:
                        result = "pending"
                except:
                    result = "N/A"

                history_lines.append(
                    f"{int(hours_ago)}h ago: {param_name} {change.old_value}→{change.new_value} ({result})"
                )

            if history_lines:
                return "HISTORY(last 24h):\n" + "\n".join(history_lines[:5])  # Top 5 most recent
            else:
                return "HISTORY: No evaluable changes"

        except Exception as e:
            logger.warning(f"Could not fetch learning history: {e}")
            return "HISTORY: Error fetching"

    def _get_combined_forecast(self) -> str:
        """
        Get combined price + weather forecast for predictive control.
        Price: fallback hourly pattern (cheap at night, expensive during day)
        Weather: SMHI temperature forecast
        """
        try:
            from datetime import datetime

            now = datetime.now()
            current_hour = now.hour

            # === PRICE FORECAST ===
            # Simple hourly pattern based on typical Swedish electricity prices
            # Cheap: 22-06, Expensive: 07-09, 17-21, Normal: rest
            expensive_hours = []
            cheap_hours = []

            for h in range(current_hour, current_hour + 12):
                hour = h % 24
                if hour in [7, 8, 9, 17, 18, 19, 20, 21]:
                    expensive_hours.append(hour)
                elif hour in [22, 23, 0, 1, 2, 3, 4, 5, 6]:
                    cheap_hours.append(hour)

            price_str = "Price:"
            if expensive_hours:
                price_str += f" EXPENSIVE at {','.join(map(str, expensive_hours[:4]))}h"
            if cheap_hours:
                price_str += f" CHEAP at {','.join(map(str, cheap_hours[:4]))}h"

            # === WEATHER FORECAST ===
            weather_str = "Weather:"
            try:
                # Get 12h temperature forecast
                temp_forecast = self.weather_service.get_temperature_forecast(hours_ahead=12)

                if temp_forecast:
                    temps = [t for _, t in temp_forecast]
                    avg_temp = sum(temps) / len(temps)
                    min_temp = min(temps)
                    max_temp = max(temps)

                    # Determine trend
                    current_temp = temps[0] if temps else None
                    end_temp = temps[-1] if len(temps) > 1 else None

                    if current_temp and end_temp:
                        if end_temp < current_temp - 2:
                            trend = "COOLING"
                        elif end_temp > current_temp + 2:
                            trend = "WARMING"
                        else:
                            trend = "STABLE"
                    else:
                        trend = "UNKNOWN"

                    weather_str += f" {min_temp:.1f}-{max_temp:.1f}°C (avg:{avg_temp:.1f}°C) {trend}"
                else:
                    weather_str += " No data"
            except Exception as e:
                logger.warning(f"Could not get weather forecast: {e}")
                weather_str += " Error"

            return f"FORECAST(next 12h): {price_str} | {weather_str}"

        except Exception as e:
            logger.warning(f"Could not get combined forecast: {e}")
            return "FORECAST: Error"

    def _get_verified_facts(self) -> str:
        """Fetch insights from successful scientific tests"""
        try:
            # Get successful tests that led to a recommendation or conclusion
            completed_tests = self.analyzer.session.query(ABTestResult).order_by(
                ABTestResult.created_at.desc()
            ).limit(5).all()
            
            if not completed_tests:
                return "FACTS: No scientific tests completed yet."
                
            facts = []
            for test in completed_tests:
                if test.recommendation and "Keep" in test.recommendation:
                     # Get parameter name via change relation
                     change = self.analyzer.session.query(ParameterChange).filter_by(id=test.parameter_change_id).first()
                     if change:
                         param = self.analyzer.session.query(Parameter).filter_by(id=change.parameter_id).first()
                         facts.append(f"Confirmed: {param.parameter_name} change was beneficial ({test.recommendation})")
            
            return "FACTS:\n" + "\n".join(facts) if facts else "FACTS: No conclusive tests yet."
        except Exception as e:
            logger.warning(f"Could not fetch verified facts: {e}")
            return "FACTS: Unavailable"

    def _get_performance_summary(self) -> str:
        """Fetch summary of recent AI performance evaluations"""
        try:
            from sqlalchemy import func
            
            # Get evaluations from last 7 days
            week_ago = datetime.utcnow() - timedelta(days=7)
            
            stats = self.analyzer.session.query(
                AIEvaluation.verdict, func.count(AIEvaluation.id)
            ).filter(
                AIEvaluation.created_at >= week_ago
            ).group_by(AIEvaluation.verdict).all()
            
            if not stats:
                return "AI_PERFORMANCE: No data yet"
                
            summary = []
            total = 0
            for verdict, count in stats:
                summary.append(f"{verdict}: {count}")
                total += count
                
            return f"AI_PERFORMANCE(7d): {', '.join(summary)} (Total: {total})"
        except Exception as e:
            logger.warning(f"Could not fetch performance summary: {e}")
            return "AI_PERFORMANCE: Unavailable"

    def _build_optimized_context(self, metrics) -> str:
        """Compact context to save tokens"""

        # Fetch Price Data
        try:
            p_info = self.price_service.get_price_analysis()
            price_str = f"Price: {p_info.get('current_price',0):.2f} SEK/kWh. Status: {p_info.get('price_level', 'UNKNOWN')}."
        except Exception as e:
            logger.warning(f"Failed to get prices: {e}")
            price_str = "Price: N/A"

        # Fetch Combined Price + Weather Forecast
        forecast_str = self._get_combined_forecast()

        # Fetch HW Probability
        try:
            hw_prob = self.hw_analyzer.get_usage_probability(datetime.now())
            hw_str = f"HW_Usage_Risk: {'HIGH' if hw_prob > 0.5 else 'LOW'} ({hw_prob:.1f})"
        except Exception as e:
            hw_str = "HW_Usage_Risk: UNKNOWN"

        # Fetch learning history
        history_str = self._get_recent_learning_history(hours_back=24)
        
        # Fetch Consolidated Insights (NEW)
        facts_str = self._get_verified_facts()
        perf_str = self._get_performance_summary()

        # Format Time to Start
        tts_str = "TimeToStart: N/A"
        if metrics.estimated_time_to_start_minutes is not None:
             hours = int(metrics.estimated_time_to_start_minutes / 60)
             mins = int(metrics.estimated_time_to_start_minutes % 60)
             tts_str = f"TimeToStart: {hours}h {mins}m"
        elif metrics.degree_minutes is not None and metrics.degree_minutes < -60:
             # Fallback if calculation failed but we are active
             tts_str = "TimeToStart: Calculating..."

        return f"""DT:{datetime.now().strftime('%Y-%m-%d %H:%M')}
METRICS(72h):
Outdoor:{metrics.avg_outdoor_temp:.1f}C
Indoor:{metrics.avg_indoor_temp:.1f}C
COP:{metrics.estimated_cop:.2f}
DegMin:{metrics.degree_minutes:.0f}
{tts_str}
Curve:{metrics.heating_curve}/Offset:{metrics.curve_offset}
{price_str}
{forecast_str}
{hw_str}

{facts_str}
{perf_str}
{history_str}
"""

    def _create_optimized_prompt(self, context: str, min_temp: float, target_min: float, target_max: float, mode: str = "tactical", metrics=None) -> str:
        
        # Hämta säkra värden från metrics om det finns, annars fallback
        indoor_temp = 20.0
        outdoor_temp = 0.0
        current_offset = -3.0
        
        if metrics:
            if metrics.avg_indoor_temp is not None: indoor_temp = metrics.avg_indoor_temp
            if metrics.avg_outdoor_temp is not None: outdoor_temp = metrics.avg_outdoor_temp
            if metrics.curve_offset is not None: current_offset = metrics.curve_offset

        # Hämta pris från context-texten
        import re
        price_match = re.search(r"Price: ([\d\.]+)", context)
        current_price = price_match.group(1) if price_match else "Unknown"

        # Define allowed parameters based on mode
        if mode == "strategic":
            allowed_params = "heating_curve(1-15), curve_offset(-10-10), start_compressor(-DM), hot_water_demand(0-2), increased_ventilation(0-4)"
            mode_instruction = "MODE: STRATEGIC. You may adjust base Heating Curve (slope)."
        else:
            allowed_params = "curve_offset(-10-10), hot_water_demand(0-2), increased_ventilation(0-4)"
            mode_instruction = "MODE: TACTICAL. Focus on curve_offset and hot_water only."

        prompt = f"""
You are an expert autonomous control agent for a Nibe F730 Heat Pump.
Your goal is to optimize indoor comfort and electricity cost.

SYSTEM CONTEXT:
- **BASELINE CURVE OFFSET: -3** (This is the 'Normal' setting).
- Higher values (e.g. -2, -1, 0) = MORE HEAT (Buffering/Comfort).
- Lower values (e.g. -4, -5) = LESS HEAT (Saving/Coasting).
- Current Curve Offset: {current_offset}

SENSORS:
- Indoor Temp: {indoor_temp:.1f}°C (Target: {target_min}-{target_max}°C)
- Outdoor Temp: {outdoor_temp:.1f}°C
- Electricity Price: {current_price}

STRATEGY LOGIC (Evaluate in order):

1. COMFORT PROTECTION (The Law):
   - IF Indoor > {target_max}: REDUCE heating (Target -4 or -5).
   - IF Indoor < {min_temp}: INCREASE heating (Target -1 or 0).

2. PRICE TREND STRATEGY (If comfort is OK):
   - **Scenario A: Price is DROPPING soon** (Cheap later):
     ACTION: COASTING. Reduce heating NOW to save expensive energy. Wait for the cheap price.
     Target: -4 or -5.
   
   - **Scenario B: Price is RISING soon** (Expensive later):
     ACTION: PRE-HEATING. Increase heating NOW (using current cheaper price) to buffer heat.
     Target: -1 or 0 (Only if Indoor < 22).

   - **Scenario C: Stable Price**:
     - If Expensive: Target -4 or -5.
     - If Cheap: Target -3 (Baseline) or -2 (Slight buffer).

3. STABILITY (Override):
   - IF Indoor is PERFECT ({target_min} - {target_max}) AND Price is Unknown/Stable:
     ACTION: HOLD or gentle move to Baseline (-3). Do NOT make drastic changes if comfort is good.

4. EXECUTION:
   - Determine target based on above.
   - Max change: +/- 3 steps allowed (if needed).
   - Explain reasoning clearly.

Output JSON only. Use 'suggested_value' for the new target.
Action: adjust|hold|investigate
Params: {allowed_params}
Rules: Indoor target {target_min:.1f}-{target_max:.1f}C (MINIMUM {min_temp:.1f}°C). Max 1 change. Min conf 0.7.
{mode_instruction}

Example:
{{"action":"adjust","parameter":"curve_offset","suggested_value":-4.0,"reasoning":"Price dropping soon, coasting to save energy.","confidence":0.9}}
"""
        return prompt

    def _parse_json_response_robust(self, text: str) -> AIDecisionModel:
        """
        Robust JSON parsing with Pydantic validation.
        Handles multiple JSON formats and provides clear error messages.
        """
        clean_text = text.strip()

        # Try to extract JSON from markdown code blocks
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0]
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].split("```")[0]

        # Remove any leading/trailing whitespace
        clean_text = clean_text.strip()

        try:
            # Parse JSON
            data = json.loads(clean_text)

            # Handle case where Gemini returns a list instead of a dict
            if isinstance(data, list):
                if len(data) > 0 and isinstance(data[0], dict):
                    logger.warning("Gemini returned a list, using first element")
                    data = data[0]
                else:
                    raise ValueError("Gemini returned a list but no valid dict found")

            # Validate with Pydantic
            decision_model = AIDecisionModel(**data)
            return decision_model

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            logger.error(f"Raw response: {text[:500]}")

            # Try to find JSON object with regex as fallback
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', clean_text)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    decision_model = AIDecisionModel(**data)
                    logger.warning("Used regex fallback to extract JSON")
                    return decision_model
                except Exception as fallback_error:
                    logger.error(f"Regex fallback also failed: {fallback_error}")

            raise ValueError(f"Failed to parse AI response as JSON: {e}")

        except ValidationError as e:
            logger.error(f"Pydantic validation failed: {e}")
            logger.error(f"Data received: {data}")
            raise ValueError(f"AI response failed validation: {e}")

    def evaluate_scientific_test_results(self, test: PlannedTest, start_time: datetime, end_time: datetime) -> Dict:
        """
        Evaluate scientific test results using specialized analysis methods.

        This method determines which analysis to run based on the test's hypothesis
        or parameter, then uses the scientific_analyzer to get detailed metrics.

        Args:
            test: The PlannedTest object that was completed
            start_time: When the test started
            end_time: When the test ended

        Returns:
            Dictionary with evaluation results and analysis data
        """
        logger.info("="*80)
        logger.info(f"EVALUATING SCIENTIFIC TEST: {test.hypothesis}")
        logger.info(f"Period: {start_time} to {end_time}")
        logger.info("="*80)

        # Get parameter info
        param = self.analyzer.session.query(Parameter).filter_by(id=test.parameter_id).first()
        if not param:
            logger.error(f"Parameter ID {test.parameter_id} not found")
            return {'success': False, 'error': 'Parameter not found'}

        param_id = param.parameter_id
        duration_hours = (end_time - start_time).total_seconds() / 3600

        evaluation = {
            'test_id': test.id,
            'parameter_id': param_id,
            'parameter_name': param.parameter_name,
            'hypothesis': test.hypothesis,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_hours': round(duration_hours, 2),
            'analysis': {},
            'conclusion': '',
            'success': True
        }

        # Determine which analysis to run based on parameter and hypothesis
        logger.info(f"Analyzing test for parameter {param_id} ({param.parameter_name})")

        # Test 1: Curve Offset (-10) - Measure cooling rate
        if param_id == '47011' and 'tidskonstant' in test.hypothesis.lower():
            logger.info("Running cooling rate analysis (thermal time constant test)")
            cooling_analysis = self.scientific_analyzer.analyze_cooling_rate(start_time, end_time)
            evaluation['analysis']['cooling_rate'] = cooling_analysis

            if cooling_analysis['success']:
                rate = cooling_analysis['cooling_rate_c_per_hour']
                r2 = cooling_analysis['r_squared']

                # Interpret results
                if abs(rate) < 0.1:
                    conclusion = f"House has excellent thermal stability. Cooling rate: {rate:.3f}°C/h (R²={r2:.2f}). Very well insulated."
                elif rate < 0:  # Cooling
                    conclusion = f"House cooling at {abs(rate):.3f}°C/h (R²={r2:.2f}). Thermal time constant suggests good insulation."
                else:  # Heating
                    conclusion = f"House warming at {rate:.3f}°C/h (R²={r2:.2f}). Heat pump compensating for low offset setting."

                evaluation['conclusion'] = conclusion
                logger.info(f"Conclusion: {conclusion}")
            else:
                evaluation['conclusion'] = f"Analysis failed: {cooling_analysis.get('error', 'Unknown error')}"
                evaluation['success'] = False

        # Test 2: Start Compressor (-160) - Minimize starts
        elif param_id == '47206' and 'kompressor' in test.hypothesis.lower():
            logger.info("Running compressor starts analysis")
            starts_analysis = self.scientific_analyzer.count_compressor_starts(start_time, end_time)
            evaluation['analysis']['compressor_starts'] = starts_analysis

            if starts_analysis['success']:
                count = starts_analysis['start_count']
                avg_runtime = starts_analysis['avg_runtime_minutes']

                # Interpret results
                starts_per_day = count / (duration_hours / 24)
                if count < 5 and duration_hours >= 24:
                    conclusion = f"Excellent: Only {count} starts in {duration_hours:.1f}h ({starts_per_day:.1f}/day). Avg runtime: {avg_runtime:.1f} min. Long cycles = high COP."
                elif count < 10 and duration_hours >= 24:
                    conclusion = f"Good: {count} starts in {duration_hours:.1f}h ({starts_per_day:.1f}/day). Avg runtime: {avg_runtime:.1f} min. Acceptable cycle length."
                else:
                    conclusion = f"Many starts: {count} in {duration_hours:.1f}h ({starts_per_day:.1f}/day). Avg runtime: {avg_runtime:.1f} min. Consider raising threshold further."

                evaluation['conclusion'] = conclusion
                logger.info(f"Conclusion: {conclusion}")
            else:
                evaluation['conclusion'] = f"Analysis failed: {starts_analysis.get('error', 'Unknown error')}"
                evaluation['success'] = False

        # Test 3: Hot Water Demand (2=Large) - Test max temp without immersion heater
        elif param_id == '47041' and 'varmvatten' in test.hypothesis.lower():
            logger.info("Running hot water temperature analysis")

            # Check immersion heater usage (with known issues)
            logger.warning("⚠️ Immersion heater parameter (43427/49993/43084) may give incorrect values")
            heater_analysis = self.scientific_analyzer.check_immersion_heater_usage(start_time, end_time)

            # For now, we'll use hot water temperature as the main metric
            # Get max hot water temperature achieved
            try:
                conn = self.analyzer.session.connection()
                from sqlalchemy import text

                # Get hot water top temperature (40013)
                query = text("""
                    SELECT MAX(pr.value) as max_temp
                    FROM parameter_readings pr
                    JOIN parameters p ON pr.parameter_id = p.id
                    WHERE p.parameter_id = '40013'
                        AND pr.timestamp >= :start_time
                        AND pr.timestamp <= :end_time
                """)

                result = conn.execute(query, {'start_time': start_time, 'end_time': end_time})
                row = result.fetchone()
                max_hw_temp = row[0] if row and row[0] else None

                evaluation['analysis']['hot_water'] = {
                    'max_temperature': max_hw_temp,
                    'immersion_heater_analysis': heater_analysis,
                    'note': 'Immersion heater data may be unreliable - using temperature as primary metric'
                }

                if max_hw_temp:
                    # Assume immersion heater NOT used if temp stays below 55-58°C
                    # (heat pump alone typically maxes around 55°C)
                    if max_hw_temp < 55:
                        conclusion = f"Heat pump alone achieved {max_hw_temp:.1f}°C. No immersion heater needed (temp < 55°C threshold)."
                    elif max_hw_temp < 58:
                        conclusion = f"Heat pump achieved {max_hw_temp:.1f}°C. Likely no immersion heater (temp < 58°C). Close to limit."
                    else:
                        conclusion = f"Max temp {max_hw_temp:.1f}°C achieved. Possible immersion heater use (temp ≥ 58°C) - verify manually."

                    evaluation['conclusion'] = conclusion
                    logger.info(f"Conclusion: {conclusion}")
                else:
                    evaluation['conclusion'] = "No hot water temperature data available"
                    evaluation['success'] = False

            except Exception as e:
                logger.error(f"Failed to query hot water temperature: {e}")
                evaluation['conclusion'] = f"Error querying hot water temp: {e}"
                evaluation['success'] = False

        else:
            # Generic analysis - run all available metrics
            logger.info("Running generic multi-metric analysis")
            summary = self.scientific_analyzer.get_test_summary(start_time, end_time)
            evaluation['analysis'] = summary
            evaluation['conclusion'] = f"Generic analysis completed for {param.parameter_name}. Review detailed metrics."

        logger.info("="*80)
        logger.info(f"EVALUATION COMPLETE: {evaluation['conclusion'][:80]}...")
        logger.info("="*80)

        return evaluation
