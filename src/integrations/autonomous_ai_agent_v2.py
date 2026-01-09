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
from sqlalchemy import text

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
from services.ventilation_manager import VentilationManager

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
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    expected_impact: str = Field(default="Balanced performance", min_length=0)

# ============================================================================
# CONFIGURATION
# ============================================================================

class ModelConfig:
    """Configuration for AI models with fallback support (Pro Only Strategy)"""
    FALLBACK_MODELS = [
        {
            'provider': 'gemini',
            'model': 'gemini-3-pro-preview',
            'name': 'Gemini 3.0 Pro (Newest)',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-2.5-pro',
            'name': 'Gemini 2.5 Pro',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-2.0-pro-exp-02-05',
            'name': 'Gemini 2.0 Pro',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-1.5-pro',
            'name': 'Gemini 1.5 Pro (Stable Fallback)',
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
        import time
        
        for i, model_entry in enumerate(self.available_models):
            model = model_entry['model']
            config = model_entry['config']
            
            # Try each model up to 2 times
            for attempt in range(2):
                try:
                    logger.info(f"Trying model {i+1}/{len(self.available_models)}: {config['name']} (Attempt {attempt+1})")
                    response = model.generate_content(
                        prompt,
                        generation_config={"response_mime_type": "application/json"}
                    )
                    logger.info(f"✓ Success with {config['name']}")
                    return response.text
                except Exception as e:
                    last_error = e
                    err_msg = str(e)
                    
                    if "429" in err_msg:
                        # Try to extract retry delay from Google's error message (e.g., "Please retry in 14.99s")
                        wait_seconds = 10 # Default fallback
                        match = re.search(r"retry in ([\d\.]+)s", err_msg)
                        if match:
                            wait_seconds = float(match.group(1)) + 1.0 # Add a buffer
                        
                        logger.warning(f"  ! Rate limited for {config['name']}. Waiting {wait_seconds:.1f}s as requested by Google...")
                        time.sleep(wait_seconds)
                    elif "404" in err_msg:
                        logger.warning(f"  ✗ {config['name']} not found (404). Skipping.")
                        break # Try next model
                    else:
                        logger.warning(f"  ✗ {config['name']} failed: {err_msg}")
                        break # Try next model
                        
        error_msg = f"All AI models failed. Last error: {str(last_error)}"
        logger.error(error_msg)
        raise Exception(error_msg)
        
    def _check_and_increment_quota(self) -> bool:
        """Check if we are within the daily free tier limit. Returns True if OK."""
        today = datetime.now().strftime('%Y-%m-%d')
        try:
            # Get current count
            res = self.db.execute(text("SELECT call_count FROM api_usage WHERE date = :date"), {"date": today}).fetchone()
            count = res[0] if res else 0
            
            if count >= 45: # Hard limit to stay safe within 50/day free tier
                logger.warning(f"⚠️ Quota Guard Triggered: {count} calls made today. Bypassing AI to ensure 100% free operation.")
                return False
                
            # Increment (or insert)
            if res:
                self.db.execute(text("UPDATE api_usage SET call_count = call_count + 1 WHERE date = :date"), {"date": today})
            else:
                self.db.execute(text("INSERT INTO api_usage (date, call_count) VALUES (:date, 1)"), {"date": today})
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Quota check failed: {e}")
            return True # If DB fails, we allow the call but log error

    def analyze_and_decide(self, hours_back: int = 72, dry_run: bool = True, mode: str = "tactical") -> AIDecision:
        logger.info("="*80)
        logger.info(f"AUTONOMOUS AI AGENT V2 (GEMINI) - Analysis [Mode: {mode.upper()}]")
        logger.info("="*80)

        # QM ADDITION: Manage Ventilation based on humidity
        try:
            vent_manager = VentilationManager(self.api_client)
            vent_manager.check_and_adjust()
        except Exception as e:
            logger.error(f"Ventilation management failed: {e}")

        # 1. Update learning events
        self.learning_service.update_pending_events()

        # 2. Execute SmartPlanner (Deterministic Layer)
        try:
            self.planner.plan_next_24h()
            logger.info("✓ SmartPlanner generated a new 24h heating plan.")
        except Exception as e:
            logger.error(f"❌ SmartPlanner failed to generate plan: {e}")
            return AIDecision('hold', None, None, None, f"Planner error: {str(e)}", 0.0, "None")

        # 3. Gather Strategic Context
        gm_account = self.db.query(GMAccount).first()
        current_gm_balance = gm_account.balance if gm_account else 0.0
        gm_mode = gm_account.mode if gm_account else 'NORMAL'
        
        # Get current curve offset from pump
        current_offset = self.analyzer.get_latest_value(self.analyzer.get_device(), '47011') or 0.0
        
        # Get current hour's plan
        current_time_utc = datetime.now(timezone.utc)
        current_hour_plan = self.db.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp <= current_time_utc,
            PlannedHeatingSchedule.timestamp > current_time_utc - timedelta(hours=1)
        ).order_by(PlannedHeatingSchedule.timestamp.desc()).first()

        planned_action_for_hour = current_hour_plan.planned_action if current_hour_plan else "UNKNOWN"
        
        # QUOTA GUARD CHECK
        if not dry_run and not self._check_and_increment_quota():
            # DETERMINISTIC FALLBACK
            reasoning = f"Quota reached. Falling back to deterministic action: {planned_action_for_hour}"
            sugg_mode = 'SPEND' if planned_action_for_hour in ['RUN', 'MUST_RUN'] else 'SAVE'
            decision = AIDecision('adjust', 'gm_account.mode', gm_mode, sugg_mode, reasoning, 1.0, "Zero-cost fallback")
            self._log_decision(decision, dry_run=False)
            self._apply_decision(decision)
            return decision

        # 4. Get metrics
        metrics = self.analyzer.calculate_metrics(hours_back=1)
        
        # DOWNSTAIRS (Primary) - Prefer IKEA High Precision
        latest_reading = self.analyzer.get_latest_reading(self.analyzer.get_device(), self.analyzer.PARAM_HA_TEMP_DOWNSTAIRS)
        if not latest_reading:
            latest_reading = self.analyzer.get_latest_reading(self.analyzer.get_device(), self.analyzer.PARAM_INDOOR_TEMP)
            
        is_indoor_stale = False
        if latest_reading:
            age_seconds = (datetime.utcnow() - latest_reading.timestamp).total_seconds()
            if age_seconds > 2700: # 45 minutes
                is_indoor_stale = True
                logger.warning(f"Downstairs temp is STALE! {age_seconds/3600:.1f} hours old.")
            metrics.avg_indoor_temp = latest_reading.value
        else:
            is_indoor_stale = True
            metrics.avg_indoor_temp = 21.0

        # DEXTER (Comfort Guard)
        dexter_reading = self.analyzer.get_latest_reading(self.analyzer.get_device(), self.analyzer.PARAM_HA_TEMP_DEXTER)
        dexter_temp = dexter_reading.value if dexter_reading else metrics.avg_indoor_temp
        is_dexter_stale = (datetime.utcnow() - (dexter_reading.timestamp if dexter_reading else datetime.min)).total_seconds() > 2700

        # PRICE-AWARE THRESHOLD LOGIC
        current_price = self.price_service.get_current_price()
        try:
            prices_today = self.price_service.get_prices_today()
            avg_price = sum(p.price_per_kwh for p in prices_today) / len(prices_today) if prices_today else 1.0
        except:
            avg_price = 1.0

        if current_price > avg_price * 1.5:
            dexter_threshold = 18.5  # Expensive: lower the floor
        elif current_price < avg_price * 0.8:
            dexter_threshold = 19.8  # Cheap: raise the floor
        else:
            dexter_threshold = 19.3  # Normal

        device = self.analyzer.get_device()
        min_safety_temp = device.min_indoor_temp_user_setting
        target_min_temp = device.target_indoor_temp_min
        target_max_temp = device.target_indoor_temp_max
        
        # Define Emergency Logic
        emergency_logic = ""
        if not is_indoor_stale:
             emergency_logic = f"""
1.  **EMERGENCY COMFORT (Safety Override):**
    -   IF Downstairs Temp ({metrics.avg_indoor_temp:.1f}°C) < {min_safety_temp}:
        ACTION: 'adjust', parameter: 'gm_account.mode', suggested_value: 'SPEND', reasoning: 'Emergency comfort. Downstairs is below safety limit.'
    -   IF Dexter Room Temp ({dexter_temp:.1f}°C) < {dexter_threshold} and not {is_dexter_stale}:
        ACTION: 'adjust', parameter: '47011', suggested_value: 4, reasoning: 'Dexter boost (Price-aware threshold: {dexter_threshold}C). Radiators need high temp water NOW.'
    -   IF Downstairs Temp ({metrics.avg_indoor_temp:.1f}°C) > {target_max_temp} + 1.0:
        ACTION: 'adjust', parameter: 'gm_account.mode', suggested_value: 'SAVE', reasoning: 'Downstairs is too warm. Forcing SAVE mode.'
"""
        else:
             emergency_logic = """
1.  **EMERGENCY COMFORT (Safety Override):**
    -   DISABLED due to STALE indoor temperature data.
"""

        # 4. Build AI Prompt (Strategic Level)
        prompt = f'''
You are an autonomous AI agent controlling a Nibe heat pump. You control 'gm_account.mode' (Runtime) and '47011' (Curve Offset).

**Strategic Insight:**
- Upstairs (Dexter's Room) has radiators. They respond FAST to hot water.
- Downstairs has floor heating with a 32C SHUNT. It ignores water hotter than 32C.
- Use '47011' (Offset) to +4 to 'blast' heat into the radiators without affecting the downstairs.

**System Context:**
Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Outdoor Temp: {metrics.avg_outdoor_temp:.1f}C
Downstairs Temp: {metrics.avg_indoor_temp:.1f}C (Target: {target_min_temp}-{target_max_temp}C)
Dexter Room Temp: {dexter_temp:.1f}C (Comfort Floor: {dexter_threshold}C)
Current Offset: {current_offset}
Planned Action: '{planned_action_for_hour}'

**Adjustable Parameters:**
- 'gm_account.mode': Options=['SAVE', 'SPEND', 'NORMAL']. (IMPORTANT: You must return one of these as a string).
- '47011' (Heating Curve Offset): Range [-10, 10]. Default 0.

**STRATEGIC LOGIC:**

{emergency_logic}

2.  **ALIGN WITH PLANNER & BOOST RADIATORS:**
    -   IF planned_action_for_hour == 'RUN':
        - Set 'gm_account.mode' to 'SPEND'.
        - IF Dexter Room < 20.0: Set '47011' to 3.
        - ELSE: Set '47011' to 0.
    -   IF planned_action_for_hour == 'REST':
        - Set 'gm_account.mode' to 'SAVE'.
        - Set '47011' to 0.

**IMPORTANT:** Respond ONLY with a valid JSON object. NEVER use null for 'suggested_value'.
'''

        # 5. Execute AI Decision
        try:
            response_text = self._call_ai_with_fallback(prompt)
            decision_model = self._parse_json_response_robust(response_text)
            
            # QM SAFETY: Ensure suggested_value is never None
            sugg_val = decision_model.suggested_value
            if sugg_val is None:
                if decision_model.parameter == 'gm_account.mode':
                    sugg_val = 'NORMAL'
                else:
                    sugg_val = 0.0

            decision_for_apply = AIDecision(
                action=decision_model.action,
                parameter=decision_model.parameter,
                current_value=gm_mode if decision_model.parameter == 'gm_account.mode' else current_offset,
                suggested_value=sugg_val,
                reasoning=decision_model.reasoning,
                confidence=decision_model.confidence,
                expected_impact=decision_model.expected_impact
            )

            # Log sanitized decision
            self._log_decision(decision_for_apply, dry_run=dry_run)

            if not dry_run and decision_for_apply.action == 'adjust':
                self._apply_decision(decision_for_apply)

            return decision_for_apply

        except Exception as e:
            logger.error(f"Error in AI Agent V2: {e}")
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
            if 'new_value' in data and 'suggested_value' not in data:
                data['suggested_value'] = data['new_value']
            if 'parameter_name' in data and 'parameter' not in data:
                data['parameter'] = data['parameter_name']
                
            return AIDecisionModel(**data)
        except Exception as e:
            logger.error(f"JSON parsing failed: {e}")
            raise ValueError(f"AI response failed validation: {e}")

    def _apply_decision(self, decision: AIDecision) -> bool:
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
        elif decision.parameter == '47011':
            try:
                device = self.analyzer.get_device()
                val = float(decision.suggested_value)
                self.api_client.set_point_value(device.device_id, '47011', val)
                logger.info(f"Curve Offset (47011) set to: {val} by AI.")
                return True
            except Exception as e:
                logger.error(f"Failed to set Curve Offset: {e}")
                return False
        return False

    def _log_decision(self, decision: AIDecision, dry_run: bool = False):
        try:
            # Map strategic modes to numeric values, or use raw float for offset
            mode_map = {'NORMAL': 0.0, 'SAVE': 1.0, 'SPEND': 2.0}
            
            curr_val = decision.current_value
            sugg_val = decision.suggested_value
            
            if decision.parameter == 'gm_account.mode':
                curr_val = mode_map.get(str(decision.current_value).upper(), 0.0)
                sugg_val = mode_map.get(str(decision.suggested_value).upper(), 0.0)
            
            log_entry = AIDecisionLog(
                action=decision.action,
                current_value=float(curr_val) if curr_val is not None else None,
                suggested_value=float(sugg_val) if sugg_val is not None else None,
                reasoning=f"[{decision.parameter}] {decision.reasoning}",
                confidence=decision.confidence,
                expected_impact=decision.expected_impact,
                applied=not dry_run
            )
            self.db.add(log_entry)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log decision: {e}")
            self.db.rollback()
