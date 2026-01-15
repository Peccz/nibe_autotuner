import sys
import os
import sqlite3
from loguru import logger

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def migrate():
    logger.info("Adding separate thermal leakage for Dexter...")
    
    db_path = 'data/nibe_autotuner.db'
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    try:
        # Get current base leakage
        c.execute("SELECT value FROM system_tuning WHERE parameter_id = 'thermal_leakage'")
        res = c.fetchone()
        base_leakage = res[0] if res else 0.009
        
        # Calculate default for Dexter (1.3x base)
        dexter_leakage = base_leakage * 1.3
        
        # Insert new parameter
        c.execute("INSERT OR IGNORE INTO system_tuning (parameter_id, value, description) VALUES (?, ?, ?)", 
                  ('thermal_leakage_dexter', dexter_leakage, 'Specific heat loss rate for Dexter room'))
            
        conn.commit()
        logger.info(f"Migration completed. Added thermal_leakage_dexter={dexter_leakage:.4f}")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()

