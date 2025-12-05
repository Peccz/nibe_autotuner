"""
Smart Optimization Engine
Combines: Performance Score, Cost Tracking, AI Recommendations
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from services.analyzer import HeatPumpAnalyzer
from integrations.gemini_agent import GeminiAgent, GeminiRecommendation
from core.config import settings


@dataclass
class PerformanceScore:
    """Overall system performance score"""
    total_score: int  # 0-100
    cop_score: int
    delta_t_score: int
    comfort_score: int
    efficiency_score: int
    grade: str  # 'A+', 'A', 'B', 'C', 'D', 'F'
    emoji: str


@dataclass
class CostAnalysis:
    """Detailed cost analysis"""
    daily_cost_sek: float
    monthly_cost_sek: float
    yearly_cost_sek: float
    heating_cost_daily: float
    hot_water_cost_daily: float
    cop_avg: float
    baseline_yearly_cost: float  # If no optimization
    savings_yearly: float


@dataclass
class OptimizationSuggestion:
    """AI-generated optimization suggestion"""
    priority: str  # 'high', 'medium', 'low'
    title: str
    description: str
    parameter_name: str
    parameter_id: str
    current_value: float
    suggested_value: float
    expected_cop_improvement: float
    expected_savings_yearly: float
    confidence: float  # 0-1
    reasoning: str


class SmartOptimizer:
    """Smart optimization engine with Gemini AI"""

    # Electricity price
    ELECTRICITY_PRICE_SEK_KWH = 2.0

    # Baseline COP (typical unoptimized system)
    BASELINE_COP = 2.5

    # Compressor power
    COMPRESSOR_POWER_KW = 1.5

    def __init__(self, analyzer: HeatPumpAnalyzer, use_ai: bool = True):
        self.analyzer = analyzer
        self.use_ai = use_ai

        # Initialize Gemini if API key is available
        self.gemini_agent = None
        if use_ai and settings.GOOGLE_API_KEY:
            try:
                self.gemini_agent = GeminiAgent()
            except Exception as e:
                print(f"Warning: Could not initialize Gemini agent: {e}")
                self.use_ai = False

    def calculate_performance_score(self, hours_back: int = 72) -> PerformanceScore:
        """
        Calculate overall performance score 0-100

        Components:
        - COP: 40 points
        - Delta T: 20 points
        - Comfort (temp stability): 20 points
        - Efficiency (cycles, runtime): 20 points
        """
        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)

        score = 0
        cop_score = 0
        delta_t_score = 0
        comfort_score = 0
        efficiency_score = 0

        # COP Score (40 points)
        if metrics.estimated_cop:
            if metrics.estimated_cop >= 4.5:
                cop_score = 40
            elif metrics.estimated_cop >= 4.0:
                cop_score = 35
            elif metrics.estimated_cop >= 3.5:
                cop_score = 30
            elif metrics.estimated_cop >= 3.0:
                cop_score = 25
            elif metrics.estimated_cop >= 2.5:
                cop_score = 15
            else:
                cop_score = 5

        # Delta T Score (20 points) - Optimal 5-7°C
        if metrics.delta_t_active:
            if 5.0 <= metrics.delta_t_active <= 7.0:
                delta_t_score = 20
            elif 4.0 <= metrics.delta_t_active <= 8.0:
                delta_t_score = 15
            elif 3.0 <= metrics.delta_t_active <= 9.0:
                delta_t_score = 10
            else:
                delta_t_score = 5

        # Comfort Score (20 points) - Stable indoor temp around 21°C
        if metrics.avg_indoor_temp:
            temp_deviation = abs(metrics.avg_indoor_temp - 21.0)
            if temp_deviation <= 0.5:
                comfort_score = 20
            elif temp_deviation <= 1.0:
                comfort_score = 15
            elif temp_deviation <= 1.5:
                comfort_score = 10
            else:
                comfort_score = 5

        # Efficiency Score (20 points) - Low cycles, good runtime
        if metrics.heating_metrics:
            cycles = metrics.heating_metrics.num_cycles
            runtime = metrics.heating_metrics.runtime_hours

            # Fewer cycles is better
            if cycles <= 10:
                efficiency_score += 10
            elif cycles <= 15:
                efficiency_score += 7
            elif cycles <= 20:
                efficiency_score += 5
            else:
                efficiency_score += 2

            # Decent runtime is good
            if runtime and runtime >= 12:
                efficiency_score += 10
            elif runtime and runtime >= 8:
                efficiency_score += 7
            elif runtime and runtime >= 4:
                efficiency_score += 5

        total_score = cop_score + delta_t_score + comfort_score + efficiency_score

        # Determine grade
        if total_score >= 90:
            grade, emoji = 'A+', '🏆'
        elif total_score >= 80:
            grade, emoji = 'A', '⭐'
        elif total_score >= 70:
            grade, emoji = 'B', '✨'
        elif total_score >= 60:
            grade, emoji = 'C', '👍'
        elif total_score >= 50:
            grade, emoji = 'D', '😐'
        else:
            grade, emoji = 'F', '⚠️'

        return PerformanceScore(
            total_score=total_score,
            cop_score=cop_score,
            delta_t_score=delta_t_score,
            comfort_score=comfort_score,
            efficiency_score=efficiency_score,
            grade=grade,
            emoji=emoji
        )

    def calculate_costs(self, hours_back: int = 72) -> CostAnalysis:
        """Calculate detailed cost analysis"""
        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)

        # Calculate actual costs
        heating_cost_daily = 0
        hot_water_cost_daily = 0

        if metrics.heating_metrics and metrics.heating_metrics.runtime_hours:
            hours_per_day = metrics.heating_metrics.runtime_hours / (hours_back / 24)
            heating_cost_daily = hours_per_day * self.COMPRESSOR_POWER_KW * self.ELECTRICITY_PRICE_SEK_KWH

        if metrics.hot_water_metrics and metrics.hot_water_metrics.runtime_hours:
            hours_per_day = metrics.hot_water_metrics.runtime_hours / (hours_back / 24)
            hot_water_cost_daily = hours_per_day * self.COMPRESSOR_POWER_KW * self.ELECTRICITY_PRICE_SEK_KWH

        daily_cost = heating_cost_daily + hot_water_cost_daily
        monthly_cost = daily_cost * 30
        yearly_cost = daily_cost * 365

        # Calculate baseline (unoptimized) cost
        avg_cop = metrics.estimated_cop if metrics.estimated_cop else self.BASELINE_COP
        baseline_cop = self.BASELINE_COP

        # If current COP is better than baseline, we're saving money
        if avg_cop > baseline_cop:
            baseline_yearly = yearly_cost * (avg_cop / baseline_cop)
            savings_yearly = baseline_yearly - yearly_cost
        else:
            baseline_yearly = yearly_cost
            savings_yearly = 0

        return CostAnalysis(
            daily_cost_sek=daily_cost,
            monthly_cost_sek=monthly_cost,
            yearly_cost_sek=yearly_cost,
            heating_cost_daily=heating_cost_daily,
            hot_water_cost_daily=hot_water_cost_daily,
            cop_avg=avg_cop,
            baseline_yearly_cost=baseline_yearly,
            savings_yearly=savings_yearly
        )

    def generate_suggestions(self, hours_back: int = 72) -> List[OptimizationSuggestion]:
        """
        Generate AI-powered optimization suggestions

        Uses Gemini AI if available, otherwise falls back to rule-based system
        """
        # Try Gemini AI first
        if self.use_ai and self.gemini_agent:
            try:
                return self._generate_ai_suggestions(hours_back)
            except Exception as e:
                print(f"AI suggestions failed, falling back to rules: {e}")

        # Fallback to rule-based suggestions
        return self._generate_rule_based_suggestions(hours_back)

    def _generate_ai_suggestions(self, hours_back: int = 72) -> List[OptimizationSuggestion]:
        """Generate suggestions using Gemini AI"""
        from database import SessionLocal, ParameterChange

        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)

        # Get yesterday's metrics for trend analysis
        yesterday_metrics = None
        if hours_back <= 24:
            try:
                yesterday_metrics = self.analyzer.calculate_metrics(
                    hours_back=24,
                    end_offset_hours=24
                )
            except:
                pass

        # Build metrics dict for Gemini
        metrics_dict = {
            'cop': float(metrics.estimated_cop) if metrics.estimated_cop else None,
            'degree_minutes': float(metrics.degree_minutes),
            'delta_t_active': float(metrics.delta_t_active) if metrics.delta_t_active else None,
            'avg_compressor_frequency': float(metrics.avg_compressor_frequency) if metrics.avg_compressor_frequency else None,
            'runtime_hours': float(metrics.heating_metrics.runtime_hours) if metrics.heating_metrics else None,
            'total_energy_in': float(metrics.total_energy_in) if metrics.total_energy_in else None,
            'total_energy_out': float(metrics.total_energy_out) if metrics.total_energy_out else None,
            'room_temp': float(metrics.avg_indoor_temp) if metrics.avg_indoor_temp else None,
            'outdoor_temp': float(metrics.avg_outdoor_temp) if metrics.avg_outdoor_temp else None,
            'supply_temp': float(metrics.avg_supply_temp) if metrics.avg_supply_temp else None,
            'return_temp': float(metrics.avg_return_temp) if metrics.avg_return_temp else None,
        }

        # Add yesterday's metrics if available
        if yesterday_metrics:
            metrics_dict['cop_yesterday'] = float(yesterday_metrics.estimated_cop) if yesterday_metrics.estimated_cop else None
            metrics_dict['degree_minutes_yesterday'] = float(yesterday_metrics.degree_minutes)
            metrics_dict['delta_t_active_yesterday'] = float(yesterday_metrics.delta_t_active) if yesterday_metrics.delta_t_active else None

        # Get recent parameter changes for context
        recent_changes = []
        try:
            db = SessionLocal()
            changes = db.query(ParameterChange).order_by(
                ParameterChange.timestamp.desc()
            ).limit(10).all()

            recent_changes = [{
                'timestamp': c.timestamp.isoformat(),
                'parameter_name': c.parameter_name,
                'old_value': c.old_value,
                'new_value': c.new_value,
                'reason': c.reason
            } for c in changes]

            db.close()
        except:
            pass

        # Get current parameter values (only API-accessible parameters)
        current_parameters = {
            '47011': metrics.curve_offset if metrics.curve_offset else 0,
            # Note: 47007 removed - not accessible via API on F730
        }

        # Call Gemini
        result = self.gemini_agent.analyze_and_recommend(
            metrics=metrics_dict,
            recent_changes=recent_changes,
            current_parameters=current_parameters
        )

        # Convert Gemini recommendations to OptimizationSuggestion format
        suggestions = []
        for rec in result.get('recommendations', []):
            suggestions.append(OptimizationSuggestion(
                priority=rec.get('priority', 'medium'),
                title=rec.get('parameter_name', 'Optimization'),
                description=rec.get('reasoning', ''),
                parameter_name=rec.get('parameter_name', ''),
                parameter_id=rec.get('parameter_id', ''),
                current_value=float(rec.get('current_value', 0)),
                suggested_value=float(rec.get('suggested_value', 0)),
                expected_cop_improvement=0.2,  # Gemini doesn't provide this yet
                expected_savings_yearly=800,  # Estimate
                confidence=float(rec.get('confidence', 0.7)),
                reasoning=rec.get('reasoning', '')
            ))

        return suggestions[:3]  # Return top 3

    def _generate_rule_based_suggestions(self, hours_back: int = 72) -> List[OptimizationSuggestion]:
        """Generate suggestions using rule-based system (fallback)"""
        suggestions = []
        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)

        # Suggestion 1: COP too low - adjust room temp setpoint
        if metrics.estimated_cop and metrics.estimated_cop < 3.0:
            outdoor_temp = metrics.avg_outdoor_temp

            # If it's not extremely cold, we can improve by lowering target temp
            if outdoor_temp > -10 and metrics.avg_indoor_temp > 20.5:
                current_setpoint = metrics.curve_offset if metrics.curve_offset else 21.0
                suggested_setpoint = current_setpoint - 0.5

                suggestions.append(OptimizationSuggestion(
                    priority='high',
                    title='Sänk måltemperaturen för bättre COP',
                    description=f'Din COP är {metrics.estimated_cop:.1f} vilket är lågt. Vid {outdoor_temp:.0f}°C ute och {metrics.avg_indoor_temp:.1f}°C inne kan du sänka måltemperaturen.',
                    parameter_name='Room temp setpoint',
                    parameter_id='47011',
                    current_value=current_setpoint,
                    suggested_value=suggested_setpoint,
                    expected_cop_improvement=0.3,
                    expected_savings_yearly=1200,
                    confidence=0.75,
                    reasoning=f'Lägre måltemperatur → lägre framledningstemp → högre COP. Nuvarande COP {metrics.estimated_cop:.1f} är under målet 3.0.'
                ))

        # Note: Pump speed suggestions removed - parameter 43437 not accessible via API

        # Suggestion 2: Many short cycles - suggest manual check
        if metrics.heating_metrics and metrics.heating_metrics.num_cycles > 20:
            suggestions.append(OptimizationSuggestion(
                priority='high',
                title='För många cykler - kontrollera inställningar',
                description=f'{metrics.heating_metrics.num_cycles} cykler på {hours_back}h är för många. Detta måste justeras manuellt i värmepumpen.',
                parameter_name='Manuell justering krävs',
                parameter_id='0',  # No direct API parameter
                current_value=metrics.heating_metrics.num_cycles,
                suggested_value=15,
                expected_cop_improvement=0.3,
                expected_savings_yearly=1200,
                confidence=0.60,
                reasoning='Kort-cykling sliter på kompressor och sänker COP. Kontrollera pumphastighet och värmekurva manuellt i värmepumpen.'
            ))

        # Suggestion 5: Indoor temp too high
        if metrics.avg_indoor_temp > 22.0:
            current_offset = metrics.curve_offset
            suggested_offset = current_offset - 1

            suggestions.append(OptimizationSuggestion(
                priority='medium',
                title='Sänk kurvjusteringen - för varmt inne',
                description=f'Det är {metrics.avg_indoor_temp:.1f}°C inne. Sänk offset för att spara energi.',
                parameter_name='Kurvjustering',
                parameter_id='47011',
                current_value=current_offset,
                suggested_value=suggested_offset,
                expected_cop_improvement=0.0,
                expected_savings_yearly=600,
                confidence=0.80,
                reasoning='Lägre innetemperatur = lägre framledningstemp = bättre COP + lägre förbrukning.'
            ))

        # Suggestion 6: Indoor temp too low
        elif metrics.avg_indoor_temp < 20.5:
            current_offset = metrics.curve_offset
            suggested_offset = current_offset + 1

            suggestions.append(OptimizationSuggestion(
                priority='high',
                title='Höj kurvjusteringen - för kallt inne',
                description=f'Det är bara {metrics.avg_indoor_temp:.1f}°C inne. Höj offset för bättre komfort.',
                parameter_name='Kurvjustering',
                parameter_id='47011',
                current_value=current_offset,
                suggested_value=suggested_offset,
                expected_cop_improvement=0.0,
                expected_savings_yearly=0,
                confidence=0.90,
                reasoning='Komfort är viktigare än små COP-förbättringar. Målet är 20-22°C.'
            ))

        # Sort by priority and confidence
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        suggestions.sort(key=lambda s: (priority_order[s.priority], -s.confidence))

        return suggestions[:3]  # Return top 3
