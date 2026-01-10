import sys
import os
import sqlite3
from loguru import logger

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def migrate():
    logger.info("Migrating to Full Zone Separation...")
    
    db_path = 'data/nibe_autotuner.db'
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 1. Fetch current base values to use as defaults
    defaults = {
        'wind_sensitivity': 0.01,
        'solar_gain_coeff': 0.04,
        'internal_heat_gain': 0.015
    }
    
    current = {}
    try:
        c.execute("SELECT parameter_id, value FROM system_tuning")
        for row in c.fetchall():
            current[row[0]] = row[1]
    except Exception:
        pass

    # 2. Define new parameters (Defaults = Current Base Values)
    new_params = [
        ('wind_sensitivity_dexter', current.get('wind_sensitivity', defaults['wind_sensitivity']), 'Wind impact on Dexter room'),
        ('solar_gain_dexter', current.get('solar_gain_coeff', defaults['solar_gain_coeff']), 'Solar gain coefficient for Dexter'),
        ('internal_gain_dexter', current.get('internal_heat_gain', defaults['internal_heat_gain']), 'Internal heat gain in Dexter room')
    ]
    
    # 3. Insert if missing
    try:
        for pid, val, desc in new_params:
            c.execute("INSERT OR IGNORE INTO system_tuning (parameter_id, value, description) VALUES (?, ?, ?)", (pid, val, desc))
            logger.info(f"Added parameter: {pid} = {val}")
            
        conn.commit()
        logger.info("Migration completed successfully.")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
