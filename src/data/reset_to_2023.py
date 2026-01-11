import sys
import os
import sqlite3
from loguru import logger

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def reset_physics():
    logger.info("Resetting Physics Model to 'Modern House 2023' Standard...")
    
    db_path = 'data/nibe_autotuner.db'
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # New Baseline Parameters
    params = {
        # Insulation (Very good, 2023 standard)
        'thermal_leakage': 0.003, 
        'thermal_leakage_dexter': 0.0035, # Slightly higher due to roof?
        
        # Emitters (High efficiency to work with low temps)
        'slab_efficiency': 0.04, 
        'rad_efficiency': 0.03,
        
        # Internal Logic
        'inter_zone_transfer': 0.005, # Heat rising from downstairs
        'actual_shunt_limit': 29.0,   # Proven limit
        
        # Environment (Parhus = Less solar)
        'solar_gain_coeff': 0.02,
        'solar_gain_dexter': 0.02,
        
        # Wind (Modern tightness = less sensitivity)
        'wind_sensitivity': 0.005,
        'wind_sensitivity_dexter': 0.005,
        'wind_direction_west_factor': 1.1 # Reduced impact
    }
    
    try:
        for pid, val in params.items():
            # Update existing or insert new
            c.execute("INSERT OR REPLACE INTO system_tuning (parameter_id, value, description) VALUES (?, ?, ?)", 
                      (pid, val, 'Reset to 2023 Standard'))
            logger.info(f"  Set {pid} = {val}")
            
        conn.commit()
        logger.info("Physics reset complete.")
        
    except Exception as e:
        logger.error(f"Reset failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    reset_physics()
