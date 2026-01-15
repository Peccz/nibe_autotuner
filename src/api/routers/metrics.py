from fastapi import APIRouter, Depends
from services.analyzer import HeatPumpAnalyzer

router = APIRouter()

@router.get("/metrics")
def get_metrics():
    try:
        analyzer = HeatPumpAnalyzer()
        metrics = analyzer.calculate_metrics(hours=24)
        return {
            "cop": metrics.cop,
            "avg_indoor_temp": metrics.avg_indoor_temp,
            "total_energy_kwh": metrics.total_energy_kwh,
            "degree_minutes": metrics.degree_minutes
        }
    except Exception as e:
        return {"error": str(e)}

