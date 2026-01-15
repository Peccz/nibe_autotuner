from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from data.database import Base

class AIEvaluation(Base):
    """
    Stores the "Post-Mortem" analysis of an AI decision.
    Computed 24h after the decision was made.
    """
    __tablename__ = 'ai_evaluations'

    id = Column(Integer, primary_key=True)
    decision_id = Column(Integer, ForeignKey('ai_decision_log.id'), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Outcomes (measured X hours after decision)
    actual_cost_savings = Column(Float)       # Estimated SEK saved
    indoor_temp_deviation = Column(Float)     # Max deviation from target (°C)
    cop_impact = Column(Float)                # Change in COP
    
    # Quality Assessment
    outcome_score = Column(Float)             # -1.0 (Bad) to 1.0 (Good)
    verdict = Column(String(50))              # 'Success', 'Ineffective', 'Counter-productive'
    
    # Learning Data
    observation = Column(Text)                # "Lowered offset before price spike..."
    result_summary = Column(Text)             # "...maintained temp but saved 2 SEK."
    
    # Relationships
    decision = relationship("AIDecisionLog", backref="evaluation")

    def __repr__(self):
        return f"<AIEval(id={self.id}, score={self.outcome_score}, verdict='{self.verdict}')>"

