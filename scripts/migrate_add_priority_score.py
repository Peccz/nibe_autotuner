#!/usr/bin/env python3
"""
Database migration: Add priority_score and execution_order to planned_tests table
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import create_engine, text
from loguru import logger

# Database path - check multiple possible locations
possible_paths = [
    os.path.expanduser('~/nibe_autotuner/data/nibe_autotuner.db'),
    os.path.expanduser('~/nibe_autotuner_data/db/nibe_autotuner.db'),
    'data/nibe_autotuner.db'
]

DB_PATH = None
for path in possible_paths:
    if os.path.exists(path):
        DB_PATH = path
        break

if not DB_PATH:
    raise FileNotFoundError(f"Database not found in any of: {possible_paths}")

logger.info(f"Using database: {DB_PATH}")
engine = create_engine(f'sqlite:///{DB_PATH}')

def migrate():
    """Add priority_score and execution_order columns"""
    with engine.connect() as conn:
        try:
            # Check if columns already exist
            result = conn.execute(text("PRAGMA table_info(planned_tests)"))
            columns = [row[1] for row in result]

            if 'priority_score' in columns and 'execution_order' in columns:
                logger.info("✅ Columns already exist, no migration needed")
                return

            # Add priority_score column
            if 'priority_score' not in columns:
                logger.info("Adding priority_score column...")
                conn.execute(text("ALTER TABLE planned_tests ADD COLUMN priority_score REAL DEFAULT 0.0"))
                conn.commit()
                logger.info("✅ priority_score column added")

            # Add execution_order column
            if 'execution_order' not in columns:
                logger.info("Adding execution_order column...")
                conn.execute(text("ALTER TABLE planned_tests ADD COLUMN execution_order INTEGER"))
                conn.commit()
                logger.info("✅ execution_order column added")

            # Calculate and populate priority_score and execution_order for existing tests
            logger.info("Calculating priority scores for existing tests...")

            # Simple priority scoring based on existing priority and confidence
            priority_map = {'high': 70, 'medium': 50, 'low': 30}

            result = conn.execute(text("SELECT id, priority, confidence FROM planned_tests"))
            tests = list(result)

            for test_id, priority, confidence in tests:
                base_score = priority_map.get(priority, 50)
                confidence_bonus = (confidence * 100 * 0.3) if confidence else 0
                priority_score = base_score + confidence_bonus

                conn.execute(
                    text("UPDATE planned_tests SET priority_score = :score WHERE id = :id"),
                    {"score": priority_score, "id": test_id}
                )

            conn.commit()

            # Set execution_order based on priority_score
            result = conn.execute(text(
                "SELECT id FROM planned_tests WHERE status = 'pending' ORDER BY priority_score DESC"
            ))

            for order, (test_id,) in enumerate(result, start=1):
                conn.execute(
                    text("UPDATE planned_tests SET execution_order = :order WHERE id = :id"),
                    {"order": order, "id": test_id}
                )

            conn.commit()
            logger.info(f"✅ Updated {len(tests)} tests with priority scores and execution orders")

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            conn.rollback()
            raise

if __name__ == '__main__':
    logger.info("Starting migration: Add priority_score and execution_order to planned_tests")
    migrate()
    logger.info("✅ Migration complete!")
