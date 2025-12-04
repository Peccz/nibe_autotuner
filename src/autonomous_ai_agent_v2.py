"""
Autonomous AI Agent V2 - Optimized & Safe
Uses Google Gemini API with strict safety guardrails and token optimization.
"""
import os
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import google.generativeai as genai
from loguru import logger
from pydantic import BaseModel, Field, ValidationError, ConfigDict

# Reuse existing classes
from autonomous_ai_agent import AIDecision, AutonomousAIAgent
from models import AIDecisionLog, Parameter, ParameterChange
from price_service import ElectricityPriceService
from hw_analyzer import HotWaterPatternAnalyzer

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

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
        'curve_offset': 2,      # Max ±2 steps
        'heating_curve': 1,     # Max ±1 step
        'room_temp': 1,         # Max ±1°C
    }

    # Minimum temperature thresholds
    MIN_INDOOR_TEMP = 19.0  # Never target below this

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
        Initialize autonomous AI agent with Gemini
        """
        self.analyzer = analyzer
        self.api_client = api_client
        self.weather_service = weather_service
        self.device_id = device_id
        
        # Initialize Price Service (defaults to SE3 Stockholm)
        self.price_service = ElectricityPriceService("SE3")
        
        # Initialize HW Usage Analyzer
        self.hw_analyzer = HotWaterPatternAnalyzer()

        # Configure Gemini
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")
            
        genai.configure(api_key=api_key)
        # Use Gemini 2.0 Flash (or Pro) for speed and reasoning
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    def analyze_and_decide(self, hours_back: int = 72, dry_run: bool = True) -> AIDecision:
        logger.info("="*80)
        logger.info("AUTONOMOUS AI AGENT V2 (GEMINI) - Analysis")
        logger.info("="*80)

        # Train HW analyzer (lightweight, uses cached data if available)
        try:
            self.hw_analyzer.train_on_history(days_back=14)
        except Exception as e:
            logger.warning(f"HW Analyzer training failed: {e}")

        # 1. Build Optimized Context
        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)
        context = self._build_optimized_context(metrics)

        # 2. Create Optimized Prompt
        prompt = self._create_optimized_prompt(context)

        # 3. Call Gemini API
        try:
            logger.info("Calling Gemini API...")
            
            # Force JSON response via generation config
            response = self.model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Log token usage
            logger.info("Gemini response received")

            response_text = response.text
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

    def _is_decision_safe(self, decision: AIDecision) -> Tuple[bool, str]:
        """
        Deterministic safety checks that override the AI.
        Uses centralized ParameterConfig for all bounds and limits.
        """
        if decision.action != 'adjust':
            return True, ""

        if decision.suggested_value is None or decision.parameter is None:
            return False, "Missing required fields: parameter or suggested_value"

        # Rule 1: Minimum Indoor Temperature (Safety over Cost)
        if decision.parameter == 'room_temp':
            if decision.suggested_value < ParameterConfig.MIN_INDOOR_TEMP:
                return False, f"Suggested room temp {decision.suggested_value}°C is below safety limit ({ParameterConfig.MIN_INDOOR_TEMP}°C)"

        # Rule 2: Parameter Bounds
        if decision.parameter in ParameterConfig.BOUNDS:
            min_val, max_val = ParameterConfig.BOUNDS[decision.parameter]
            if not (min_val <= decision.suggested_value <= max_val):
                return False, f"Value {decision.suggested_value} for {decision.parameter} is out of bounds ({min_val}-{max_val})"

        # Rule 3: Step Size Limits (Prevent drastic changes)
        if decision.parameter in ParameterConfig.MAX_STEP_SIZES and decision.current_value is not None:
            max_step = ParameterConfig.MAX_STEP_SIZES[decision.parameter]
            diff = abs(decision.suggested_value - decision.current_value)
            if diff > max_step:
                return False, f"Change of {diff} steps for {decision.parameter} is too aggressive (max {max_step})"

        return True, ""

    def _build_optimized_context(self, metrics) -> str:
        """Compact context to save tokens"""
        
        # Fetch Price Data
        try:
            p_info = self.price_service.get_current_price_info()
            price_str = f"Price:{p_info.get('current_price_sek',0)} SEK/kWh. Status:{'CHEAP' if p_info.get('is_cheap') else 'EXPENSIVE' if p_info.get('is_expensive') else 'NORMAL'}."
        except Exception as e:
            logger.warning(f"Failed to get prices: {e}")
            price_str = "Price: N/A"

        # Fetch HW Probability
        try:
            hw_prob = self.hw_analyzer.get_usage_probability(datetime.now())
            hw_str = f"HW_Usage_Risk: {'HIGH' if hw_prob > 0.5 else 'LOW'} ({hw_prob:.1f})"
        except Exception as e:
            hw_str = "HW_Usage_Risk: UNKNOWN"

        return f"""DT:{datetime.now().strftime('%Y-%m-%d %H:%M')}
METRICS(72h):
Outdoor:{metrics.avg_outdoor_temp:.1f}C
Indoor:{metrics.avg_indoor_temp:.1f}C
COP:{metrics.estimated_cop:.2f}
DegMin:{metrics.degree_minutes:.0f}
Curve:{metrics.heating_curve}/Offset:{metrics.curve_offset}
{price_str}
{hw_str}
"""

    def _create_optimized_prompt(self, context: str) -> str:
        return f"""System: Nibe F730 HeatPump. Goal: Optimize COP, Comfort & COST.
Context:
{context}

Output JSON only.
Action: adjust|hold|investigate
Params: heating_curve(1-15), curve_offset(-10-10), start_compressor(-DM), hot_water_demand(0-2), increased_ventilation(0-4)
Rules: Indoor target 20-22C. Max 1 change. Min conf 0.7.
STRATEGY: 
1. If Price EXPENSIVE: Lower heat (Offset -1). Set HotWater=Small(0) if HW_Usage_Risk is LOW.
2. If Price CHEAP: Buffer heat (Offset +1). Set HotWater=Large(2) if HW_Usage_Risk is HIGH.
3. If HW_Usage_Risk is HIGH: Ensure HotWater is at least Medium(1).

Example:
{{"action":"adjust","parameter":"hot_water_demand","current_value":1,"suggested_value":0,"reasoning":"Price is EXPENSIVE & HW Usage Risk is LOW. Saving energy.","confidence":0.9,"expected_impact":"Save energy"}}
"""

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
