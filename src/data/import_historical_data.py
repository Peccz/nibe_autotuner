"""
Import all historical CSV files from data_input directory
"""
import os
import re
from pathlib import Path
from datetime import datetime
from loguru import logger
from data.csv_importer import CSVImporter
from data.models import init_db, Device, Parameter, ParameterReading as ParameterReadingModel
from sqlalchemy.orm import sessionmaker
from sqlalchemy import and_


def parse_myuplink_csv(csv_path: str):
    """
    Parse myUplink CSV format:
    - Semicolon separated
    - Header: timestamp;[Parameter Name][Unit][ParameterID];
    - Data: timestamp;value;
    """
    logger.info(f"Parsing {csv_path}")

    with open(csv_path, 'r', encoding='utf-8') as f:
        # Read header
        header = f.readline().strip()

        # Extract parameter info from header
        # Format: timestamp;[Parameter Name][Unit][ParameterID];
        match = re.search(r'\[(.*?)\]\[(.*?)\]\[(\d+)\]', header)

        if not match:
            logger.warning(f"Could not parse header: {header}")
            return None, None, None, []

        param_name = match.group(1)
        param_unit = match.group(2)
        param_id = match.group(3)

        # Read data rows
        readings = []
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split(';')
            if len(parts) < 2:
                continue

            timestamp_str = parts[0]
            value_str = parts[1]

            if not timestamp_str or not value_str:
                continue

            try:
                # Parse ISO 8601 timestamp
                timestamp = datetime.fromisoformat(timestamp_str.replace('+00:00', '+00:00'))
                # Convert to naive UTC for database
                timestamp = timestamp.replace(tzinfo=None)

                value = float(value_str)
                readings.append((timestamp, value))
            except (ValueError, IndexError) as e:
                logger.debug(f"Skipping invalid line: {line} - {e}")
                continue

        logger.info(f"  Parameter: {param_name} ({param_id})")
        logger.info(f"  Unit: {param_unit}")
        logger.info(f"  Readings: {len(readings)}")

        return param_id, param_name, param_unit, readings


def import_all_csv_files(data_input_dir: str = './data_input'):
    """Import all CSV files from data_input directory"""

    # Initialize database connection
    db_path = 'data/nibe_autotuner.db'
    database_url = f'sqlite:///./{db_path}'
    engine = init_db(database_url)
    SessionMaker = sessionmaker(bind=engine)
    session = SessionMaker()

    # Get device
    device = session.query(Device).first()
    if not device:
        logger.error("No device found in database. Run data logger first.")
        return

    # Get all CSV files
    csv_files = sorted(Path(data_input_dir).glob('*.csv'))

    logger.info("="*80)
    logger.info("IMPORTING HISTORICAL DATA FROM MYUPLINK")
    logger.info("="*80)
    logger.info(f"Found {len(csv_files)} CSV files")
    logger.info("")

    total_stats = {
        'files_processed': 0,
        'files_skipped': 0,
        'total_readings': 0,
        'imported': 0,
        'skipped_duplicates': 0,
        'errors': 0
    }

    # Process each file
    for csv_file in csv_files:
        try:
            param_id, param_name, param_unit, readings = parse_myuplink_csv(str(csv_file))

            if not readings:
                logger.warning(f"No readings found in {csv_file.name}")
                total_stats['files_skipped'] += 1
                continue

            total_stats['files_processed'] += 1
            total_stats['total_readings'] += len(readings)

            # Get or create parameter
            param = session.query(Parameter).filter_by(parameter_id=param_id).first()

            if not param:
                logger.info(f"  Creating new parameter: {param_id} - {param_name}")
                param = Parameter(
                    parameter_id=param_id,
                    parameter_name=param_name,
                    parameter_unit=param_unit,
                    writable=False
                )
                session.add(param)
                session.commit()

            # Import readings
            imported_count = 0
            duplicate_count = 0

            for timestamp, value in readings:
                # Check if reading already exists
                exists = session.query(ParameterReadingModel).filter(
                    and_(
                        ParameterReadingModel.device_id == device.id,
                        ParameterReadingModel.parameter_id == param.id,
                        ParameterReadingModel.timestamp == timestamp
                    )
                ).first() is not None

                if exists:
                    duplicate_count += 1
                    continue

                # Create reading
                reading = ParameterReadingModel(
                    device_id=device.id,
                    parameter_id=param.id,
                    timestamp=timestamp,
                    value=value
                )
                session.add(reading)
                imported_count += 1

                # Commit in batches
                if imported_count % 500 == 0:
                    session.commit()

            # Final commit for this file
            session.commit()

            total_stats['imported'] += imported_count
            total_stats['skipped_duplicates'] += duplicate_count

            logger.info(f"  ✅ Imported: {imported_count}, Skipped: {duplicate_count}")
            logger.info("")

        except Exception as e:
            logger.error(f"Error processing {csv_file.name}: {e}")
            total_stats['errors'] += 1
            continue

    session.close()

    # Print summary
    logger.info("="*80)
    logger.info("IMPORT COMPLETE")
    logger.info("="*80)
    logger.info(f"Files processed:    {total_stats['files_processed']}")
    logger.info(f"Files skipped:      {total_stats['files_skipped']}")
    logger.info(f"Total readings:     {total_stats['total_readings']}")
    logger.info(f"Imported:           {total_stats['imported']}")
    logger.info(f"Skipped duplicates: {total_stats['skipped_duplicates']}")
    logger.info(f"Errors:             {total_stats['errors']}")
    logger.info("")

    # Show data span
    session = SessionMaker()
    from sqlalchemy import func

    first_reading = session.query(func.min(ParameterReadingModel.timestamp)).scalar()
    last_reading = session.query(func.max(ParameterReadingModel.timestamp)).scalar()
    total_readings_db = session.query(func.count(ParameterReadingModel.id)).scalar()
    unique_timestamps = session.query(func.count(func.distinct(ParameterReadingModel.timestamp))).scalar()

    session.close()

    if first_reading and last_reading:
        duration = last_reading - first_reading
        days = duration.total_seconds() / 86400

        logger.info("DATABASE SUMMARY")
        logger.info("="*80)
        logger.info(f"Total readings in DB: {total_readings_db:,}")
        logger.info(f"Unique timestamps:    {unique_timestamps:,}")
        logger.info(f"First reading:        {first_reading}")
        logger.info(f"Last reading:         {last_reading}")
        logger.info(f"Data span:            {days:.1f} days ({duration})")
        logger.info("")
        logger.info("✅ Ready for analysis!")


if __name__ == '__main__':
    import_all_csv_files()
