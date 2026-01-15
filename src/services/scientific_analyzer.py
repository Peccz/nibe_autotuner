"""
Scientific Test Analyzer
Specialized analysis methods for scientific tests that go beyond standard COP metrics.
"""
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from loguru import logger


class ScientificTestAnalyzer:
    """
    Analyzer for scientific heat pump tests.
    Provides specialized metrics beyond standard COP analysis.
    """

    def __init__(self, db_path='data/nibe_autotuner.db'):
        """
        Initialize the scientific analyzer.

        Args:
            db_path: Path to the SQLite database
        """
        self.db_path = db_path

        # Parameter IDs for analysis
        self.PARAM_ROOM_TEMP = '13'  # BT50 Room temperature
        self.PARAM_COMPRESSOR_FREQ = '41778'  # Compressor frequency (Hz)
        self.PARAM_IMMERSION_HEATER_POWER = '43427'  # Electrical addition power (kW)
        self.PARAM_DEGREE_MINUTES = '43005'  # Degree minutes

    def analyze_cooling_rate(self, start_time: datetime, end_time: datetime) -> Dict:
        """
        Calculate the cooling rate of the house in °C/hour.

        This is useful for determining the house's thermal time constant
        and heat loss characteristics.

        Args:
            start_time: Start of measurement period
            end_time: End of measurement period

        Returns:
            Dictionary with cooling rate analysis:
            {
                'cooling_rate_c_per_hour': float,  # °C/hour temperature drop
                'start_temp': float,                # Initial temperature
                'end_temp': float,                  # Final temperature
                'total_drop': float,                # Total temperature drop
                'duration_hours': float,            # Duration of measurement
                'data_points': int,                 # Number of readings used
                'r_squared': float,                 # Linearity of cooling (0-1)
                'success': bool                     # Whether analysis succeeded
            }
        """
        try:
            conn = sqlite3.connect(self.db_path)

            # Get parameter internal ID
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM parameters WHERE parameter_id = ?", (self.PARAM_ROOM_TEMP,))
            res = cursor.fetchone()
            if not res:
                logger.error(f"Parameter {self.PARAM_ROOM_TEMP} not found in database")
                return {'success': False, 'error': 'Parameter not found'}

            param_id = res[0]

            # Query room temperature readings
            query = """
            SELECT timestamp, value
            FROM parameter_readings
            WHERE parameter_id = ?
                AND timestamp >= ?
                AND timestamp <= ?
            ORDER BY timestamp ASC
            """

            df = pd.read_sql_query(
                query,
                conn,
                params=(param_id, start_time, end_time)
            )
            conn.close()

            if df.empty or len(df) < 2:
                logger.warning("Insufficient data for cooling rate analysis")
                return {'success': False, 'error': 'Insufficient data'}

            # Convert to numeric
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['value'] = pd.to_numeric(df['value'])

            # Calculate time difference in hours from start
            df['hours_elapsed'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds() / 3600

            # Perform linear regression to get cooling rate
            # temperature = start_temp + cooling_rate * time
            coeffs = np.polyfit(df['hours_elapsed'], df['value'], 1)
            cooling_rate_per_hour = coeffs[0]  # Slope (will be negative if cooling)

            # Calculate R² to measure linearity
            fitted_values = np.polyval(coeffs, df['hours_elapsed'])
            residuals = df['value'] - fitted_values
            ss_res = np.sum(residuals**2)
            ss_tot = np.sum((df['value'] - df['value'].mean())**2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            # Get start and end temperatures
            start_temp = df['value'].iloc[0]
            end_temp = df['value'].iloc[-1]
            total_drop = end_temp - start_temp

            # Duration
            duration_hours = df['hours_elapsed'].iloc[-1]

            result = {
                'cooling_rate_c_per_hour': round(cooling_rate_per_hour, 3),
                'start_temp': round(start_temp, 2),
                'end_temp': round(end_temp, 2),
                'total_drop': round(total_drop, 2),
                'duration_hours': round(duration_hours, 2),
                'data_points': len(df),
                'r_squared': round(r_squared, 3),
                'success': True
            }

            logger.info(f"Cooling rate analysis: {cooling_rate_per_hour:.3f} °C/hour (R²={r_squared:.3f})")
            return result

        except Exception as e:
            logger.error(f"Error analyzing cooling rate: {e}")
            return {'success': False, 'error': str(e)}

    def count_compressor_starts(self, start_time: datetime, end_time: datetime) -> Dict:
        """
        Count the number of compressor starts during a period.

        A "start" is defined as the compressor frequency going from 0 Hz
        to a non-zero value.

        Args:
            start_time: Start of measurement period
            end_time: End of measurement period

        Returns:
            Dictionary with compressor start analysis:
            {
                'start_count': int,              # Number of starts
                'avg_runtime_minutes': float,    # Average runtime per cycle
                'total_runtime_hours': float,    # Total compressor runtime
                'idle_hours': float,             # Total idle time
                'data_points': int,              # Number of readings
                'success': bool
            }
        """
        try:
            conn = sqlite3.connect(self.db_path)

            # Get parameter internal ID
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM parameters WHERE parameter_id = ?", (self.PARAM_COMPRESSOR_FREQ,))
            res = cursor.fetchone()
            if not res:
                logger.error(f"Parameter {self.PARAM_COMPRESSOR_FREQ} not found in database")
                return {'success': False, 'error': 'Parameter not found'}

            param_id = res[0]

            # Query compressor frequency readings
            query = """
            SELECT timestamp, value
            FROM parameter_readings
            WHERE parameter_id = ?
                AND timestamp >= ?
                AND timestamp <= ?
            ORDER BY timestamp ASC
            """

            df = pd.read_sql_query(
                query,
                conn,
                params=(param_id, start_time, end_time)
            )
            conn.close()

            if df.empty:
                logger.warning("No compressor data found")
                return {'success': False, 'error': 'No data'}

            # Convert to numeric
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['value'] = pd.to_numeric(df['value'])

            # Determine running state (frequency > 0 Hz)
            df['running'] = df['value'] > 0

            # Find transitions from stopped to running (starts)
            df['prev_running'] = df['running'].shift(1, fill_value=False)
            df['is_start'] = (~df['prev_running']) & df['running']

            start_count = df['is_start'].sum()

            # Calculate runtime statistics
            running_readings = df[df['running']]
            total_readings = len(df)

            # Estimate time between readings (assume regular intervals)
            if len(df) > 1:
                time_diffs = df['timestamp'].diff().dt.total_seconds() / 60  # minutes
                avg_interval_minutes = time_diffs.median()
            else:
                avg_interval_minutes = 5  # Default assumption

            # Total runtime
            total_runtime_hours = (len(running_readings) * avg_interval_minutes) / 60

            # Total idle time
            idle_readings = total_readings - len(running_readings)
            idle_hours = (idle_readings * avg_interval_minutes) / 60

            # Average runtime per cycle
            if start_count > 0:
                avg_runtime_minutes = (total_runtime_hours * 60) / start_count
            else:
                avg_runtime_minutes = 0

            result = {
                'start_count': int(start_count),
                'avg_runtime_minutes': round(avg_runtime_minutes, 1),
                'total_runtime_hours': round(total_runtime_hours, 2),
                'idle_hours': round(idle_hours, 2),
                'data_points': total_readings,
                'success': True
            }

            logger.info(f"Compressor starts: {start_count} starts, avg runtime {avg_runtime_minutes:.1f} min")
            return result

        except Exception as e:
            logger.error(f"Error counting compressor starts: {e}")
            return {'success': False, 'error': str(e)}

    def check_immersion_heater_usage(self, start_time: datetime, end_time: datetime) -> Dict:
        """
        Check if the electrical immersion heater (elpatron) was used.

        The immersion heater supplements the heat pump when temperatures
        are too low or demand is too high. We want to minimize its use.

        Args:
            start_time: Start of measurement period
            end_time: End of measurement period

        Returns:
            Dictionary with immersion heater usage:
            {
                'was_used': bool,                # Whether heater was used at all
                'total_usage_hours': float,      # Total hours with power > 0
                'max_power_kw': float,           # Maximum power draw
                'avg_power_kw': float,           # Average power when active
                'total_energy_kwh': float,       # Estimated total energy used
                'usage_percentage': float,       # % of time heater was on
                'data_points': int,              # Number of readings
                'success': bool
            }
        """
        try:
            conn = sqlite3.connect(self.db_path)

            # Get parameter internal ID
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM parameters WHERE parameter_id = ?",
                          (self.PARAM_IMMERSION_HEATER_POWER,))
            res = cursor.fetchone()
            if not res:
                logger.warning(f"Parameter {self.PARAM_IMMERSION_HEATER_POWER} not found in database")
                return {'success': False, 'error': 'Parameter not found'}

            param_id = res[0]

            # Query immersion heater power readings
            query = """
            SELECT timestamp, value
            FROM parameter_readings
            WHERE parameter_id = ?
                AND timestamp >= ?
                AND timestamp <= ?
            ORDER BY timestamp ASC
            """

            df = pd.read_sql_query(
                query,
                conn,
                params=(param_id, start_time, end_time)
            )
            conn.close()

            if df.empty:
                logger.warning("No immersion heater data found")
                # If no data, we can't confirm usage, but assume not used
                return {
                    'was_used': False,
                    'total_usage_hours': 0,
                    'max_power_kw': 0,
                    'avg_power_kw': 0,
                    'total_energy_kwh': 0,
                    'usage_percentage': 0,
                    'data_points': 0,
                    'success': True,
                    'note': 'No data available, assuming heater not used'
                }

            # Convert to numeric
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['value'] = pd.to_numeric(df['value'])

            # Determine if heater was active (power > 0)
            df['active'] = df['value'] > 0

            was_used = df['active'].any()
            active_readings = df[df['active']]

            # Calculate statistics
            if len(active_readings) > 0:
                max_power_kw = active_readings['value'].max()
                avg_power_kw = active_readings['value'].mean()
            else:
                max_power_kw = 0
                avg_power_kw = 0

            # Estimate time between readings
            if len(df) > 1:
                time_diffs = df['timestamp'].diff().dt.total_seconds() / 3600  # hours
                avg_interval_hours = time_diffs.median()
            else:
                avg_interval_hours = 5 / 60  # Default: 5 minutes

            # Total usage hours
            total_usage_hours = len(active_readings) * avg_interval_hours

            # Total energy (kWh) = sum of (power × time interval)
            total_energy_kwh = (active_readings['value'] * avg_interval_hours).sum()

            # Usage percentage
            total_readings = len(df)
            usage_percentage = (len(active_readings) / total_readings * 100) if total_readings > 0 else 0

            result = {
                'was_used': bool(was_used),
                'total_usage_hours': round(total_usage_hours, 2),
                'max_power_kw': round(max_power_kw, 2),
                'avg_power_kw': round(avg_power_kw, 2),
                'total_energy_kwh': round(total_energy_kwh, 2),
                'usage_percentage': round(usage_percentage, 1),
                'data_points': total_readings,
                'success': True
            }

            if was_used:
                logger.warning(f"Immersion heater WAS USED: {total_energy_kwh:.2f} kWh over {total_usage_hours:.2f} hours")
            else:
                logger.info("Immersion heater was NOT used during this period")

            return result

        except Exception as e:
            logger.error(f"Error checking immersion heater usage: {e}")
            return {'success': False, 'error': str(e)}

    def get_test_summary(self, start_time: datetime, end_time: datetime) -> Dict:
        """
        Get a comprehensive summary of all scientific metrics for a test period.

        Args:
            start_time: Start of test period
            end_time: End of test period

        Returns:
            Dictionary containing all analysis results
        """
        logger.info(f"Running scientific analysis for period {start_time} to {end_time}")

        return {
            'period': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'duration_hours': (end_time - start_time).total_seconds() / 3600
            },
            'cooling_rate': self.analyze_cooling_rate(start_time, end_time),
            'compressor_starts': self.count_compressor_starts(start_time, end_time),
            'immersion_heater': self.check_immersion_heater_usage(start_time, end_time)
        }


if __name__ == "__main__":
    """Test the scientific analyzer"""
    import sys

    analyzer = ScientificTestAnalyzer()

    # Test with last 24 hours
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=24)

    print("=" * 80)
    print("SCIENTIFIC TEST ANALYZER - TEST RUN")
    print("=" * 80)
    print()

    # Test each method
    print("1. COOLING RATE ANALYSIS")
    print("-" * 80)
    cooling = analyzer.analyze_cooling_rate(start_time, end_time)
    for key, value in cooling.items():
        print(f"  {key}: {value}")
    print()

    print("2. COMPRESSOR STARTS ANALYSIS")
    print("-" * 80)
    starts = analyzer.count_compressor_starts(start_time, end_time)
    for key, value in starts.items():
        print(f"  {key}: {value}")
    print()

    print("3. IMMERSION HEATER USAGE")
    print("-" * 80)
    heater = analyzer.check_immersion_heater_usage(start_time, end_time)
    for key, value in heater.items():
        print(f"  {key}: {value}")
    print()

    print("4. COMPLETE TEST SUMMARY")
    print("-" * 80)
    summary = analyzer.get_test_summary(start_time, end_time)
    import json
    print(json.dumps(summary, indent=2))
    print()

    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

