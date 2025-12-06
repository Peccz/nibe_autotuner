"""
Database configuration and session management

This module provides centralized database configuration including:
- SQLAlchemy engine creation
- Session factory
- Declarative base for models
- FastAPI dependency for database sessions
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from core.config import settings

# ============================================================================
# Database Engine
# ============================================================================

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
    echo=False  # Set to True for SQL query logging during development
)

# ============================================================================
# Session Factory
# ============================================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ============================================================================
# Declarative Base
# ============================================================================

Base = declarative_base()

# ============================================================================
# Database Dependency for FastAPI
# ============================================================================

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Usage in FastAPI routes:
        @app.get("/items/")
        def read_items(db: Session = Depends(get_db)):
            items = db.query(Item).all()
            return items

    Yields:
        Session: SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# Database Initialization
# ============================================================================

def init_db():
    """
    Initialize database by creating all tables.

    Should be called once when the application starts.
    Note: In production, use a migration tool like Alembic instead.
    """
        # Import all models to ensure they're registered with Base                                                                                                 
        from data.models import (System, Device, Parameter, ParameterReading, ParameterChange, AIDecisionLog, Recommendation, PlannedTest, ABTestResult)           
        from data.evaluation_model import AIEvaluation
                                                                                                                                                                   
        Base.metadata.create_all(bind=engine)

def get_session() -> Session:
    """
    Get a new database session.

    IMPORTANT: Caller is responsible for closing the session.
    Prefer using get_db() dependency in FastAPI routes.

    Returns:
        Session: SQLAlchemy database session
    """
    return SessionLocal()
