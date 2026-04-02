"""
Migration: Add target_radiator_temp to devices table.

Enables per-device zone priority: setting target_radiator_temp > target_indoor_temp_max
causes the optimizer to keep higher offsets (→ higher supply temp → radiator boost),
effectively prioritizing upper floors over ground floor and vice versa.
"""
import sys
import os
import sqlite3
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate():
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'data', 'nibe_autotuner.db'
    )
    conn = sqlite3.connect(db_path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(devices)").fetchall()]
        if 'target_radiator_temp' not in cols:
            conn.execute("ALTER TABLE devices ADD COLUMN target_radiator_temp REAL DEFAULT 21.0")
            conn.commit()
            logger.success("Added target_radiator_temp to devices (default 21.0°C)")
        else:
            logger.info("target_radiator_temp already exists, skipping")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
