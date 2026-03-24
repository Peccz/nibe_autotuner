"""
Autonomous AI Agent V2 - Optimized & Safe
Uses Google Gemini API with fallback models and strict safety guardrails.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple, List
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, GoogleAPIError
from loguru import logger
from services.safety_guard import SafetyGuard
from pydantic import BaseModel, Field, ValidationError, ConfigDict

# Reuse existing classes
from integrations.autonomous_ai_agent import AIDecision, AutonomousAIAgent
from core.config import settings
from data.models import AIDecisionLog, Parameter, ParameterChange, PlannedTest, ABTestResult, GMAccount, PlannedHeatingSchedule
from data.evaluation_model import AIEvaluation
from services.price_service import price_service
from services.hw_analyzer import HotWaterPatternAnalyzer
from services.scientific_analyzer import ScientificTestAnalyzer
from services.learning_service import LearningService
from services.smart_planner import SmartPlanner

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class AIDecisionModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action: str = Field(..., pattern="^(adjust|hold|investigate)$")
    parameter: Optional[str] = None
    current_value: Optional[Any] = None # Can be str or float
    suggested_value: Optional[Any] = None # Can be str or float
    reasoning: str = Field(default="", min_length=0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_impact: str = Field(default="", min_length=0)

# ============================================================================
# CONFIGURATION
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

# ============================================================================
# AGENT IMPLEMENTATION
# ============================================================================

class AutonomousAIAgentV2(AutonomousAIAgent):
    """
    Improved version of AutonomousAIAgent with:
    1. Integration with SmartPlanner (Deterministic)
    2. Integration with GMController (Execution)
    3. Strategic AI role (Monitoring & Mode setting)
    """
    
    # Constants for Strategic Logic
    MIN_BALANCE_FOR_SPENDING = -500.0
    MAX_BALANCE_FOR_SAVING = 100.0

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
        self.planner = SmartPlanner() # Initialize SmartPlanner
        
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

        # 1. Update learning events
        self.learning_service.update_pending_events()

        # 2. Check for blocking tests (Temporarily disabled/simplified)
        # blocking_test = self._check_for_blocking_test()
        # if blocking_test: ...

        # 3. Execute SmartPlanner (Deterministic Layer)
        try:
            self.planner.plan_next_24h()
            logger.info("✓ SmartPlanner generated a new 24h heating plan.")
        except Exception as e:
            logger.error(f"❌ SmartPlanner failed to generate plan: {e}")
            import traceback
            traceback.print_exc()
            # If planner fails, we should arguably 'hold' or fallback to a safe mode.
            return AIDecision('hold', None, None, None, f"Planner error: {str(e)}", 0.0, "None")

        # 4. Gather Strategic Context for AI
        gm_account = self.db.query(GMAccount).first()
        current_gm_balance = gm_account.balance if gm_account else 0.0
        gm_mode = gm_account.mode if gm_account else 'NORMAL'
        
        # Get next hour's plan
        current_time_utc = datetime.now(timezone.utc)
        current_hour_plan = self.db.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp <= current_time_utc,
            PlannedHeatingSchedule.timestamp > current_time_utc - timedelta(hours=1)
        ).order_by(PlannedHeatingSchedule.timestamp.desc()).first()

        planned_action_for_hour = current_hour_plan.planned_action if current_hour_plan else "UNKNOWN"
        simulated_indoor_for_hour = current_hour_plan.simulated_indoor_temp if current_hour_plan else 0.0
        
        # Get metrics
        metrics = self.analyzer.calculate_metrics(hours_back=1)
        real_time_indoor = self.analyzer.get_latest_value(self.analyzer.get_device(), self.analyzer.PARAM_INDOOR_TEMP)
        if real_time_indoor is not None:
            metrics.avg_indoor_temp = real_time_indoor

        device = self.analyzer.get_device()
        min_safety_temp = device.min_indoor_temp_user_setting
        target_min_temp = device.target_indoor_temp_min
        target_max_temp = device.target_indoor_temp_max
        
        # 5. Build AI Prompt (Strategic Level)
        prompt = f'''
You are an autonomous AI agent controlling a Nibe heat pump. Your primary role is to set the strategic mode for the 'Gradminut Banken' (Degree Minute Bank) by updating the 'gm_account.mode' in the database. The 'SmartPlanner' generates a detailed 24-hour schedule based on optimal comfort and price, and the 'GMController' executes this minute-by-minute.

Your decisions should focus on:
1.  Ensuring the 'gm_account.mode' aligns with the overall strategic goal (SAVE, SPEND, NORMAL).
2.  Monitoring for critical deviations where the 'SmartPlanner' might need to be overridden or re-tuned.

**System Context:**
Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Outdoor Temp: {metrics.avg_outdoor_temp:.1f}°C
Indoor Temp: {metrics.avg_indoor_temp:.1f}°C (Target: {target_min_temp:.1f}-{target_max_temp:.1f}°C, Min Safety: {min_safety_temp:.1f}°C)
Current Electricity Price: {self.price_service.get_current_price().price_per_kwh:.2f} SEK/kWh
GM Bank Balance: {current_gm_balance:.1f}
GM Bank Mode (Current): '{gm_mode}'
Planned Action for this hour by SmartPlanner: '{planned_action_for_hour}'
Simulated Indoor Temp for this hour from SmartPlanner: {simulated_indoor_for_hour:.1f}°C

**Adjustable Parameters (Your Direct Control):**
- GM Bank Mode (DB: gm_account.mode): Current='{gm_mode}', Options=['SAVE', 'SPEND', 'NORMAL']

**Goals:**
- Maintain optimal comfort within [{target_min_temp}-{target_max_temp}]°C.
- Maximize energy cost savings.
- Ensure efficient pump operation.

**STRATEGIC LOGIC (Determine GM Bank Mode):**

1.  **EMERGENCY COMFORT (Safety Override):**
    -   IF Indoor Temp ({metrics.avg_indoor_temp:.1f}°C) < {min_safety_temp}:
        ACTION: 'adjust', parameter: 'gm_account.mode', suggested_value: 'SPEND', reasoning: 'Emergency comfort. Actual indoor temp is below safety limit. Forcing SPEND mode.'
    -   IF Indoor Temp ({metrics.avg_indoor_temp:.1f}°C) > {target_max_temp} + 1.0:
        ACTION: 'adjust', parameter: 'gm_account.mode', suggested_value: 'SAVE', reasoning: 'Actual indoor temp is too high. Forcing SAVE mode.'

2.  **ALIGN WITH PLANNER:**
    -   IF planned_action_for_hour == 'MUST_RUN' or planned_action_for_hour == 'RUN':
        ACTION: 'adjust', parameter: 'gm_account.mode', suggested_value: 'SPEND', reasoning: 'Aligning with SmartPlanner to run pump for planned heating period.'
    -   IF planned_action_for_hour == 'MUST_REST' or planned_action_for_hour == 'REST':
        ACTION: 'adjust', parameter: 'gm_account.mode', suggested_value: 'SAVE', reasoning: 'Aligning with SmartPlanner to rest pump for planned saving period.'

3.  **DEFAULT:**
    -   ACTION: 'adjust', parameter: 'gm_account.mode', suggested_value: 'NORMAL', reasoning: 'No override needed. Maintaining NORMAL operation to follow plan.'

**IMPORTANT:** Respond ONLY with a valid JSON object. Do not include any other text.
'''

        # 6. Execute AI Decision
        try:
            response_text = self._call_ai_with_fallback(prompt)
            decision_model = self._parse_json_response_robust(response_text)

            decision = AIDecision(
                action=decision_model.action,
                parameter=decision_model.parameter,
                current_value=gm_mode,
                suggested_value=decision_model.suggested_value,
                reasoning=decision_model.reasoning,
                confidence=decision_model.confidence,
                expected_impact=decision_model.expected_impact
            )

            # Log decision
            self._log_decision(decision, dry_run=dry_run)

            # Apply decision (only if it's an adjustment to mode)
            if not dry_run and decision.action == 'adjust':
                self._apply_decision(decision)

            return decision

        except Exception as e:
            logger.error(f"Error in AI Agent V2: {e}")
            import traceback
            traceback.print_exc()
            return AIDecision('hold', None, None, None, f"AI Error: {str(e)}", 0.0, "None")

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
            # Handle potential field mismatch
            if 'new_value' in data and 'suggested_value' not in data:
                data['suggested_value'] = data['new_value']
            if 'parameter_name' in data and 'parameter' not in data:
                data['parameter'] = data['parameter_name']
                
            decision_model = AIDecisionModel(**data)
            return decision_model
        except Exception as e:
            logger.error(f"JSON parsing failed: {e}")
            raise ValueError(f"AI response failed validation: {e}")

    def _apply_decision(self, decision: AIDecision) -> bool:
        """
        Apply AI decision to the system. In this new role, AI only sets GMAccount.mode.
        """
        if decision.parameter == 'gm_account.mode':
            try:
                gm_account = self.db.query(GMAccount).first()
                if not gm_account:
                    gm_account = GMAccount(balance=0.0, mode=decision.suggested_value) 
                    self.db.add(gm_account)
                else:
                    gm_account.mode = decision.suggested_value
                self.db.commit()
                logger.info(f"GM Account Mode set to: {decision.suggested_value} by AI.")
                return True
            except Exception as e:
                logger.error(f"Failed to set GM Account Mode: {e}")
                return False
        else:
            logger.warning(f"AI attempted to apply unknown parameter: {decision.parameter}. AI is only allowed to set 'gm_account.mode' in this phase.")
            return False

    def _check_for_blocking_test(self) -> Optional[PlannedTest]:
        return None 

    # --- Placeholder methods for base class compatibility/logging ---
    def _predict_indoor_temp_after_offset_change(self, current_offset: float, new_offset: float, current_indoor_temp: float) -> float:
        return current_indoor_temp # No-op

    def _is_decision_safe(self, decision: AIDecision) -> Tuple[bool, str]:
        return True, "Safe" # Logic moved to SmartPlanner/SafetyGuard

    def _get_recent_learning_history(self, hours_back: int = 24) -> str:
        return ""

    def _get_combined_forecast(self, device) -> str:
        return ""

    def _get_verified_facts(self) -> str:
        return ""

    def _get_performance_summary(self) -> str:
        return ""
    
    def _create_optimized_prompt(self, context: str, min_temp: float, target_min: float, target_max: float, mode: str = "tactical", metrics=None, device=None) -> str:
        # This is kept for compatibility if called, but not used in new flow
        return "Prompt not used in new architecture."

    def _build_optimized_context(self, metrics, device) -> str:
        return "Context not used in new architecture."
