from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

from data.database import get_db
from data.models import Parameter, Device
from integrations.api_client import MyUplinkClient
from api.schemas import ParameterChangeRequest, APIResponse

router = APIRouter(
    prefix="/parameters",
    tags=["Parameters & Control"]
)

@router.get("", response_model=List[dict])
def get_parameters(db: Session = Depends(get_db)):
    """Get list of all monitored parameters"""
    params = db.query(Parameter).all()
    return [
        {
            "id": p.parameter_id,
            "name": p.parameter_name,
            "title": p.title,
            "unit": p.unit
        }
        for p in params
    ]

@router.post("/change", response_model=APIResponse)
def change_parameter(
    request: ParameterChangeRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Manually change a parameter value (ASYNC)"""
    # Verify device exists
    device = db.query(Device).first()
    if not device:
        raise HTTPException(status_code=404, detail="No device configured")

    # Initialize client
    try:
        client = MyUplinkClient()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to init API client: {str(e)}")

    # Define the task function
    def _do_change(dev_id, param_id, val):
        client.set_point_value(dev_id, param_id, val)

    # Add to background tasks (so API responds immediately)
    background_tasks.add_task(
        _do_change, 
        device.device_id, 
        request.parameter_id, 
        request.value
    )

    return {
        "success": True, 
        "message": f"Queued change for {request.parameter_id} to {request.value}"
    }
