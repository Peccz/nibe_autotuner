#!/usr/bin/env python3
"""
Database migration script - Add AB Testing tables
"""
from data.models import Base
from data.database import init_db

def migrate():
    """Run database migration"""
    print("Starting database migration...")

    # Initialize database (creates tables if they don't exist)
    engine = init_db('sqlite:///./data/nibe_autotuner.db')

    # Create all tables (will only create new ones)
    Base.metadata.create_all(engine)

    print("✓ Migration complete!")
    print(f"✓ Tables: {', '.join(Base.metadata.tables.keys())}")

if __name__ == '__main__':
    migrate()
