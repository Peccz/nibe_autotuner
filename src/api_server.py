"""
FastAPI Web Server for Nibe Autotuner
Provides REST API for Android app integration
"""
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger

from analyzer import HeatPumpAnalyzer, EfficiencyMetrics, OptimizationOpportunity
from visualizer import HeatPumpVisualizer
from csv_importer import CSVImporter
from models import (
    init_db, Device, Parameter, ParameterReading as ParameterReadingModel,
    Recommendation, ParameterChange
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func, and_


# Initialize FastAPI app
app = FastAPI(
    title="Nibe Autotuner API",
    description="API for heat pump optimization and monitoring",
    version="1.0.0"
)

# Enable CORS for mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your Android app's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database connection
db_path = 'data/nibe_autotuner.db'
database_url = f'sqlite:///./{db_path}'
engine = init_db(database_url)
SessionMaker = sessionmaker(bind=engine)


# Pydantic models for API
class SystemStatus(BaseModel):
    """Current system status"""
    device_name: str
    outdoor_temp: float
    indoor_temp: float
    supply_temp: float
    return_temp: float
    compressor_freq: float
    degree_minutes: float
    heating_curve: float
    curve_offset: float
    estimated_cop: Optional[float]
    last_updated: datetime


class MetricsResponse(BaseModel):
    """Efficiency metrics response"""
    period_start: datetime
    period_end: datetime
    avg_outdoor_temp: float
    avg_indoor_temp: float
    avg_supply_temp: float
    avg_return_temp: float
    delta_t: float
    avg_compressor_freq: float
    degree_minutes: float
    heating_curve: float
    curve_offset: float
    estimated_cop: Optional[float]
    compressor_runtime_hours: Optional[float]


class RecommendationResponse(BaseModel):
    """Optimization recommendation"""
    id: Optional[int]
    parameter_id: str
    parameter_name: str
    current_value: float
    suggested_value: float
    expected_impact: str
    reasoning: str
    confidence: float
    created_at: Optional[datetime]
    status: Optional[str]


class ParameterReading(BaseModel):
    """Single parameter reading"""
    timestamp: datetime
    parameter_id: str
    parameter_name: str
    value: float
    unit: Optional[str]


class ParameterChangeRequest(BaseModel):
    """Request to record a parameter change"""
    parameter_id: str
    old_value: float
    new_value: float
    reason: str
    recommendation_id: Optional[int] = None


# API Endpoints

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "Nibe Autotuner API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/api/status", response_model=SystemStatus)
async def get_system_status():
    """Get current system status"""
    try:
        analyzer = HeatPumpAnalyzer(db_path)
        device = analyzer.get_device()

        # Get latest values
        outdoor = analyzer.get_latest_value(device, analyzer.PARAM_OUTDOOR_TEMP) or 0.0
        indoor = analyzer.get_latest_value(device, analyzer.PARAM_INDOOR_TEMP) or 0.0
        supply = analyzer.get_latest_value(device, analyzer.PARAM_SUPPLY_TEMP) or 0.0
        return_temp = analyzer.get_latest_value(device, analyzer.PARAM_RETURN_TEMP) or 0.0
        compressor = analyzer.get_latest_value(device, analyzer.PARAM_COMPRESSOR_FREQ) or 0.0
        degree_mins = analyzer.get_latest_value(device, analyzer.PARAM_DM_CURRENT) or 0.0
        heating_curve = analyzer.get_latest_value(device, analyzer.PARAM_HEATING_CURVE) or 0.0
        curve_offset = analyzer.get_latest_value(device, analyzer.PARAM_CURVE_OFFSET) or 0.0

        # Estimate COP
        estimated_cop = analyzer._estimate_cop(outdoor, supply, return_temp)

        # Get latest reading timestamp
        session = SessionMaker()
        latest_reading = session.query(func.max(ParameterReadingModel.timestamp)).scalar()
        session.close()

        return SystemStatus(
            device_name=device.product_name,
            outdoor_temp=outdoor,
            indoor_temp=indoor,
            supply_temp=supply,
            return_temp=return_temp,
            compressor_freq=compressor,
            degree_minutes=degree_mins,
            heating_curve=heating_curve,
            curve_offset=curve_offset,
            estimated_cop=estimated_cop,
            last_updated=latest_reading or datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics(hours_back: int = Query(24, ge=1, le=168)):
    """Get efficiency metrics for specified time period"""
    try:
        analyzer = HeatPumpAnalyzer(db_path)
        metrics = analyzer.calculate_metrics(hours_back=hours_back)

        return MetricsResponse(
            period_start=metrics.period_start,
            period_end=metrics.period_end,
            avg_outdoor_temp=metrics.avg_outdoor_temp,
            avg_indoor_temp=metrics.avg_indoor_temp,
            avg_supply_temp=metrics.avg_supply_temp,
            avg_return_temp=metrics.avg_return_temp,
            delta_t=metrics.delta_t,
            avg_compressor_freq=metrics.avg_compressor_freq,
            degree_minutes=metrics.degree_minutes,
            heating_curve=metrics.heating_curve,
            curve_offset=metrics.curve_offset,
            estimated_cop=metrics.estimated_cop,
            compressor_runtime_hours=metrics.compressor_runtime_hours
        )

    except Exception as e:
        logger.error(f"Error calculating metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recommendations", response_model=List[RecommendationResponse])
async def get_recommendations(
    hours_back: int = Query(24, ge=1, le=168),
    min_confidence: float = Query(0.6, ge=0.0, le=1.0),
    include_pending: bool = Query(True)
):
    """Get optimization recommendations"""
    try:
        analyzer = HeatPumpAnalyzer(db_path)

        # Get fresh recommendations
        opportunities = analyzer.generate_recommendations(
            hours_back=hours_back,
            min_confidence=min_confidence
        )

        recommendations = []
        for opp in opportunities:
            recommendations.append(RecommendationResponse(
                id=None,
                parameter_id=opp.parameter_id,
                parameter_name=opp.parameter_name,
                current_value=opp.current_value,
                suggested_value=opp.suggested_value,
                expected_impact=opp.expected_impact,
                reasoning=opp.reasoning,
                confidence=opp.confidence,
                created_at=datetime.utcnow(),
                status='pending'
            ))

        # Optionally include saved pending recommendations from database
        if include_pending:
            session = SessionMaker()
            device = analyzer.get_device()

            saved_recs = session.query(Recommendation).filter(
                and_(
                    Recommendation.device_id == device.id,
                    Recommendation.status == 'pending'
                )
            ).order_by(Recommendation.created_at.desc()).limit(10).all()

            for rec in saved_recs:
                param = session.query(Parameter).get(rec.parameter_id)
                if param:
                    recommendations.append(RecommendationResponse(
                        id=rec.id,
                        parameter_id=param.parameter_id,
                        parameter_name=param.parameter_name,
                        current_value=rec.current_value or 0.0,
                        suggested_value=rec.recommended_value or 0.0,
                        expected_impact=rec.expected_impact or "",
                        reasoning="",
                        confidence=rec.confidence_score or 0.0,
                        created_at=rec.created_at,
                        status=rec.status
                    ))

            session.close()

        return recommendations

    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history/{parameter_id}")
async def get_parameter_history(
    parameter_id: str,
    hours_back: int = Query(24, ge=1, le=720)
):
    """Get historical readings for a specific parameter"""
    try:
        analyzer = HeatPumpAnalyzer(db_path)
        device = analyzer.get_device()

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)

        readings = analyzer.get_readings(device, parameter_id, start_time, end_time)

        return {
            "parameter_id": parameter_id,
            "start_time": start_time,
            "end_time": end_time,
            "count": len(readings),
            "readings": [
                {"timestamp": ts.isoformat(), "value": value}
                for ts, value in readings
            ]
        }

    except Exception as e:
        logger.error(f"Error getting parameter history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/parameters")
async def get_parameters():
    """Get list of all available parameters"""
    try:
        session = SessionMaker()
        params = session.query(Parameter).all()

        result = [
            {
                "parameter_id": p.parameter_id,
                "parameter_name": p.parameter_name,
                "unit": p.parameter_unit,
                "writable": p.writable,
                "min_value": p.min_value,
                "max_value": p.max_value
            }
            for p in params
        ]

        session.close()
        return result

    except Exception as e:
        logger.error(f"Error getting parameters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/parameter-change")
async def record_parameter_change(change: ParameterChangeRequest):
    """Record a manual parameter change"""
    try:
        session = SessionMaker()
        analyzer = HeatPumpAnalyzer(db_path)
        device = analyzer.get_device()

        # Get parameter
        param = session.query(Parameter).filter_by(
            parameter_id=change.parameter_id
        ).first()

        if not param:
            raise HTTPException(status_code=404, detail="Parameter not found")

        # Create parameter change record
        param_change = ParameterChange(
            device_id=device.id,
            parameter_id=param.id,
            timestamp=datetime.utcnow(),
            old_value=change.old_value,
            new_value=change.new_value,
            reason=change.reason,
            applied_by='user',
            recommendation_id=change.recommendation_id
        )

        session.add(param_change)

        # If this was applying a recommendation, update its status
        if change.recommendation_id:
            rec = session.query(Recommendation).get(change.recommendation_id)
            if rec:
                rec.status = 'applied'
                rec.applied_at = datetime.utcnow()

        session.commit()
        session.close()

        return {"success": True, "message": "Parameter change recorded"}

    except Exception as e:
        logger.error(f"Error recording parameter change: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/visualizations/{plot_type}")
async def get_visualization(
    plot_type: str,
    hours_back: int = Query(24, ge=1, le=168)
):
    """
    Get visualization plot

    plot_type: temperature, efficiency, cop, dashboard
    """
    try:
        visualizer = HeatPumpVisualizer()

        # Generate plot based on type
        if plot_type == "temperature":
            file_path = visualizer.plot_temperatures(hours_back=hours_back)
        elif plot_type == "efficiency":
            file_path = visualizer.plot_efficiency(hours_back=hours_back)
        elif plot_type == "cop":
            file_path = visualizer.plot_cop_estimate(hours_back=hours_back)
        elif plot_type == "dashboard":
            file_path = visualizer.create_dashboard(hours_back=hours_back)
        else:
            raise HTTPException(status_code=400, detail="Invalid plot type")

        # Return the image file
        if Path(file_path).exists():
            return FileResponse(file_path, media_type="image/png")
        else:
            raise HTTPException(status_code=500, detail="Failed to generate plot")

    except Exception as e:
        logger.error(f"Error generating visualization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/database-stats")
async def get_database_stats():
    """Get database statistics"""
    try:
        session = SessionMaker()

        total_readings = session.query(func.count(ParameterReadingModel.id)).scalar()
        unique_timestamps = session.query(
            func.count(func.distinct(ParameterReadingModel.timestamp))
        ).scalar()

        first_reading = session.query(func.min(ParameterReadingModel.timestamp)).scalar()
        last_reading = session.query(func.max(ParameterReadingModel.timestamp)).scalar()

        parameter_count = session.query(func.count(Parameter.id)).scalar()
        device_count = session.query(func.count(Device.id)).scalar()

        session.close()

        data_span = None
        if first_reading and last_reading:
            data_span = (last_reading - first_reading).total_seconds() / 3600  # hours

        return {
            "total_readings": total_readings,
            "unique_timestamps": unique_timestamps,
            "parameter_count": parameter_count,
            "device_count": device_count,
            "first_reading": first_reading.isoformat() if first_reading else None,
            "last_reading": last_reading.isoformat() if last_reading else None,
            "data_span_hours": data_span
        }

    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Run server
if __name__ == "__main__":
    import uvicorn

    logger.info("="*80)
    logger.info("STARTING NIBE AUTOTUNER API SERVER")
    logger.info("="*80)
    logger.info("")
    logger.info("API Documentation: http://localhost:8000/docs")
    logger.info("API Base URL:      http://localhost:8000/api")
    logger.info("")
    logger.info("Available Endpoints:")
    logger.info("  GET  /api/status           - Current system status")
    logger.info("  GET  /api/metrics          - Efficiency metrics")
    logger.info("  GET  /api/recommendations  - Optimization recommendations")
    logger.info("  GET  /api/history/{param}  - Parameter history")
    logger.info("  GET  /api/parameters       - List all parameters")
    logger.info("  POST /api/parameter-change - Record parameter change")
    logger.info("  GET  /api/visualizations/* - Get plots (temperature/efficiency/cop/dashboard)")
    logger.info("  GET  /api/database-stats   - Database statistics")
    logger.info("")
    logger.info("="*80)

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
