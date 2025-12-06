"""
AI Evaluator Service
Analyzes past AI decisions to determine their effectiveness.
"""
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger
from sqlalchemy.orm import Session

from data.database import SessionLocal
from data.models import AIDecisionLog, ParameterReading, ParameterChange
from data.evaluation_model import AIEvaluation
from services.analyzer import HeatPumpAnalyzer

class AIEvaluator:
    def __init__(self):
        self.session = SessionLocal()
        self.analyzer = HeatPumpAnalyzer()

    def run_daily_evaluation(self):
        """Evaluate pending decisions older than 6 hours"""
        logger.info("Starting AI Decision Evaluation...")
        
        # Find unevaluated decisions older than 6h (to allow time for effect)
        cutoff_time = datetime.utcnow() - timedelta(hours=6)
        
        # Get decisions that don't have an evaluation yet
        # (This implies a LEFT JOIN logic or simple check)
        # Using simple iteration for clarity and SQLite compatibility
        decisions = self.session.query(AIDecisionLog).filter(
            AIDecisionLog.timestamp < cutoff_time
        ).order_by(AIDecisionLog.timestamp.desc()).limit(50).all()

        evaluated_count = 0
        
        for decision in decisions:
            # Check if already evaluated
            existing = self.session.query(AIEvaluation).filter_by(decision_id=decision.id).first()
            if existing:
                continue
                
            logger.info(f"Evaluating decision {decision.id}: {decision.action} {decision.parameter}")
            self._evaluate_single_decision(decision)
            evaluated_count += 1
            
        logger.info(f"Evaluation complete. Processed {evaluated_count} decisions.")

    def _evaluate_single_decision(self, decision: AIDecisionLog):
        """
        Analyze the outcome of a single decision.
        """
        if decision.action == 'hold':
            # Holds are harder to evaluate, simplistic check for now
            self._record_evaluation(decision, score=0.0, verdict="Neutral", summary="Hold action - no change to evaluate")
            return

        # Time window for evaluation (next 4 hours)
        start_time = decision.timestamp
        end_time = start_time + timedelta(hours=4)
        
        # 1. Check Indoor Temperature Impact
        # Did it go out of bounds?
        avg_indoor = self.analyzer.calculate_average(
            self.analyzer.get_device(), 
            self.analyzer.PARAM_INDOOR_TEMP, 
            start_time, 
            end_time
        )
        
        temp_score = 0.0
        verdict = "Neutral"
        summary = ""
        
        if avg_indoor:
            if avg_indoor < 20.0:
                temp_score = -0.5
                summary += "Resulted in low indoor temp (<20C). "
            elif avg_indoor > 22.5:
                temp_score = -0.2
                summary += "Resulted in high indoor temp (>22.5C). "
            else:
                temp_score = 0.2
                summary += "Maintained comfort. "
                
        # 2. Check Cost/COP Impact (Simplified)
        # Did we shift consumption?
        # This requires more complex logic, for now we assume if 'adjust' was made and temp is OK, it's a success.
        
        final_score = 0.5 + temp_score # Baseline 0.5 for taking action
        
        if final_score > 0.8:
            verdict = "Success"
        elif final_score < 0.0:
            verdict = "Counter-productive"
        else:
            verdict = "Acceptable"
            
        self._record_evaluation(
            decision,
            score=final_score,
            verdict=verdict,
            summary=summary,
            indoor_dev=0.0 # TODO: Calculate actual deviation
        )

    def _record_evaluation(self, decision, score, verdict, summary, indoor_dev=0.0):
        eval_entry = AIEvaluation(
            decision_id=decision.id,
            outcome_score=score,
            verdict=verdict,
            result_summary=summary,
            indoor_temp_deviation=indoor_dev
        )
        self.session.add(eval_entry)
        self.session.commit()
        logger.info(f"  -> Verdict: {verdict} (Score: {score})")

if __name__ == "__main__":
    evaluator = AIEvaluator()
    evaluator.run_daily_evaluation()
