"""
CSV Data Importer
Import historical heat pump data from CSV files (e.g., exported from myUplink web)
"""
import csv
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
import pandas as pd
from loguru import logger
from sqlalchemy import and_

from data.models import Device, Parameter, ParameterReading
from data.database import init_db
from sqlalchemy.orm import sessionmaker


class CSVImporter:
    """Import historical heat pump data from CSV files"""

    def __init__(self, db_path: str = 'data/nibe_autotuner.db'):
        """Initialize importer with database connection"""
        self.db_path = db_path
        database_url = f'sqlite:///./{db_path}'
        self.engine = init_db(database_url)
        SessionMaker = sessionmaker(bind=self.engine)
        self.session = SessionMaker()

    def __del__(self):
        """Clean up database connection"""
        if hasattr(self, 'session'):
            self.session.close()

    def get_device(self) -> Device:
        """Get the first (and typically only) device"""
        device = self.session.query(Device).first()
        if not device:
            raise ValueError("No device found in database. Run data logger first to initialize.")
        return device

    def get_or_create_parameter(
        self,
        parameter_id: str,
        parameter_name: str,
        parameter_unit: Optional[str] = None
    ) -> Parameter:
        """Get existing parameter or create new one"""
        param = self.session.query(Parameter).filter_by(parameter_id=parameter_id).first()

        if not param:
            logger.info(f"Creating new parameter: {parameter_id} - {parameter_name}")
            param = Parameter(
                parameter_id=parameter_id,
                parameter_name=parameter_name,
                parameter_unit=parameter_unit,
                writable=False  # Default to read-only for imported data
            )
            self.session.add(param)
            self.session.commit()

        return param

    def reading_exists(
        self,
        device_id: int,
        parameter_id: int,
        timestamp: datetime
    ) -> bool:
        """Check if a reading already exists"""
        exists = self.session.query(ParameterReading).filter(
            and_(
                ParameterReading.device_id == device_id,
                ParameterReading.parameter_id == parameter_id,
                ParameterReading.timestamp == timestamp
            )
        ).first() is not None

        return exists

    def import_myuplink_csv(
        self,
        csv_path: str,
        skip_duplicates: bool = True,
        date_format: str = '%Y-%m-%d %H:%M:%S'
    ) -> Dict[str, int]:
        """
        Import CSV data from myUplink web export

        Expected CSV format:
        - Timestamp, Parameter ID, Parameter Name, Value, Unit
        or
        - Date, Time, Parameter, Value, Unit

        Args:
            csv_path: Path to CSV file
            skip_duplicates: Skip readings that already exist
            date_format: Format string for parsing dates

        Returns:
            Dictionary with import statistics
        """
        logger.info(f"Importing data from {csv_path}")

        device = self.get_device()
        stats = {
            'total_rows': 0,
            'imported': 0,
            'skipped_duplicates': 0,
            'errors': 0
        }

        try:
            # Read CSV file
            df = pd.read_csv(csv_path)
            stats['total_rows'] = len(df)

            logger.info(f"Found {stats['total_rows']} rows in CSV")
            logger.info(f"Columns: {list(df.columns)}")

            # Detect CSV format
            if 'Timestamp' in df.columns or 'timestamp' in df.columns:
                # Format 1: Timestamp, Parameter ID, Parameter Name, Value, Unit
                timestamp_col = 'Timestamp' if 'Timestamp' in df.columns else 'timestamp'
                param_id_col = 'Parameter ID' if 'Parameter ID' in df.columns else 'ParameterId'
                param_name_col = 'Parameter Name' if 'Parameter Name' in df.columns else 'ParameterName'
                value_col = 'Value' if 'Value' in df.columns else 'value'
                unit_col = 'Unit' if 'Unit' in df.columns else 'unit'

            elif 'Date' in df.columns and 'Time' in df.columns:
                # Format 2: Date, Time, Parameter, Value, Unit
                # Combine Date and Time into Timestamp
                df['Timestamp'] = df['Date'] + ' ' + df['Time']
                timestamp_col = 'Timestamp'
                param_name_col = 'Parameter'
                value_col = 'Value'
                unit_col = 'Unit'
                param_id_col = None  # Will need to map from name

            else:
                raise ValueError(f"Unrecognized CSV format. Columns: {list(df.columns)}")

            # Process each row
            for idx, row in df.iterrows():
                try:
                    # Parse timestamp
                    timestamp_str = str(row[timestamp_col])
                    timestamp = datetime.strptime(timestamp_str, date_format)

                    # Get parameter info
                    param_name = str(row[param_name_col])
                    param_id = str(row[param_id_col]) if param_id_col else self._guess_param_id(param_name)
                    value = float(row[value_col])
                    unit = str(row[unit_col]) if unit_col and pd.notna(row[unit_col]) else None

                    # Get or create parameter
                    param = self.get_or_create_parameter(param_id, param_name, unit)

                    # Check for duplicates
                    if skip_duplicates and self.reading_exists(device.id, param.id, timestamp):
                        stats['skipped_duplicates'] += 1
                        continue

                    # Create reading
                    reading = ParameterReading(
                        device_id=device.id,
                        parameter_id=param.id,
                        timestamp=timestamp,
                        value=value
                    )
                    self.session.add(reading)

                    stats['imported'] += 1

                    # Commit in batches
                    if stats['imported'] % 1000 == 0:
                        self.session.commit()
                        logger.info(f"Imported {stats['imported']} readings...")

                except Exception as e:
                    logger.warning(f"Error processing row {idx}: {e}")
                    stats['errors'] += 1
                    continue

            # Final commit
            self.session.commit()

            logger.info("="*80)
            logger.info("IMPORT COMPLETE")
            logger.info("="*80)
            logger.info(f"Total rows:         {stats['total_rows']}")
            logger.info(f"Imported:           {stats['imported']}")
            logger.info(f"Skipped duplicates: {stats['skipped_duplicates']}")
            logger.info(f"Errors:             {stats['errors']}")

            return stats

        except Exception as e:
            logger.error(f"Failed to import CSV: {e}")
            self.session.rollback()
            raise

    def import_generic_csv(
        self,
        csv_path: str,
        timestamp_column: str,
        parameter_id_column: str,
        value_column: str,
        parameter_name_column: Optional[str] = None,
        unit_column: Optional[str] = None,
        date_format: str = '%Y-%m-%d %H:%M:%S',
        skip_duplicates: bool = True
    ) -> Dict[str, int]:
        """
        Import CSV data with custom column mapping

        Args:
            csv_path: Path to CSV file
            timestamp_column: Name of timestamp column
            parameter_id_column: Name of parameter ID column
            value_column: Name of value column
            parameter_name_column: Name of parameter name column (optional)
            unit_column: Name of unit column (optional)
            date_format: Format string for parsing dates
            skip_duplicates: Skip readings that already exist

        Returns:
            Dictionary with import statistics
        """
        logger.info(f"Importing generic CSV from {csv_path}")

        device = self.get_device()
        stats = {
            'total_rows': 0,
            'imported': 0,
            'skipped_duplicates': 0,
            'errors': 0
        }

        try:
            df = pd.read_csv(csv_path)
            stats['total_rows'] = len(df)

            logger.info(f"Found {stats['total_rows']} rows")

            for idx, row in df.iterrows():
                try:
                    timestamp = datetime.strptime(str(row[timestamp_column]), date_format)
                    param_id = str(row[parameter_id_column])
                    value = float(row[value_column])

                    param_name = str(row[parameter_name_column]) if parameter_name_column else param_id
                    unit = str(row[unit_column]) if unit_column and pd.notna(row[unit_column]) else None

                    param = self.get_or_create_parameter(param_id, param_name, unit)

                    if skip_duplicates and self.reading_exists(device.id, param.id, timestamp):
                        stats['skipped_duplicates'] += 1
                        continue

                    reading = ParameterReading(
                        device_id=device.id,
                        parameter_id=param.id,
                        timestamp=timestamp,
                        value=value
                    )
                    self.session.add(reading)
                    stats['imported'] += 1

                    if stats['imported'] % 1000 == 0:
                        self.session.commit()
                        logger.info(f"Imported {stats['imported']} readings...")

                except Exception as e:
                    logger.warning(f"Error processing row {idx}: {e}")
                    stats['errors'] += 1
                    continue

            self.session.commit()

            logger.info(f"Import complete: {stats['imported']} readings imported")
            return stats

        except Exception as e:
            logger.error(f"Failed to import CSV: {e}")
            self.session.rollback()
            raise

    def _guess_param_id(self, param_name: str) -> str:
        """
        Try to guess parameter ID from name
        This is a fallback when parameter ID is not in CSV
        """
        # Common Nibe parameter name to ID mappings
        name_to_id = {
            'outdoor temperature': '40004',
            'supply temperature': '40008',
            'return temperature': '40012',
            'indoor temperature': '13',
            'compressor frequency': '41778',
            'degree minutes': '40940',
            'heating curve': '47007',
            'offset': '47011',
        }

        # Normalize name for matching
        normalized = param_name.lower().strip()

        for name, param_id in name_to_id.items():
            if name in normalized:
                return param_id

        # If no match, use a hash of the name as ID
        import hashlib
        hash_id = hashlib.md5(param_name.encode()).hexdigest()[:8]
        logger.warning(f"Unknown parameter '{param_name}', using generated ID: {hash_id}")
        return hash_id

    def export_to_csv(
        self,
        output_path: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        parameter_ids: Optional[List[str]] = None
    ) -> str:
        """
        Export database readings to CSV

        Args:
            output_path: Path to save CSV file
            start_date: Start date filter (optional)
            end_date: End date filter (optional)
            parameter_ids: List of parameter IDs to export (optional, exports all if None)

        Returns:
            Path to exported CSV file
        """
        logger.info(f"Exporting data to {output_path}")

        device = self.get_device()

        # Build query
        query = self.session.query(
            ParameterReading.timestamp,
            Parameter.parameter_id,
            Parameter.parameter_name,
            ParameterReading.value,
            Parameter.parameter_unit
        ).join(Parameter).filter(ParameterReading.device_id == device.id)

        if start_date:
            query = query.filter(ParameterReading.timestamp >= start_date)
        if end_date:
            query = query.filter(ParameterReading.timestamp <= end_date)
        if parameter_ids:
            query = query.filter(Parameter.parameter_id.in_(parameter_ids))

        # Execute query
        results = query.order_by(ParameterReading.timestamp).all()

        logger.info(f"Exporting {len(results)} readings...")

        # Write to CSV
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Timestamp', 'Parameter ID', 'Parameter Name', 'Value', 'Unit'])

            for row in results:
                writer.writerow([
                    row.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    row.parameter_id,
                    row.parameter_name,
                    row.value,
                    row.parameter_unit or ''
                ])

        logger.info(f"✅ Export complete: {output_path}")
        return output_path


def main():
    """Example usage"""
    import sys

    if len(sys.argv) < 2:
        logger.info("CSV Importer Usage:")
        logger.info("")
        logger.info("Import CSV:")
        logger.info("  python csv_importer.py import <csv_file>")
        logger.info("")
        logger.info("Export CSV:")
        logger.info("  python csv_importer.py export <output_file>")
        logger.info("")
        logger.info("Example:")
        logger.info("  python csv_importer.py import data/myuplink_export.csv")
        logger.info("  python csv_importer.py export data/backup.csv")
        return

    command = sys.argv[1]
    importer = CSVImporter()

    if command == 'import':
        if len(sys.argv) < 3:
            logger.error("Please specify CSV file to import")
            return

        csv_file = sys.argv[2]
        if not Path(csv_file).exists():
            logger.error(f"File not found: {csv_file}")
            return

        stats = importer.import_myuplink_csv(csv_file)

    elif command == 'export':
        if len(sys.argv) < 3:
            logger.error("Please specify output CSV file")
            return

        output_file = sys.argv[2]
        importer.export_to_csv(output_file)

    else:
        logger.error(f"Unknown command: {command}")
        logger.info("Valid commands: import, export")


if __name__ == '__main__':
    main()
