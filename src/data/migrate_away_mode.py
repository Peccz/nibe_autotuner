import sys
import os
# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import engine
from loguru import logger
import sqlite3

def migrate():
    logger.info("Migrating database: Adding 'away_mode' columns to 'devices'...")
    
    # We use raw SQL because adding columns to existing table in SQLite with SQLAlchemy is tricky
    # and we want to avoid data loss.
    
    db_path = 'data/nibe_autotuner.db'
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    try:
        # Add away_mode_enabled
        try:
            c.execute("ALTER TABLE devices ADD COLUMN away_mode_enabled BOOLEAN DEFAULT 0")
            logger.info("Added column: away_mode_enabled")
        except sqlite3.OperationalError as e:
            logger.info(f"Column away_mode_enabled likely exists: {e}")

        # Add away_mode_end_date
        try:
            c.execute("ALTER TABLE devices ADD COLUMN away_mode_end_date DATETIME")
            logger.info("Added column: away_mode_end_date")
        except sqlite3.OperationalError as e:
            logger.info(f"Column away_mode_end_date likely exists: {e}")
            
        conn.commit()
        logger.info("Migration completed successfully.")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
