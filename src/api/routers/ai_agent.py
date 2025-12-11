from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
from typing import List, Optional
from loguru import logger

from data.database import get_db
# VIKTIGT: Vi importerar AIDecisionLog (gammal data) men aliasar den till AIDecision
from data.models import AIDecisionLog as AIDecision, ABTest

router = APIRouter()

@router.get("/status", tags=["AI Agent"])
def get_agent_status(db: Session = Depends(get_db)):
    """Hämtar status för när AI-agenten senast körde."""
    last_decision = db.query(AIDecision).order_by(AIDecision.timestamp.desc()).first()
    
    status = "unknown"
    last_run = None
    
    if last_decision:
        last_run = last_decision.timestamp
        # Om den körde inom senaste 90 min räknar vi den som active
        if last_run > datetime.utcnow() - timedelta(minutes=90):
            status = "active"
        else:
            status = "idle"

    return {
        "status": status,
        "last_run": last_run,
        "model_used": getattr(last_decision, 'model_used', 'Gemini Flash (Legacy)')
    }

@router.get("/latest-decision", tags=["AI Agent"])
def get_latest_decision(db: Session = Depends(get_db)):
    """Hämtar det absolut senaste beslutet."""
    decision = db.query(AIDecision).order_by(AIDecision.timestamp.desc()).first()
    if not decision:
        return None
    
    decision_dict = decision.__dict__.copy()
    if 'model_used' not in decision_dict:
        decision_dict['model_used'] = 'Gemini Flash (Legacy)'
    decision_dict.pop('_sa_instance_state', None)
    return decision_dict

@router.get("/history", tags=["AI Agent"])
def get_decision_history(limit: int = 24, db: Session = Depends(get_db)):
    """Hämtar historik över beslut."""
    decisions = db.query(AIDecision).order_by(AIDecision.timestamp.desc()).limit(limit).all()
    return decisions

# --- A/B Test Endpoints ---

@router.get("/active-tests", tags=["AB Testing"])
def get_active_tests(db: Session = Depends(get_db)):
    """Hämtar aktiva A/B-tester (end_time är NULL)."""
    try:
        return db.query(ABTest).filter(ABTest.end_time.is_(None)).all()
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_active_tests: {e}")
        return []

@router.get("/planned-tests", tags=["AB Testing"])
def get_planned_tests(db: Session = Depends(get_db)):
    return []

@router.get("/completed-tests", tags=["AB Testing"])
def get_completed_tests(limit: int = 10, db: Session = Depends(get_db)):
    """Hämtar avslutade A/B-tester (end_time är NOT NULL)."""
    try:
        return db.query(ABTest).filter(ABTest.end_time.isnot(None)).order_by(ABTest.end_time.desc()).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_completed_tests: {e}")
        return []

@router.get("/learning-stats", tags=["AB Testing"])
def get_learning_stats(db: Session = Depends(get_db)):
    """Hämtar statistik om A/B-testning."""
    try:
        count = db.query(ABTest).count()
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_learning_stats: {e}")
        count = 0
    return {
        "total_tests_run": count,
        "insights_generated": 0
    }
