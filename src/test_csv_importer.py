"""
Test CSV importer with sample data
"""
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger
from data.csv_importer import CSVImporter


def create_sample_csv():
    """Create a sample CSV file for testing"""
    sample_file = 'data/sample_import.csv'

    logger.info(f"Creating sample CSV: {sample_file}")

    # Create sample data
    with open(sample_file, 'w') as f:
        f.write("Timestamp,Parameter ID,Parameter Name,Value,Unit\n")

        # Generate 24 hours of sample data (every hour)
        base_time = datetime(2025, 11, 20, 0, 0, 0)

        for hour in range(24):
            timestamp = base_time + timedelta(hours=hour)
            ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')

            # Outdoor temperature (varying)
            outdoor_temp = 2.0 + (hour % 12) * 0.5
            f.write(f"{ts_str},40004,Outdoor Temperature,{outdoor_temp:.1f},°C\n")

            # Supply temperature
            supply_temp = 35.0 + (hour % 12) * 0.3
            f.write(f"{ts_str},40008,Supply Temperature,{supply_temp:.1f},°C\n")

            # Return temperature
            return_temp = supply_temp - 5.0
            f.write(f"{ts_str},40012,Return Temperature,{return_temp:.1f},°C\n")

            # Indoor temperature (relatively stable)
            indoor_temp = 20.5 + ((hour % 24) - 12) * 0.1
            f.write(f"{ts_str},13,Indoor Temperature,{indoor_temp:.1f},°C\n")

    logger.info(f"✅ Sample CSV created with {24 * 4} readings")
    return sample_file


def test_import():
    """Test importing the sample CSV"""
    logger.info("="*80)
    logger.info("TESTING CSV IMPORTER")
    logger.info("="*80 + "\n")

    # Create sample CSV
    sample_file = create_sample_csv()

    # Import it
    importer = CSVImporter()

    logger.info(f"\nImporting {sample_file}...")
    stats = importer.import_myuplink_csv(sample_file)

    logger.info("\n" + "="*80)
    logger.info("TEST RESULTS")
    logger.info("="*80)

    if stats['imported'] > 0:
        logger.info(f"✅ Successfully imported {stats['imported']} readings")
    else:
        logger.warning("⚠️  No readings were imported")

    if stats['skipped_duplicates'] > 0:
        logger.info(f"ℹ️  Skipped {stats['skipped_duplicates']} duplicate readings")

    if stats['errors'] > 0:
        logger.warning(f"⚠️  {stats['errors']} errors occurred during import")

    # Test export
    logger.info("\nTesting export...")
    export_file = 'data/test_export.csv'
    importer.export_to_csv(
        export_file,
        start_date=datetime(2025, 11, 20, 0, 0, 0),
        end_date=datetime(2025, 11, 20, 23, 59, 59)
    )

    # Verify export file exists
    if Path(export_file).exists():
        with open(export_file, 'r') as f:
            lines = f.readlines()
            logger.info(f"✅ Export file created with {len(lines)-1} readings")
            logger.info(f"\nFirst few lines of export:")
            for line in lines[:5]:
                logger.info(f"  {line.strip()}")
    else:
        logger.error("❌ Export file was not created")

    logger.info("\n" + "="*80)
    logger.info("CSV IMPORTER TEST COMPLETE")
    logger.info("="*80)


if __name__ == '__main__':
    test_import()
