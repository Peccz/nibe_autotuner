from datetime import datetime
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine, desc
from loguru import logger

from data.models import (
    Device,
    Parameter,
    ParameterReading,
    Recommendation,
    HeatingMetrics,
    HotWaterMetrics,
    EfficiencyMetrics,
    COPModel,
    ABTestResult,
)
