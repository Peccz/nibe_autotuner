#!/usr/bin/env python3
"""
Database Migration: Add user settings columns to Device table

This script adds the following columns to the devices table:
- min_indoor_temp_user_setting (Float, default 20.5)
- target_indoor_temp_min (Float, default 20.5)
- target_indoor_temp_max (Float, default 22.0)

Usage:
    python src/data/migrate_add_user_settings.py

IMPORTANT: This is a simple SQLite migration. For production systems with
multiple database types, consider using Alembic or similar migration tools.
"""

import sqlite3
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from loguru import logger


def migrate_database(db_path: str = "data/nibe_autotuner.db"):
    """Add user settings columns to Device table"""

    logger.info("=" * 80)
    logger.info("Database Migration: Add User Settings to Device Table")
    logger.info("=" * 80)

    # Check if database exists
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        return False

    conn = None
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        logger.info(f"Connected to database: {db_path}")

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(devices)")
        columns = {row[1] for row in cursor.fetchall()}

        logger.info(f"Current device table columns: {', '.join(sorted(columns))}")

        # Add columns if they don't exist
        migrations_needed = []

        if 'min_indoor_temp_user_setting' not in columns:
            migrations_needed.append(
                "ALTER TABLE devices ADD COLUMN min_indoor_temp_user_setting REAL DEFAULT 20.5 NOT NULL"
            )
            logger.info("  → Will add: min_indoor_temp_user_setting")

        if 'target_indoor_temp_min' not in columns:
            migrations_needed.append(
                "ALTER TABLE devices ADD COLUMN target_indoor_temp_min REAL DEFAULT 20.5 NOT NULL"
            )
            logger.info("  → Will add: target_indoor_temp_min")

        if 'target_indoor_temp_max' not in columns:
            migrations_needed.append(
                "ALTER TABLE devices ADD COLUMN target_indoor_temp_max REAL DEFAULT 22.0 NOT NULL"
            )
            logger.info("  → Will add: target_indoor_temp_max")

        if not migrations_needed:
            logger.info("✓ All columns already exist - no migration needed")
            return True

        # Execute migrations
        logger.info(f"\nExecuting {len(migrations_needed)} migration(s)...")
        for i, sql in enumerate(migrations_needed, 1):
            logger.info(f"  {i}. {sql}")
            cursor.execute(sql)

        # Commit changes
        conn.commit()

        logger.info("\n✓ Migration completed successfully!")

        # Verify columns were added
        cursor.execute("PRAGMA table_info(devices)")
        new_columns = {row[1] for row in cursor.fetchall()}

        logger.info(f"\nUpdated device table columns: {', '.join(sorted(new_columns))}")

        # Show current values for all devices
        cursor.execute("""
            SELECT
                device_id,
                product_name,
                min_indoor_temp_user_setting,
                target_indoor_temp_min,
                target_indoor_temp_max
            FROM devices
        """)

        devices = cursor.fetchall()
        if devices:
            logger.info("\nCurrent settings for devices:")
            for device_id, product_name, min_temp, target_min, target_max in devices:
                logger.info(f"  {product_name} ({device_id}):")
                logger.info(f"    Min Indoor Temp:  {min_temp:.1f}°C")
                logger.info(f"    Target Range:     {target_min:.1f}-{target_max:.1f}°C")

        return True

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        if conn:
            conn.rollback()
        return False

    finally:
        if conn:
            conn.close()
            logger.info("\nDatabase connection closed")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Migrate database to add user settings')
    parser.add_argument(
        '--db',
        default='data/nibe_autotuner.db',
        help='Path to SQLite database (default: data/nibe_autotuner.db)'
    )

    args = parser.parse_args()

    success = migrate_database(args.db)

    if success:
        logger.info("\n" + "=" * 80)
        logger.info("Migration completed successfully!")
        logger.info("=" * 80)
        sys.exit(0)
    else:
        logger.error("\n" + "=" * 80)
        logger.error("Migration failed!")
        logger.error("=" * 80)
        sys.exit(1)
