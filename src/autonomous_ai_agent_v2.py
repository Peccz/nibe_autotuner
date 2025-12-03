"""
Autonomous AI Agent V2 - Optimized & Safe
Uses Claude API with strict safety guardrails and token optimization.
"""
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any
import anthropic
from loguru import logger

# Reuse existing classes
from autonomous_ai_agent import AIDecision, AutonomousAIAgent
from models import AIDecisionLog, Parameter, ParameterChange

class AutonomousAIAgentV2(AutonomousAIAgent):
    """
    Improved version of AutonomousAIAgent with:
    1. Hardcoded Safety Guardrails (cannot be overridden by LLM)
    2. Optimized Prompts (lower cost)
    3. Explicit Token Tracking
    """

    def analyze_and_decide(self, hours_back: int = 72, dry_run: bool = True) -> AIDecision:
        logger.info("="*80)
        logger.info("AUTONOMOUS AI AGENT V2 - Analysis (Optimized)")
        logger.info("="*80)

        # 1. Build Optimized Context (Less tokens, same info)
        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)
        context = self._build_optimized_context(metrics)

        # 2. Create Optimized Prompt
        prompt = self._create_optimized_prompt(context)

        # 3. Call Claude API
        try:
            logger.info("Calling Claude API...")
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000, # Reduced from 2000
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Log usage
            if hasattr(message, 'usage'):
                logger.info(f"Token Usage: Input={message.usage.input_tokens}, Output={message.usage.output_tokens}")

            response_text = message.content[0].text
            decision_data = self._parse_json_response(response_text)
            
            decision = AIDecision(
                action=decision_data['action'],
                parameter=decision_data.get('parameter'),
                current_value=decision_data.get('current_value'),
                suggested_value=decision_data.get('suggested_value'),
                reasoning=decision_data.get('reasoning', ''),
                confidence=float(decision_data.get('confidence', 0.0)),
                expected_impact=decision_data.get('expected_impact', '')
            )

            # 4. SAFETY CHECK (The V2 Upgrade)
            is_safe, safety_reason = self._is_decision_safe(decision)
            
            if not is_safe:
                logger.warning(f"⚠️ SAFETY GUARDRAIL TRIGGERED: {safety_reason}")
                logger.warning(f"Blocked decision: {decision}")
                
                # Convert to 'hold' decision
                decision.action = 'hold'
                decision.reasoning = f"[BLOCKED BY SAFETY GUARDRAIL] Original intent: {decision.reasoning}. Block reason: {safety_reason}"
                decision.suggested_value = None

            # 5. Log & Apply
            self._log_decision(decision, dry_run=dry_run)

            if not dry_run and decision.action == 'adjust' and decision.confidence >= 0.70:
                self._apply_decision(decision)

            return decision

        except Exception as e:
            logger.error(f"Error in AI Agent V2: {e}")
            # Return safe fallback
            return AIDecision('hold', None, None, None, f"Error: {str(e)}", 0.0, "None")

    def _is_decision_safe(self, decision: AIDecision) -> (bool, str):
        """
        Deterministic safety checks that override the AI.
        """
        if decision.action != 'adjust':
            return True, ""

        # Rule 1: Minimum Indoor Temperature
        # Never target below 19°C
        if decision.parameter == 'room_temp' and decision.suggested_value is not None:
            if decision.suggested_value < 19.0:
                return False, f"Suggested room temp {decision.suggested_value}°C is below safety limit (19.0°C)"

        # Rule 2: Parameter Bounds
        bounds = {
            'heating_curve': (1, 15),   # Nibe curve range
            'curve_offset': (-10, 10),  # Nibe offset range
            'start_compressor': (-1000, -60), # DM range
            'room_temp': (18, 25)
        }
        
        if decision.parameter in bounds and decision.suggested_value is not None:
            min_val, max_val = bounds[decision.parameter]
            if not (min_val <= decision.suggested_value <= max_val):
                return False, f"Value {decision.suggested_value} for {decision.parameter} is out of bounds ({min_val}-{max_val})"

        # Rule 3: Step Size Limits (Prevent drastic changes)
        # e.g. Don't change offset by more than 2 steps at once
        if decision.parameter == 'curve_offset' and decision.current_value is not None:
            diff = abs(decision.suggested_value - decision.current_value)
            if diff > 2:
                return False, f"Change of {diff} steps for curve_offset is too aggressive (max 2)"

        return True, ""

    def _build_optimized_context(self, metrics) -> str:
        """Compact context to save tokens"""
        return f"""DT:{datetime.now().strftime('%Y-%m-%d %H:%M')}
METRICS(72h):
Outdoor:{metrics.avg_outdoor_temp:.1f}C
Indoor:{metrics.avg_indoor_temp:.1f}C
COP:{metrics.estimated_cop:.2f}
DegMin:{metrics.degree_minutes:.0f}
Curve:{metrics.heating_curve}/Offset:{metrics.curve_offset}
"""

    def _create_optimized_prompt(self, context: str) -> str:
        return f"""System: Nibe F730 HeatPump. Goal: Optimize COP & Comfort.
Context:
{context}

Output JSON only.
Action: adjust|hold|investigate
Params: heating_curve(1-15), curve_offset(-10-10), start_compressor(-DM)
Rules: Indoor target 20-22C. Max 1 change. Min conf 0.7.

Example:
{{"action":"adjust","parameter":"curve_offset","current_value":0,"suggested_value":-1,"reasoning":"Indoor 22.5C > target. Save energy.","confidence":0.85,"expected_impact":"-0.5C indoor"}}
"""

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response"""
        clean_text = text.strip()
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0]
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].split("```")[0]
        return json.loads(clean_text)
