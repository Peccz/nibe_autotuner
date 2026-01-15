import sys
import os
import sqlite3
from loguru import logger

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def migrate():
    logger.info("Adding Weather Parameters to Database...")
    
    db_path = 'data/nibe_autotuner.db'
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    params = [
        ('EXT_WIND_SPEED', 'Wind Speed (SMHI)', 'm/s', 'External Weather', 0),
        ('EXT_WIND_DIRECTION', 'Wind Direction (SMHI)', 'deg', 'External Weather', 0)
    ]
    
    try:
        for pid, name, unit, cat, writable in params:
            # Check if exists
            c.execute("SELECT id FROM parameters WHERE parameter_id = ?", (pid,))
            if c.fetchone():
                logger.info(f"Parameter {pid} already exists.")
            else:
                c.execute("""
                    INSERT INTO parameters (parameter_id, parameter_name, parameter_unit, category, writable, created_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                """, (pid, name, unit, cat, writable))
                logger.info(f"Added parameter: {pid}")
            
        conn.commit()
        logger.info("Migration completed successfully.")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()

