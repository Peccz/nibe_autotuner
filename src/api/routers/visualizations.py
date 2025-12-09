from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO

from data.database import get_db
from services.visualizer import HeatPumpVisualizer

router = APIRouter(
    prefix="/visualizations",
    tags=["Visualizations"]
)

@router.get("/{plot_type}")
def get_plot(plot_type: str, db: Session = Depends(get_db)):
    """Generate and return a PNG plot"""
    visualizer = HeatPumpVisualizer(db)
    
    # Map string types to visualizer methods
    plot_map = {
        "main": visualizer.generate_main_plot,
        "cop": visualizer.generate_cop_plot,
        "correlation": visualizer.generate_correlation_plot,
        "hourly": visualizer.generate_hourly_plot
    }
    
    if plot_type not in plot_map:
        raise HTTPException(status_code=400, detail=f"Unknown plot type: {plot_type}")
        
    try:
        # Generate plot buffer
        buf = plot_map[plot_type]()
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plot generation failed: {str(e)}")
