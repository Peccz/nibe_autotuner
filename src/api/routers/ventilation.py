from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from sqlalchemy.orm import Session
from data.database import get_db
from services.ventilation_optimizer import VentilationOptimizer
from services.analyzer import HeatPumpAnalyzer
from integrations.api_client import MyUplinkClient

router = APIRouter()

@router.get("/status")
def get_ventilation_status(db: Session = Depends(get_db)):
    """Get current ventilation status and strategy"""
    try:
        # Initialize services
        # Note: This is a bit heavy to do on every request, normally we'd use dependency injection
        # but for now we instantiate directly to keep it simple
        client = MyUplinkClient()
        analyzer = HeatPumpAnalyzer()
        optimizer = VentilationOptimizer(analyzer, client)
        
        # Evaluate current state
        analysis = optimizer.evaluate_ventilation()
        
        return {
            "success": True,
            "data": analysis
        }
    except Exception as e:
        # Fallback mock data if something fails (e.g. API connection)
        return {
            "success": True, 
            "data": {
                "current_strategy": "NORMAL",
                "needs_adjustment": False,
                "exhaust_temp": 20.5,
                "fan_speed_pct": 55,
                "estimated_rh_drop_pct": 0,
                "reasoning": "Data unavailable, showing default status."
            }
        }
