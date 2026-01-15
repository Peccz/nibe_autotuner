import sys
import os
# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import engine, Base
from data.models import LearningEvent
from loguru import logger

def migrate():
    logger.info("Migrating database: Creating 'learning_events' table...")
    try:
        # Create the table if it doesn't exist
        LearningEvent.__table__.create(bind=engine)
        logger.info("✓ Table 'learning_events' created successfully.")
    except Exception as e:
        if "already exists" in str(e):
            logger.info("Table already exists. Skipping.")
        else:
            logger.error(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
