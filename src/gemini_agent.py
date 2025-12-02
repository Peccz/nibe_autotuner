"""
Gemini AI Agent for Nibe Heat Pump Optimization

Uses Google Gemini 2.5 Flash for intelligent analysis and recommendations.
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
import google.generativeai as genai
from dataclasses import dataclass
from loguru import logger


@dataclass
class GeminiRecommendation:
    """AI recommendation from Gemini"""
    parameter_id: str
    parameter_name: str
    current_value: float
    suggested_value: float
    reasoning: str
    priority: str  # 'high', 'medium', 'low'
    estimated_impact: str
    confidence: float  # 0.0 to 1.0


class GeminiAgent:
    """Gemini AI Agent for heat pump optimization"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini agent

        Args:
            api_key: Google API key (if not provided, reads from GOOGLE_API_KEY env var)
        """
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")

        genai.configure(api_key=self.api_key)

        # Use Gemini 2.5 Flash - fast, cost-effective, powerful
        self.model = genai.GenerativeModel('gemini-2.5-flash-002')

        # System prompt for heat pump optimization
        self.system_prompt = """Du är en expert på värmepumpsoptimering, specifikt Nibe F730 exhaust air heat pump.

Din uppgift är att analysera prestanda-data och ge intelligenta rekommendationer för att:
1. Maximera COP (Coefficient of Performance)
2. Minimera gradminuter (avvikelse från måltemperatur)
3. Optimera komfort och energieffektivitet

VIKTIGA SÄKERHETSREGLER:
- Rekommendera ALDRIG värden utanför tillåtna intervall
- Ändra endast EN parameter åt gången
- Ge alltid tydlig motivering för varje rekommendation
- Markera högprioriterade åtgärder som kan ge snabb förbättring

PARAMETRAR DU KAN JUSTERA:
- 47011: Room temp setpoint room sensor (14-30°C) - Måltemperatur för rumssensor
- 47041: Room sensor factor (0-10) - Hur mycket rumssensorn påverkar regleringen
- 47015: Room temp setpoint S4 (5-30°C) - Extra värmebehov för S4-läge
- 47007: Offset S4 (-10 till +10°C) - Kurvförskjutning för S4
- 47020: Min supply temp (-10 till +30°C) - Lägsta tillåtna framledningstemperatur
- 47019: Max supply temp (20-70°C) - Högsta tillåtna framledningstemperatur

TOLKNINGSNYCKLAR:
- COP >3.0 = Utmärkt, 2.5-3.0 = Bra, 2.0-2.5 = OK, <2.0 = Dåligt
- Gradminuter: Lägre = bättre komfort. <50 = utmärkt, 50-100 = bra, >100 = förbättring behövs
- Delta T aktiv: Temperaturskillnad mellan framledning och retur när värmepumpen kör
- Kompressorfrekvens: 30-50Hz = låg belastning, 50-70Hz = normal, >70Hz = hög belastning

Svara ALLTID med valid JSON i följande format:
{
  "recommendations": [
    {
      "parameter_id": "47011",
      "parameter_name": "Room temp setpoint",
      "current_value": 22.0,
      "suggested_value": 21.5,
      "reasoning": "Detaljerad förklaring...",
      "priority": "high|medium|low",
      "estimated_impact": "Förväntat resultat...",
      "confidence": 0.85
    }
  ],
  "analysis": "Övergripande analys av systemets prestanda...",
  "status": "good|warning|critical"
}"""

    def analyze_and_recommend(
        self,
        metrics: Dict[str, Any],
        recent_changes: List[Dict[str, Any]],
        current_parameters: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Analyze current system state and generate recommendations

        Args:
            metrics: Current performance metrics (COP, degree minutes, etc.)
            recent_changes: Recent parameter changes for context
            current_parameters: Current parameter values

        Returns:
            Dict with recommendations, analysis, and status
        """
        try:
            # Build context prompt
            prompt = self._build_analysis_prompt(metrics, recent_changes, current_parameters)

            logger.info("Sending analysis request to Gemini 2.5 Flash...")

            # Generate response
            response = self.model.generate_content(
                [self.system_prompt, prompt],
                generation_config={
                    'temperature': 0.3,  # Lower temperature for consistent recommendations
                    'top_p': 0.8,
                    'top_k': 40,
                    'max_output_tokens': 2048,
                }
            )

            # Parse JSON response
            response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]

            result = json.loads(response_text.strip())

            logger.info(f"Gemini analysis complete: {len(result.get('recommendations', []))} recommendations")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response: {e}")
            logger.error(f"Response text: {response_text}")
            return {
                'recommendations': [],
                'analysis': f'AI-fel: Kunde inte tolka svar ({str(e)})',
                'status': 'error'
            }
        except Exception as e:
            logger.error(f"Gemini analysis failed: {e}")
            return {
                'recommendations': [],
                'analysis': f'AI-fel: {str(e)}',
                'status': 'error'
            }

    def _build_analysis_prompt(
        self,
        metrics: Dict[str, Any],
        recent_changes: List[Dict[str, Any]],
        current_parameters: Dict[str, float]
    ) -> str:
        """Build detailed analysis prompt"""

        prompt = f"""Analysera följande värmepumpsdata och ge rekommendationer:

## AKTUELL PRESTANDA (senaste 24h)
- COP: {metrics.get('cop', 'N/A')}
- Gradminuter: {metrics.get('degree_minutes', 'N/A')}
- Delta T (aktiv): {metrics.get('delta_t_active', 'N/A')}°C
- Kompressorfrekvens (medel): {metrics.get('avg_compressor_frequency', 'N/A')} Hz
- Drifttid: {metrics.get('runtime_hours', 'N/A')} timmar
- Tillförd energi: {metrics.get('total_energy_in', 'N/A')} kWh
- Producerad energi: {metrics.get('total_energy_out', 'N/A')} kWh

## TEMPERATURDATA
- Rumstemperatur: {metrics.get('room_temp', 'N/A')}°C
- Utomhustemperatur: {metrics.get('outdoor_temp', 'N/A')}°C
- Framledningstemperatur: {metrics.get('supply_temp', 'N/A')}°C
- Returtemperatur: {metrics.get('return_temp', 'N/A')}°C

## JÄMFÖRELSE MED IGÅR
- COP igår: {metrics.get('cop_yesterday', 'N/A')}
- Gradminuter igår: {metrics.get('degree_minutes_yesterday', 'N/A')}
- Delta T igår: {metrics.get('delta_t_active_yesterday', 'N/A')}°C

## AKTUELLA PARAMETERVÄRDEN
"""

        for param_id, value in current_parameters.items():
            prompt += f"- {param_id}: {value}\n"

        if recent_changes:
            prompt += f"\n## SENASTE ÄNDRINGAR ({len(recent_changes)} st)\n"
            for change in recent_changes[-5:]:  # Last 5 changes
                timestamp = change.get('timestamp', 'N/A')
                param_name = change.get('parameter_name', 'Unknown')
                old_val = change.get('old_value', 'N/A')
                new_val = change.get('new_value', 'N/A')
                reason = change.get('reason', 'N/A')
                prompt += f"- {timestamp}: {param_name} ({old_val} → {new_val}) - {reason}\n"

        prompt += """

## UPPDRAG
Baserat på ovanstående data:
1. Identifiera förbättringsområden
2. Ge 1-3 konkreta parameterändringar som kan förbättra COP eller komfort
3. Förklara varför varje ändring kommer hjälpa
4. Uppskatta förväntad effekt av varje ändring
5. Ge övergripande statusbedömning

Svara med valid JSON enligt det fördefinierade formatet."""

        return prompt

    def explain_metric(self, metric_name: str, value: float, context: Dict[str, Any]) -> str:
        """
        Get natural language explanation of a metric

        Args:
            metric_name: Name of the metric
            value: Current value
            context: Additional context data

        Returns:
            Human-readable explanation
        """
        try:
            prompt = f"""Förklara kort (max 2 meningar) vad detta betyder för användaren:

Mätvärde: {metric_name}
Värde: {value}
Kontext: {json.dumps(context, indent=2)}

Ge en tydlig, icke-teknisk förklaring på svenska."""

            response = self.model.generate_content(
                prompt,
                generation_config={'temperature': 0.5, 'max_output_tokens': 256}
            )

            return response.text.strip()

        except Exception as e:
            logger.error(f"Failed to explain metric: {e}")
            return f"Värde: {value}"

    def chat(self, user_message: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Interactive chat with the AI agent

        Args:
            user_message: User's question or message
            conversation_history: Previous messages in the conversation

        Returns:
            AI response
        """
        try:
            # Build conversation context
            messages = [self.system_prompt]

            if conversation_history:
                for msg in conversation_history[-10:]:  # Last 10 messages
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    messages.append(f"{role}: {content}")

            messages.append(f"user: {user_message}")

            response = self.model.generate_content(
                '\n\n'.join(messages),
                generation_config={'temperature': 0.7, 'max_output_tokens': 1024}
            )

            return response.text.strip()

        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return f"Ursäkta, jag kunde inte svara på den frågan. Fel: {str(e)}"


# Convenience function for quick analysis
def quick_analyze(
    metrics: Dict[str, Any],
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Quick analysis without managing agent instance

    Args:
        metrics: Performance metrics
        api_key: Google API key (optional)

    Returns:
        Analysis results
    """
    agent = GeminiAgent(api_key=api_key)
    return agent.analyze_and_recommend(metrics, [], {})
