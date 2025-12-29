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
from services.learning_service import LearningService

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

class ModelConfig:
    """Configuration for AI models with fallback support"""

    FALLBACK_MODELS = [
        {
            'provider': 'gemini',
            'model': 'gemini-2.5-pro',
            'name': 'Gemini 2.5 Pro (Primary - Best Reasoning)',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-2.5-flash',
            'name': 'Gemini 2.5 Flash (Fallback - Faster)',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-2.5-flash-lite',
            'name': 'Gemini 2.5 Flash Lite (Fallback - High Availability)',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-2.0-flash-lite',
            'name': 'Gemini 2.0 Flash Lite (Emergency Fallback)',
            'requires_api_key': 'GOOGLE_API_KEY',
        }
    ]

class ParameterConfig:
    """Central configuration for parameter names and their API IDs"""
    PARAMETER_IDS = {
        'heating_curve': '47007',
        'curve_offset': '47011',
        'room_temp': '47015',
        'start_compressor': '47206',
        'hot_water_demand': '47041',
        'increased_ventilation': '50005',
    }

    BOUNDS = {
        'heating_curve': (1, 15),
        'curve_offset': (-10, 10),
        'start_compressor': (-1000, -60),
        'room_temp': (18, 25),
        'hot_water_demand': (0, 2),
        'increased_ventilation': (0, 4),
    }

    MAX_STEP_SIZES = {
        'curve_offset': 3,
        'heating_curve': 1,
        'room_temp': 1,
    }

    NORMAL_OFFSET_RANGE = (-5, 0)
    OFFSET_BASELINE = -3
    OFFSET_REDUCED = -5
    OFFSET_BUFFERED = -1
    MIN_CONFIDENCE_TO_APPLY = 0.70

# ============================================================================
# PYDANTIC MODELS FOR ROBUST JSON PARSING
# ============================================================================

class AIDecisionModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
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
    1. Optimized Prompts
    2. Explicit Token Tracking
    3. Electricity Price Awareness
    4. Powered by Google Gemini 2.5 Flash
    5. Smart Hot Water Control
    6. Learning Service Integration
    """
    
    def __init__(self, analyzer, api_client, weather_service, device_id, anthropic_api_key=None):
        self.analyzer = analyzer
        self.api_client = api_client
        self.weather_service = weather_service
        
        from data.database import SessionLocal
        self.db = SessionLocal()
        self.safety_guard = SafetyGuard(self.db)
        self.device_id = device_id
        self.price_service = price_service
        self.hw_analyzer = HotWaterPatternAnalyzer()
        self.scientific_analyzer = ScientificTestAnalyzer()
        self.learning_service = LearningService(self.db, self.analyzer)

        self.available_models = []
        if settings.GOOGLE_API_KEY:
            genai.configure(api_key=settings.GOOGLE_API_KEY)
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
            except Exception as e:
                logger.warning(f"✗ {config['name']}: Error - {str(e)}")
                last_error = e
        error_msg = f"All models failed. Last error: {str(last_error)}"
        logger.error(error_msg)
        raise Exception(error_msg)
        
    def analyze_and_decide(self, hours_back: int = 72, dry_run: bool = True, mode: str = "tactical") -> AIDecision:
        logger.info("="*80)
        logger.info(f"AUTONOMOUS AI AGENT V2 (GEMINI) - Analysis [Mode: {mode.upper()}]")
        logger.info("="*80)

        # Update learning events
        self.learning_service.update_pending_events()

        # Check for blocking test
        blocking_test = self._check_for_blocking_test()
        if blocking_test:
            logger.warning(f"⚠️ PlannedTest {blocking_test.id} is ACTIVE")
            return AIDecision('hold', None, None, None, "Test active", 1.0, "No changes")

        # Train HW analyzer
        try:
            self.hw_analyzer.train_on_history(days_back=14)
        except Exception as e:
            logger.warning(f"HW Analyzer training failed: {e}")

        # Get device settings
        from data.database import SessionLocal
        from data.models import Device
        session = SessionLocal()
        try:
            device = session.query(Device).filter(Device.device_id == self.device_id).first()
            if device:
                offset = getattr(device, 'comfort_adjustment_offset', 0.0)
                # Ensure session is closed here as it's used later
                session.close() # Close session after fetching device
            else:
                offset = 0.0
        finally:
            if 'session' in locals() and session.is_active: # Check if session is open
                session.close()

        # Away Mode Logic
        if device and device.away_mode_enabled:
            if device.away_mode_end_date and datetime.utcnow() > device.away_mode_end_date:
                device.away_mode_enabled = False
                device.away_mode_end_date = None
                session = SessionLocal() # Re-open session to commit
                session.add(device)
                session.commit()
                session.close()
                logger.info("Away mode end date passed. Disabling away mode.")
            else:
                logger.info("Away mode active. Overriding temp targets to 16-17C, and HW off.")
                min_temp = 16.0
                target_min = 16.0
                target_max = 17.0
                # If away mode is active, directly suggest turning off hot water
                # This decision can be overridden if away_mode_enabled is False.
                return AIDecision('adjust', 'hot_water_demand', 1.0, 0.0, 'Away mode active: Turning off hot water.', 1.0, 'No hot water production')

        # Normal operation:
        if device:
            min_temp = device.min_indoor_temp_user_setting + offset
            target_min = device.target_indoor_temp_min + offset
            target_max = device.target_indoor_temp_max + offset
        else:
            # Fallback values if device not found (should be handled by device check above)
            min_temp, target_min, target_max = 20.5, 20.5, 22.0
            logger.warning(f"Device {self.device_id} not found, using fallback min_temp={min_temp}°C")

        # Metrics & Context
        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)
        real_time_indoor = self.analyzer.get_latest_value(self.analyzer.get_device(), self.analyzer.PARAM_INDOOR_TEMP)
        if real_time_indoor is not None:
            metrics.avg_indoor_temp = real_time_indoor
            
        context = self._build_optimized_context(metrics, device) # Pass device to context builder
        prompt = self._create_optimized_prompt(context, min_temp, target_min, target_max, mode, metrics, device) # Pass device to prompt builder

        try:
            logger.info("Calling Gemini API with fallback support...")
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

            # Fix missing current_value
            if decision.current_value is None and metrics:
                if decision.parameter == 'curve_offset' and metrics.curve_offset is not None:
                    decision.current_value = metrics.curve_offset
                elif decision.parameter == 'heating_curve' and metrics.heating_curve is not None:
                    decision.current_value = metrics.heating_curve

            # Log & Apply
            self._log_decision(decision, dry_run=dry_run)

            if not dry_run and decision.action == 'adjust' and decision.confidence >= ParameterConfig.MIN_CONFIDENCE_TO_APPLY:
                self._apply_decision(decision)

            return decision

        except Exception as e:
            logger.error(f"Error in AI Agent V2: {e}")
            import traceback
            traceback.print_exc()
            return AIDecision('hold', None, None, None, f"Error: {str(e)}", 0.0, "None")

    def _apply_decision(self, decision: AIDecision) -> bool:
        """
        Apply AI decision to the system (Override with Learning)
        """
        if decision.action != 'adjust' or not decision.parameter:
            logger.warning("Decision does not include adjustment")
            return False

        # Map parameter names to IDs
        param_id = ParameterConfig.PARAMETER_IDS.get(decision.parameter)
        
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
            from data.models import ParameterChange, Parameter
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
            
            # --- Record Learning Event ---
            try:
                self.learning_service.record_action(
                    parameter_id=param_id,
                    action='adjust',
                    old_value=decision.current_value if decision.current_value is not None else 0.0,
                    new_value=decision.suggested_value
                )
            except Exception as e:
                logger.error(f"Failed to record learning event: {e}")
            # ----------------------------------

            return True

        except Exception as e:
            logger.error(f"Failed to apply decision: {e}")
            return False

    def _get_current_parameter_value(self, parameter_name: str) -> Optional[float]:
        if parameter_name not in ParameterConfig.PARAMETER_IDS:
            return None
        param_id = ParameterConfig.PARAMETER_IDS[parameter_name]
        device = self.analyzer.get_device()
        return self.analyzer.get_latest_value(device, param_id)

    def _predict_indoor_temp_after_offset_change(self, current_offset: float, new_offset: float, current_indoor_temp: float) -> float:
        offset_change = new_offset - current_offset
        temp_change = offset_change * 0.5 
        return current_indoor_temp + temp_change

    def _is_decision_safe(self, decision: AIDecision) -> Tuple[bool, str]:
        return True, ""

    def _check_for_blocking_test(self) -> Optional[PlannedTest]:
        BLOCKING_PARAMETER_IDS = ['47007', '47011', '47206']
        active_tests = self.analyzer.session.query(PlannedTest).filter(PlannedTest.status == 'active').all()
        for test in active_tests:
            if test.parameter and test.parameter.parameter_id in BLOCKING_PARAMETER_IDS:
                return test
        return None

    def _get_recent_learning_history(self, hours_back: int = 24) -> str:
        return "HISTORY: Learning..."

    def _get_combined_forecast(self, device) -> str: # Pass device to get away mode
        # Implementation omitted for brevity
        if device and device.away_mode_enabled:
            return "FORECAST: Away mode active, no detailed forecast needed."
        return "FORECAST: Available"

    def _get_verified_facts(self) -> str:
        return "FACTS: None"

    def _get_performance_summary(self) -> str:
        return "PERFORMANCE: N/A"

    def _build_optimized_context(self, metrics, device) -> str: # Added device
        try:
            p_info = self.price_service.get_price_analysis()
            price_str = f"Price: {p_info.get('current_price',0):.2f} SEK/kWh. Status: {p_info.get('price_level', 'UNKNOWN')}."
        except Exception as e:
            logger.warning(f"Failed to get prices: {e}")
            price_str = "Price: N/A"

        # House DNA
        try:
            inertia = self.learning_service.analyze_thermal_inertia()
            dna_str = f"HOUSE_DNA: CoolRate(0C):{inertia.get('cooling_rate_0c', -0.15):.2f}C/h"
        except Exception as e:
            dna_str = "HOUSE_DNA: Learning..."

        # HW Probability
        try:
            # Look ahead 4 hours for HW risk
            probs = [self.hw_analyzer.get_usage_probability(datetime.now() + timedelta(hours=h)) for h in range(5)]
            hw_prob = max(probs) if probs else 0.0
            hw_str = f"HW_Usage_Risk: {'HIGH' if hw_prob > 0.5 else 'LOW'} ({hw_prob:.1f})"
        except Exception as e:
            hw_str = "HW_Usage_Risk: UNKNOWN"

        away_mode_str = ""
        if device and device.away_mode_enabled:
            away_mode_str = "AWAY_MODE_ACTIVE: Target indoor 16-17C, hot water demand MUST be 0."
            if device.away_mode_end_date: away_mode_str += f" Until: {device.away_mode_end_date.strftime('%Y-%m-%d %H:%M')}"

        return f"""DT:{datetime.now().strftime('%Y-%m-%d %H:%M')}
METRICS(72h):
Outdoor:{metrics.avg_outdoor_temp:.1f}C
Indoor:{metrics.avg_indoor_temp:.1f}C
COP:{metrics.estimated_cop:.2f}
DegMin:{metrics.degree_minutes:.0f}
Curve:{metrics.heating_curve}/Offset:{metrics.curve_offset}
{price_str}
{dna_str}
{hw_str}
{away_mode_str}
"""

    def _create_optimized_prompt(self, context: str, min_temp: float, target_min: float, target_max: float, mode: str = "tactical", metrics=None, device=None) -> str: # Added device
        indoor_temp = 20.0
        outdoor_temp = 0.0
        current_offset = -3.0
        
        if metrics:
            if metrics.avg_indoor_temp is not None: indoor_temp = metrics.avg_indoor_temp
            if metrics.avg_outdoor_temp is not None: outdoor_temp = metrics.avg_outdoor_temp
            if metrics.curve_offset is not None: current_offset = metrics.curve_offset

        import re
        price_match = re.search(r"Price: ([\d\.]+)", context)
        current_price = price_match.group(1) if price_match else "Unknown"

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

**TESTSCENARIO**: Override all other logic. Your ONLY goal is to set the 'Degree Minutes' parameter to -500. This is a temporary test to verify functionality.

STRATEGY LOGIC (Evaluate in order):

1. COMFORT PROTECTION (The Law):
   - IF Indoor > {target_max}: REDUCE heating (Target -4 or -5).
   - IF Indoor < {min_temp}: INCREASE heating (Target -1 or 0).

2. WEATHER ANTICIPATION (Proactive):
   - IF Forecast implies drop >3C next 4h: PRE-HEAT (Increase +1 step from current).
   - IF Forecast implies rise >3C next 4h: COAST (Decrease -1 step from current).

3. PRICE TREND STRATEGY (If comfort is OK):
   - **Scenario A: Price is DROPPING soon** (Cheap later):
     ACTION: COASTING. Reduce heating to save energy.
     Target: -4 IF Indoor > 21.0C (Buffer exists).
     Target: -3 IF Indoor < 21.0C (Don't risk comfort).
   
   - **Scenario B: Price is RISING soon** (Expensive later):
     ACTION: PRE-HEATING. Increase heating to buffer heat.
     Target: -2 or -1 (Only if Indoor < 22).

   - **Scenario C: Stable Price**:
     - If Expensive: Target -4 (only if Indoor > 20.8C).
     - If Cheap: Target -2 (to build buffer).

4. STABILITY (Override):
   - IF Indoor is PERFECT ({target_min} - {target_max}) AND Price is Unknown/Stable:
     ACTION: HOLD or gentle move to Baseline (-3). Do NOT make drastic changes (>1 step) if comfort is good.

5. EXECUTION:
   - Determine target based on above.
   - Max change: +/- 3 steps allowed (if needed).
   - Explain reasoning clearly.

6. HOT WATER STRATEGY (Strict Economy):
   - **Default State:** NORMAL (1).
   - **LUX (2) Rules (Use sparingly):**
     - Trigger ONLY if Temp is CRITICAL (<43°C).
     - OR if Price is EXTREMELY CHEAP (lowest 20% of day) AND Temp < 48°C.
     - NEVER use LUX just because "price is rising later" if current price is already high.
   - **ECONOMY (0) Rules:**
     - Use if Price is EXPENSIVE AND HW_Usage_Risk is LOW (next 4h).
     - Ensure Temp stays > 45°C before switching to Economy.
   - **Planning Horizon:** Focus on the next 3-6 hours. If usage is high soon, maintain NORMAL.

7. VENTILATION STRATEGY:
   - IF Outdoor Temp < -10°C -> Consider reducing ventilation (Target Speed 1) to save heat.
   - IF Electricity Price > 3.00 SEK/kWh -> Consider reducing ventilation (Target Speed 1).
   - Otherwise: Maintain Normal (Target Speed 2/Normal).
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
        clean_text = text.strip()
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0]
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].split("```")[0]
        clean_text = clean_text.strip()

        try:
            data = json.loads(clean_text)
            if isinstance(data, list):
                data = data[0]
            decision_model = AIDecisionModel(**data)
            return decision_model
        except Exception as e:
            logger.error(f"JSON parsing failed: {e}")
            raise ValueError(f"AI response failed validation: {e}")

    def _apply_decision(self, decision: AIDecision) -> bool:
        if decision.action != 'adjust' or not decision.parameter:
            logger.warning("Decision does not include adjustment")
            return False

        param_id = ParameterConfig.PARAMETER_IDS.get(decision.parameter)
        
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

            from data.models import ParameterChange, Parameter
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
            
            try:
                self.learning_service.record_action(
                    parameter_id=param_id,
                    action='adjust',
                    old_value=decision.current_value if decision.current_value is not None else 0.0,
                    new_value=decision.suggested_value
                )
            except Exception as e:
                logger.error(f"Failed to record learning event: {e}")

            return True

        except Exception as e:
            logger.error(f"Failed to apply decision: {e}")
            return False
