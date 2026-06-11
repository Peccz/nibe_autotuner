from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import create_engine, desc, text
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger
import pandas as pd
import numpy as np

from data.models import Device, Parameter, ParameterReading, Recommendation, ABTestResult
from core.config import settings

# --- Pydantic models (DTOs) for internal use ---
from pydantic import BaseModel, Field

class OptimizationOpportunity(BaseModel):
    parameter_id: str
    parameter_name: str
    current_value: float
    suggested_value: float
    expected_impact: str
    reasoning: str
    confidence: float = Field(..., ge=0.0, le=1.0)

class HeatingMetrics(BaseModel):
    cop: Optional[float] = None
    delta_t: Optional[float] = None
    avg_outdoor_temp: Optional[float] = None
    avg_supply_temp: Optional[float] = None
    avg_return_temp: Optional[float] = None
    avg_compressor_freq: Optional[float] = None
    runtime_hours: Optional[float] = None
    num_cycles: int = 0

class HotWaterMetrics(BaseModel):
    cop: Optional[float] = None
    delta_t: Optional[float] = None
    avg_outdoor_temp: Optional[float] = None
    avg_hot_water_temp: Optional[float] = None
    avg_supply_temp: Optional[float] = None
    avg_return_temp: Optional[float] = None
    avg_compressor_freq: Optional[float] = None
    runtime_hours: Optional[float] = None
    num_cycles: int = 0

class EfficiencyMetrics(BaseModel):
    period_start: datetime
    period_end: datetime
    avg_outdoor_temp: Optional[float] = None
    avg_indoor_temp: Optional[float] = None
    avg_supply_temp: Optional[float] = None
    avg_return_temp: Optional[float] = None
    delta_t: float
    delta_t_active: Optional[float] = None
    delta_t_hot_water: Optional[float] = None
    avg_compressor_freq: Optional[float] = None
    degree_minutes: Optional[float] = None
    heating_curve: Optional[float] = None
    curve_offset: Optional[float] = None
    estimated_cop: Optional[float] = None
    estimated_time_to_start_minutes: Optional[float] = None
    compressor_runtime_hours: Optional[float] = None
    heating_metrics: Optional[HeatingMetrics] = None
    hot_water_metrics: Optional[HotWaterMetrics] = None

class COPModel: # Placeholder, real model might be complex
    @staticmethod
    def estimate_cop_empirical(outdoor_temp, supply_temp, return_temp, compressor_freq=None, pump_speed=None, num_cycles=None, runtime_hours=None):
        if outdoor_temp is None or supply_temp is None or return_temp is None:
            return None
        
        base_cop = 4.0 - (outdoor_temp / 10.0) - ((supply_temp - return_temp) / 10.0)
        
        return max(1.0, base_cop)


class HeatPumpAnalyzer:
    COMPRESSOR_ACTIVE_THRESHOLD = 20
    HOT_WATER_TEMP_THRESHOLD = 45

    PARAM_OUTDOOR_TEMP = '40004'
    PARAM_INDOOR_TEMP = '40033'
    PARAM_SUPPLY_TEMP = '40008'
    PARAM_RETURN_TEMP = '40012'
    PARAM_COMPRESSOR_FREQ = '41778'
    PARAM_HEATING_CURVE = '47007'
    PARAM_CURVE_OFFSET = '47011'
    PARAM_DM_CURRENT = '40009'
    PARAM_DM_HEATING_START = '47021'
    PARAM_CALCULATED_SUPPLY_TEMP = '40067'
    PARAM_HOT_WATER_TEMP = '40013'
    PARAM_COMPRESSOR_FREQUENCY = '41778'

    COP_HEATING_ELITE = 4.0
    COP_HEATING_EXCELLENT = 3.5
    COP_HEATING_VERY_GOOD = 3.0
    COP_HEATING_GOOD = 2.5
    COP_HEATING_ACCEPTABLE = 2.0

    COP_HOT_WATER_ELITE = 3.0
    COP_HOT_WATER_EXCELLENT = 2.5
    COP_HOT_WATER_VERY_GOOD = 2.0
    COP_HOT_WATER_GOOD = 1.5
    COP_HOT_WATER_ACCEPTABLE = 1.0

    DELTA_T_PERFECT_MIN = 5.0
    DELTA_T_PERFECT_MAX = 8.0
    DELTA_T_EXCELLENT_MIN = 4.0
    DELTA_T_EXCELLENT_MAX = 9.0
    DELTA_T_GOOD_MIN = 3.0
    DELTA_T_GOOD_MAX = 10.0

    TARGET_DM_MIN = -250
    TARGET_DM_MAX = -150

    ELECTRICITY_PRICE_SEK_KWH = 0.5
    COMPRESSOR_POWER_AVG_KW = 1.5

    def __init__(self, db_path: str = settings.DATABASE_URL.replace('sqlite:///', '')):
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{self.db_path}', echo=False)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        
    def get_device(self) -> Device:
        device = self.session.query(Device).first()
        if not device:
            raise ValueError("No device found in database")
        return device

    def get_parameter(self, parameter_id: str) -> Optional[Parameter]:
        """Get parameter by API ID string"""
        return self.session.query(Parameter).filter_by(parameter_id=parameter_id).first()

    def get_latest_value(self, device: Device, parameter_id_str: str) -> Optional[float]:
        try:
            # logger.debug(f"[Analyzer.get_latest_value] Device ID: {device.id}, Param ID Str: '{parameter_id_str}'")
            param = self.session.query(Parameter).filter_by(parameter_id=parameter_id_str).first()
            
            if not param:
                # logger.warning(f"[Analyzer.get_latest_value] Parameter '{parameter_id_str}' NOT FOUND in self.session!")
                return None
            
            # logger.debug(f"[Analyzer.get_latest_value] Found param ORM: {param.id} ('{param.parameter_name}')")

            reading = self.session.query(ParameterReading).filter_by(
                device_id=device.id,
                parameter_id=param.id
            ).order_by(desc(ParameterReading.timestamp)).first()
            
            if reading:
                # logger.debug(f"[Analyzer.get_latest_value] Found reading: {reading.value} @ {reading.timestamp}")
                return reading.value
            
            # logger.warning(f"[Analyzer.get_latest_value] No reading found for device {device.id} param {param.id}")
            return None
        except Exception as e:
            logger.error(f"[Analyzer.get_latest_value] Error for '{parameter_id_str}': {e}")
            return None


    def get_readings(
        self,
        device: Device,
        parameter_id_str: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Tuple[datetime, float]]:
        param = self.session.query(Parameter).filter_by(parameter_id=parameter_id_str).first()
        if not param:
            logger.warning(f"Parameter {parameter_id_str} not found in DB.")
            return []

        readings = self.session.query(ParameterReading).filter(
            ParameterReading.device_id == device.id,
            ParameterReading.parameter_id == param.id,
            ParameterReading.timestamp >= start_time,
            ParameterReading.timestamp <= end_time
        ).order_by(ParameterReading.timestamp).all()

        return [(r.timestamp, r.value) for r in readings]

    def calculate_average(
        self,
        device: Device,
        parameter_id_str: str,
        start_time: datetime,
        end_time: datetime
    ) -> Optional[float]:
        readings = self.get_readings(device, parameter_id_str, start_time, end_time)
        if not readings:
            return None
        return sum([r[1] for r in readings]) / len(readings)


    def calculate_metrics(
        self,
        hours_back: int = 24,
        end_offset_hours: int = 0
    ) -> EfficiencyMetrics:
        device = self.get_device()
        end_time = datetime.utcnow() - timedelta(hours=end_offset_hours)
        start_time = end_time - timedelta(hours=hours_back)

        logger.info(f"Calculating metrics from {start_time} to {end_time}")

        avg_outdoor = self.calculate_average(device, self.PARAM_OUTDOOR_TEMP, start_time, end_time)
        avg_indoor = self.calculate_average(device, self.PARAM_INDOOR_TEMP, start_time, end_time)
        avg_supply = self.calculate_average(device, self.PARAM_SUPPLY_TEMP, start_time, end_time)
        avg_return = self.calculate_average(device, self.PARAM_RETURN_TEMP, start_time, end_time)
        avg_compressor = self.calculate_average(device, self.PARAM_COMPRESSOR_FREQ, start_time, end_time)

        heating_curve = self.get_latest_value(device, self.PARAM_HEATING_CURVE)
        curve_offset = self.get_latest_value(device, self.PARAM_CURVE_OFFSET)
        degree_minutes = self.get_latest_value(device, self.PARAM_DM_CURRENT)

        compressor_runtime = self._calculate_compressor_runtime(device, start_time, end_time)
        delta_t = (avg_supply or 0.0) - (avg_return or 0.0)

        delta_t_active, delta_t_hot_water = self._calculate_active_delta_t(device, start_time, end_time)
        estimated_cop = self._estimate_cop(avg_outdoor, avg_supply, avg_return)

        heating_metrics, hot_water_metrics = self._calculate_separate_metrics(device, start_time, end_time)
        estimated_time_to_start = self._calculate_time_to_start(device)

        metrics = EfficiencyMetrics(
            period_start=start_time,
            period_end=end_time,
            avg_outdoor_temp=avg_outdoor or 0.0,
            avg_indoor_temp=avg_indoor or 0.0,
            avg_supply_temp=avg_supply or 0.0,
            avg_return_temp=avg_return or 0.0,
            delta_t=delta_t,
            delta_t_active=delta_t_active,
            delta_t_hot_water=delta_t_hot_water,
            avg_compressor_freq=avg_compressor or 0.0,
            degree_minutes=degree_minutes or 0.0,
            heating_curve=heating_curve or 0.0,
            curve_offset=curve_offset, # NO FALLBACK HERE ANYMORE
            estimated_cop=estimated_cop,
            estimated_time_to_start_minutes=estimated_time_to_start,
            compressor_runtime_hours=compressor_runtime,
            heating_metrics=heating_metrics,
            hot_water_metrics=hot_water_metrics
        )

        cop_str = f"{estimated_cop:.2f}" if estimated_cop else "N/A"
        dm_str = f"{degree_minutes:.0f}" if degree_minutes else "N/A"
        outdoor_str = f"{avg_outdoor:.1f}" if avg_outdoor else "N/A"
        logger.info(f"Metrics calculated: COP={cop_str}, DM={dm_str}, Outdoor={outdoor_str}°C")

        return metrics

    def _calculate_time_to_start(self, device: Device) -> Optional[float]:
        try:
            current_dm = self.get_latest_value(device, self.PARAM_DM_CURRENT)
            if current_dm is None: return None

            start_threshold = self.get_latest_value(device, self.PARAM_DM_HEATING_START)
            if start_threshold is None: start_threshold = -60

            if current_dm <= start_threshold: return 0.0

            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=15)

            avg_actual = self.calculate_average(device, self.PARAM_SUPPLY_TEMP, start_time, end_time)
            avg_calculated = self.calculate_average(device, self.PARAM_CALCULATED_SUPPLY_TEMP, start_time, end_time)

            if avg_actual is None or avg_calculated is None: return None

            dm_per_minute = avg_actual - avg_calculated
            if dm_per_minute >= 0: return None

            distance_to_go = start_threshold - current_dm
            minutes_to_start = distance_to_go / dm_per_minute
            return max(0.0, minutes_to_start)

        except Exception as e:
            logger.warning(f"Failed to calculate time to start: {e}")
            return None

    def _calculate_compressor_runtime(self, device: Device, start_time: datetime, end_time: datetime) -> float:
        readings = self.get_readings(device, self.PARAM_COMPRESSOR_FREQUENCY, start_time, end_time)
        if not readings: return 0.0
        total_seconds = 0.0
        for i in range(len(readings) - 1):
            if readings[i][1] > 0:
                time_diff = (readings[i + 1][0] - readings[i][0]).total_seconds()
                total_seconds += time_diff
        return total_seconds / 3600.0

    def _calculate_active_delta_t(self, device: Device, start_time: datetime, end_time: datetime) -> Tuple[Optional[float], Optional[float]]:
        supply_readings = self.get_readings(device, self.PARAM_SUPPLY_TEMP, start_time, end_time)
        return_readings = self.get_readings(device, self.PARAM_RETURN_TEMP, start_time, end_time)
        compressor_readings = self.get_readings(device, self.PARAM_COMPRESSOR_FREQ, start_time, end_time)

        if not supply_readings or not return_readings or not compressor_readings: return None, None
        space_heating_deltas = []
        hot_water_deltas = []
        time_tolerance = timedelta(seconds=300)

        for supply_ts, supply_temp in supply_readings:
            return_temp = None
            min_return_diff = time_tolerance
            for return_ts, temp in return_readings:
                diff = abs(supply_ts - return_ts)
                if diff < min_return_diff:
                    min_return_diff = diff
                    return_temp = temp

            comp_freq = None
            min_comp_diff = time_tolerance
            for comp_ts, freq in compressor_readings:
                diff = abs(supply_ts - comp_ts)
                if diff < min_comp_diff:
                    min_comp_diff = diff
                    comp_freq = freq

            if return_temp is not None and comp_freq is not None:
                if comp_freq >= self.COMPRESSOR_ACTIVE_THRESHOLD:
                    delta = supply_temp - return_temp
                    if supply_temp < self.HOT_WATER_TEMP_THRESHOLD: space_heating_deltas.append(delta)
                    else: hot_water_deltas.append(delta)

        delta_t_active = sum(space_heating_deltas) / len(space_heating_deltas) if space_heating_deltas else None
        delta_t_hot_water = sum(hot_water_deltas) / len(hot_water_deltas) if hot_water_deltas else None

        if space_heating_deltas or hot_water_deltas:
            # logger.debug(
            #     f"Delta T analysis: {len(space_heating_deltas)} space heating readings, "
            #     f"{len(hot_water_deltas)} hot water readings"
            # )
            pass

        return delta_t_active, delta_t_hot_water

    def _estimate_cop(self, outdoor_temp: Optional[float], supply_temp: Optional[float], return_temp: Optional[float], compressor_freq: Optional[float] = None, pump_speed: Optional[float] = None, num_cycles: Optional[int] = None, runtime_hours: Optional[float] = None) -> Optional[float]:
        if not all([outdoor_temp, supply_temp, return_temp]): return None
        cop = COPModel.estimate_cop_empirical(outdoor_temp=outdoor_temp, supply_temp=supply_temp, return_temp=return_temp, compressor_freq=compressor_freq, pump_speed=pump_speed, num_cycles=num_cycles, runtime_hours=runtime_hours)
        return cop

    def _calculate_separate_metrics(self, device: Device, start_time: datetime, end_time: datetime) -> Tuple[Optional[HeatingMetrics], Optional[HotWaterMetrics]]:
        supply_readings = self.get_readings(device, self.PARAM_SUPPLY_TEMP, start_time, end_time)
        return_readings = self.get_readings(device, self.PARAM_RETURN_TEMP, start_time, end_time)
        outdoor_readings = self.get_readings(device, self.PARAM_OUTDOOR_TEMP, start_time, end_time)
        compressor_readings = self.get_readings(device, self.PARAM_COMPRESSOR_FREQ, start_time, end_time)
        hot_water_readings = self.get_readings(device, self.PARAM_HOT_WATER_TEMP, start_time, end_time)

        if not supply_readings or not return_readings or not compressor_readings: return None, None
        heating_data = []
        hot_water_data = []
        time_tolerance = timedelta(seconds=300)

        for supply_ts, supply_temp in supply_readings:
            outdoor_temp = self._find_closest_reading(outdoor_readings, supply_ts, time_tolerance)
            return_temp = self._find_closest_reading(return_readings, supply_ts, time_tolerance)
            comp_freq = self._find_closest_reading(compressor_readings, supply_ts, time_tolerance)
            hw_temp = self._find_closest_reading(hot_water_readings, supply_ts, time_tolerance)

            if all(v is not None for v in [outdoor_temp, return_temp, comp_freq]):
                if comp_freq >= self.COMPRESSOR_ACTIVE_THRESHOLD:
                    cop = self._estimate_cop(outdoor_temp, supply_temp, return_temp)
                    if supply_temp < self.HOT_WATER_TEMP_THRESHOLD:
                        heating_data.append((supply_ts, supply_temp, return_temp, outdoor_temp, comp_freq))
                    else:
                        if hw_temp is not None:
                            hot_water_data.append((supply_ts, supply_temp, return_temp, outdoor_temp, comp_freq, hw_temp))

        heating_metrics = None
        if heating_data: heating_metrics = self._calculate_heating_metrics(heating_data, start_time, end_time)

        hot_water_metrics = None
        if hot_water_data: hot_water_metrics = self._calculate_hot_water_metrics(hot_water_data, start_time, end_time)

        return heating_metrics, hot_water_metrics

    def _find_closest_reading(self, readings: List[Tuple[datetime, float]], target_time: datetime, max_diff: timedelta) -> Optional[float]:
        closest_value = None
        min_diff = max_diff
        for ts, value in readings:
            diff = abs(target_time - ts)
            if diff < min_diff:
                min_diff = diff
                closest_value = value
        return closest_value

    def _calculate_heating_metrics(self, heating_data: List[Tuple[datetime, float, float, float, float]], start_time: datetime, end_time: datetime) -> HeatingMetrics:
        if not heating_data: return HeatingMetrics()
        supply_temps = [d[1] for d in heating_data]
        return_temps = [d[2] for d in heating_data]
        outdoor_temps = [d[3] for d in heating_data]
        comp_freqs = [d[4] for d in heating_data]
        avg_supply = sum(supply_temps) / len(supply_temps)
        avg_return = sum(return_temps) / len(return_temps)
        avg_outdoor = sum(outdoor_temps) / len(outdoor_temps)
        avg_comp_freq = sum(comp_freqs) / len(comp_freqs)
        delta_t = avg_supply - avg_return
        cop = self._estimate_cop(avg_outdoor, avg_supply, avg_return)
        total_hours = (end_time - start_time).total_seconds() / 3600
        reading_interval = 5 / 60
        runtime_hours = len(heating_data) * reading_interval
        num_cycles = self._count_cycles([d[0] for d in heating_data])
        return HeatingMetrics(cop=cop, delta_t=delta_t, avg_outdoor_temp=avg_outdoor, avg_supply_temp=avg_supply, avg_return_temp=avg_return, avg_compressor_freq=avg_comp_freq, runtime_hours=runtime_hours, num_cycles=num_cycles)

    def _calculate_hot_water_metrics(self, hot_water_data: List[Tuple[datetime, float, float, float, float, float]], start_time: datetime, end_time: datetime) -> HotWaterMetrics:
        if not hot_water_data: return HotWaterMetrics()
        supply_temps = [d[1] for d in hot_water_data]
        return_temps = [d[2] for d in hot_water_data]
        outdoor_temps = [d[3] for d in hot_water_data]
        comp_freqs = [d[4] for d in hot_water_data]
        hw_temps = [d[5] for d in hot_water_data]
        avg_supply = sum(supply_temps) / len(supply_temps)
        avg_return = sum(return_temps) / len(return_temps)
        avg_outdoor = sum(outdoor_temps) / len(outdoor_temps)
        avg_comp_freq = sum(comp_freqs) / len(comp_freqs)
        avg_hw_temp = sum(hw_temps) / len(hw_temps)
        delta_t = avg_supply - avg_return
        cop = self._estimate_cop(avg_outdoor, avg_hw_temp, avg_return)
        reading_interval = 5 / 60
        runtime_hours = len(hot_water_data) * reading_interval
        num_cycles = self._count_cycles([d[0] for d in hot_water_data])
        return HotWaterMetrics(cop=cop, delta_t=delta_t, avg_outdoor_temp=avg_outdoor, avg_hot_water_temp=avg_hw_temp, avg_supply_temp=avg_supply, avg_return_temp=avg_return, avg_compressor_freq=avg_comp_freq, runtime_hours=runtime_hours, num_cycles=num_cycles)

    def _count_cycles(self, timestamps: List[datetime]) -> int:
        if len(timestamps) < 2: return 0 if len(timestamps) == 0 else 1
        cycles = 1
        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i-1]).total_seconds() / 60
            if gap > 30: cycles += 1
        return cycles

    @staticmethod
    def get_cop_rating_heating(cop: Optional[float]) -> dict:
        if cop is None: return {'tier': 'Unknown', 'badge': 'N/A', 'emoji': '❓', 'color': '#666'}
        if cop >= HeatPumpAnalyzer.COP_HEATING_ELITE: return {'tier': 'Elite', 'badge': '🏆 ELITE', 'emoji': '🏆', 'color': '#FFD700'}
        elif cop >= HeatPumpAnalyzer.COP_HEATING_EXCELLENT: return {'tier': 'Excellent', 'badge': '⭐ EXCELLENT', 'emoji': '⭐', 'color': '#00D4FF'}
        elif cop >= HeatPumpAnalyzer.COP_HEATING_VERY_GOOD: return {'tier': 'Very Good', 'badge': '✨ VERY GOOD', 'emoji': '✨', 'color': '#00FF88'}
        elif cop >= HeatPumpAnalyzer.COP_HEATING_GOOD: return {'tier': 'Good', 'badge': '✅ GOOD', 'emoji': '✅', 'color': '#88FF00'}
        elif cop >= HeatPumpAnalyzer.COP_HEATING_ACCEPTABLE: return {'tier': 'Acceptable', 'badge': '👍 OK', 'emoji': '👍', 'color': '#FFA500'}
        else: return {'tier': 'Poor', 'badge': '⚠️ POOR', 'emoji': '⚠️', 'color': '#FF4444'}

    @staticmethod
    def get_cop_rating_hot_water(cop: Optional[float]) -> dict:
        if cop is None: return {'tier': 'Unknown', 'badge': 'N/A', 'emoji': '❓', 'color': '#666'}
        if cop >= HeatPumpAnalyzer.COP_HOT_WATER_ELITE: return {'tier': 'Elite', 'badge': '🏆 ELITE', 'emoji': '🏆', 'color': '#FFD700'}
        elif cop >= HeatPumpAnalyzer.COP_HOT_WATER_EXCELLENT: return {'tier': 'Excellent', 'badge': '⭐ EXCELLENT', 'emoji': '⭐', 'color': '#00D4FF'}
        elif cop >= HeatPumpAnalyzer.COP_HOT_WATER_VERY_GOOD: return {'tier': 'Very Good', 'badge': '✨ VERY GOOD', 'emoji': '✨', 'color': '#00FF88'}
        elif cop >= HeatPumpAnalyzer.COP_HOT_WATER_GOOD: return {'tier': 'Good', 'badge': '✅ GOOD', 'emoji': '✅', 'color': '#88FF00'}
        elif cop >= HeatPumpAnalyzer.COP_HOT_WATER_ACCEPTABLE: return {'tier': 'Acceptable', 'badge': '👍 OK', 'emoji': '👍', 'color': '#FFA500'}
        else: return {'tier': 'Poor', 'badge': '⚠️ POOR', 'emoji': '⚠️', 'color': '#FF4444'}

    @staticmethod
    def get_delta_t_rating(delta_t: Optional[float]) -> dict:
        if delta_t is None: return {'tier': 'Unknown', 'badge': 'N/A', 'emoji': '❓', 'color': '#666'}
        if HeatPumpAnalyzer.DELTA_T_PERFECT_MIN <= delta_t <= HeatPumpAnalyzer.DELTA_T_PERFECT_MAX: return {'tier': 'Perfect', 'badge': '💎 PERFECT', 'emoji': '💎', 'color': '#9D00FF'}
        elif HeatPumpAnalyzer.DELTA_T_EXCELLENT_MIN <= delta_t <= HeatPumpAnalyzer.DELTA_T_EXCELLENT_MAX: return {'tier': 'Excellent', 'badge': '⭐ EXCELLENT', 'emoji': '⭐', 'color': '#00D4FF'}
        elif HeatPumpAnalyzer.DELTA_T_GOOD_MIN <= delta_t <= HeatPumpAnalyzer.DELTA_T_GOOD_MAX: return {'tier': 'Good', 'badge': '✅ GOOD', 'emoji': '✅', 'color': '#88FF00'}
        else: return {'tier': 'Needs Adjustment', 'badge': '⚠️ ADJUST', 'emoji': '⚠️', 'color': '#FF4444'}

    def get_cop_vs_outdoor_temp(self, device: Device, start_time: datetime, end_time: datetime) -> dict:
        heating_metrics, hot_water_metrics = self._calculate_separate_metrics(device, start_time, end_time)
        supply_readings = self.get_readings(device, self.PARAM_SUPPLY_TEMP, start_time, end_time)
        return_readings = self.get_readings(device, self.PARAM_RETURN_TEMP, start_time, end_time)
        outdoor_readings = self.get_readings(device, self.PARAM_OUTDOOR_TEMP, start_time, end_time)
        compressor_readings = self.get_readings(device, self.PARAM_COMPRESSOR_FREQ, start_time, end_time)
        heating_points = []
        hot_water_points = []
        time_tolerance = timedelta(seconds=300)
        for supply_ts, supply_temp in supply_readings:
            outdoor_temp = self._find_closest_reading(outdoor_readings, supply_ts, time_tolerance)
            return_temp = self._find_closest_reading(return_readings, supply_ts, time_tolerance)
            comp_freq = self._find_closest_reading(compressor_readings, supply_ts, time_tolerance)
            if all(v is not None for v in [outdoor_temp, return_temp, comp_freq]):
                if comp_freq >= self.COMPRESSOR_ACTIVE_THRESHOLD:
                    cop = self._estimate_cop(outdoor_temp, supply_temp, return_temp)
                    if supply_temp < self.HOT_WATER_TEMP_THRESHOLD: heating_points.append((outdoor_temp, cop))
                    else: hot_water_points.append((outdoor_temp, cop))
        outdoor_range = range(-15, 16, 1)
        carnot_curve = []
        for outdoor_temp in outdoor_range:
            supply_temp = 35 + (0 - outdoor_temp) * 0.5
            theoretical_cop = self._estimate_cop(outdoor_temp, supply_temp, supply_temp - 7)
            if theoretical_cop: carnot_curve.append((outdoor_temp, theoretical_cop))
        return {'heating': heating_points, 'hot_water': hot_water_points, 'carnot_curve': carnot_curve}

    def calculate_cost_analysis(self, heating_metrics: Optional[HeatingMetrics], hot_water_metrics: Optional[HotWaterMetrics], electricity_price: float = None) -> dict:
        if electricity_price is None: electricity_price = self.ELECTRICITY_PRICE_SEK_KWH
        result = {'heating': {'runtime_hours': 0, 'energy_kwh': 0, 'cost_sek': 0, 'heat_output_kwh': 0}, 'hot_water': {'runtime_hours': 0, 'energy_kwh': 0, 'cost_sek': 0, 'heat_output_kwh': 0}, 'total': {'runtime_hours': 0, 'energy_kwh': 0, 'cost_sek': 0, 'heat_output_kwh': 0}, 'electricity_price': electricity_price}
        if heating_metrics and heating_metrics.runtime_hours:
            energy_kwh = heating_metrics.runtime_hours * self.COMPRESSOR_POWER_AVG_KW
            cost_sek = energy_kwh * electricity_price
            heat_output = energy_kwh * (heating_metrics.cop if heating_metrics.cop else 3.0)
            result['heating'] = {'runtime_hours': heating_metrics.runtime_hours, 'energy_kwh': energy_kwh, 'cost_sek': cost_sek, 'heat_output_kwh': heat_output, 'cop': heating_metrics.cop}
        if hot_water_metrics and hot_water_metrics.runtime_hours:
            energy_kwh = hot_water_metrics.runtime_hours * self.COMPRESSOR_POWER_AVG_KW
            cost_sek = energy_kwh * electricity_price
            heat_output = energy_kwh * (hot_water_metrics.cop if hot_water_metrics.cop else 2.5)
            result['hot_water'] = {'runtime_hours': hot_water_metrics.runtime_hours, 'energy_kwh': energy_kwh, 'cost_sek': cost_sek, 'heat_output_kwh': heat_output, 'cop': hot_water_metrics.cop}
        result['total'] = {'runtime_hours': result['heating']['runtime_hours'] + result['hot_water']['runtime_hours'], 'energy_kwh': result['heating']['energy_kwh'] + result['hot_water']['energy_kwh'], 'cost_sek': result['heating']['cost_sek'] + result['hot_water']['cost_sek'], 'heat_output_kwh': result['heating']['heat_output_kwh'] + result['hot_water']['heat_output_kwh']}
        if result['total']['runtime_hours'] > 0:
            result['heating']['percent'] = (result['heating']['runtime_hours'] / result['total']['runtime_hours']) * 100
            result['hot_water']['percent'] = (result['hot_water']['runtime_hours'] / result['total']['runtime_hours']) * 100
        return result

    def calculate_optimization_score(self, metrics: EfficiencyMetrics) -> dict:
        score_breakdown = {}
        total_score = 0
        max_score = 0
        if metrics.heating_metrics and metrics.heating_metrics.cop:
            cop = metrics.heating_metrics.cop
            if cop >= self.COP_HEATING_ELITE: cop_score = 30
            elif cop >= self.COP_HEATING_EXCELLENT: cop_score = 25
            elif cop >= self.COP_HEATING_VERY_GOOD: cop_score = 20
            elif cop >= self.COP_HEATING_GOOD: cop_score = 15
            elif cop >= self.COP_HEATING_ACCEPTABLE: cop_score = 10
            else: cop_score = 5
            score_breakdown['heating_cop'] = {'score': cop_score, 'max': 30, 'value': cop}
            total_score += cop_score
        max_score += 30
        if metrics.hot_water_metrics and metrics.hot_water_metrics.cop:
            cop = metrics.hot_water_metrics.cop
            if cop >= self.COP_HOT_WATER_ELITE: cop_score = 20
            elif cop >= self.COP_HOT_WATER_EXCELLENT: cop_score = 16
            elif cop >= self.COP_HOT_WATER_VERY_GOOD: cop_score = 12
            elif cop >= self.COP_HOT_WATER_GOOD: cop_score = 8
            else: cop_score = 4
            score_breakdown['hot_water_cop'] = {'score': cop_score, 'max': 20, 'value': cop}
            total_score += cop_score
        max_score += 20
        if metrics.heating_metrics and metrics.heating_metrics.delta_t:
            delta_t = metrics.heating_metrics.delta_t
            if self.DELTA_T_PERFECT_MIN <= delta_t <= self.DELTA_T_PERFECT_MAX: dt_score = 25
            elif self.DELTA_T_EXCELLENT_MIN <= delta_t <= self.DELTA_T_EXCELLENT_MAX: dt_score = 20
            elif self.DELTA_T_GOOD_MIN <= delta_t <= self.DELTA_T_GOOD_MAX: dt_score = 15
            else: dt_score = 5
            score_breakdown['delta_t'] = {'score': dt_score, 'max': 25, 'value': delta_t}
            total_score += dt_score
        max_score += 25
        dm = metrics.degree_minutes
        if self.TARGET_DM_MIN <= dm <= self.TARGET_DM_MAX: dm_score = 15
        elif dm < self.TARGET_DM_MIN: dm_score = max(0, 15 - abs(dm - self.TARGET_DM_MIN) / 20)
        else: dm_score = max(0, 15 - abs(dm - self.TARGET_DM_MAX) / 10)
        score_breakdown['degree_minutes'] = {'score': dm_score, 'max': 15, 'value': dm}
        total_score += dm_score
        max_score += 15
        if metrics.heating_metrics:
            cycles = metrics.heating_metrics.num_cycles
            runtime = metrics.heating_metrics.runtime_hours or 0
            if cycles > 0 and runtime > 0:
                avg_cycle_length = (runtime * 60) / cycles
                if avg_cycle_length >= 60: cycle_score = 10
                elif avg_cycle_length >= 45: cycle_score = 8
                elif avg_cycle_length >= 30: cycle_score = 6
                elif avg_cycle_length >= 20: cycle_score = 4
                else: cycle_score = 2
                score_breakdown['cycle_efficiency'] = {'score': cycle_score, 'max': 10, 'avg_cycle_minutes': avg_cycle_length}
                total_score += cycle_score
        max_score += 10
        final_score = (total_score / max_score * 100) if max_score > 0 else 0
        if final_score >= 90: rating = {'tier': 'Elite', 'badge': '🏆 ELITE', 'color': '#FFD700'}
        elif final_score >= 80: rating = {'tier': 'Excellent', 'badge': '⭐ EXCELLENT', 'color': '#00D4FF'}
        elif final_score >= 70: rating = {'tier': 'Very Good', 'badge': '✨ VERY GOOD', 'color': '#00FF88'}
        elif final_score >= 60: rating = {'tier': 'Good', 'badge': '✅ GOOD', 'color': '#88FF00'}
        elif final_score >= 50: rating = {'tier': 'Acceptable', 'badge': '👍 OK', 'color': '#FFA500'}
        else: rating = {'tier': 'Poor', 'badge': '⚠️ IMPROVE', 'color': '#FF4444'}
        return {'score': round(final_score, 1), 'rating': rating, 'breakdown': score_breakdown, 'total_points': round(total_score, 1), 'max_points': max_score}

    def analyze_heating_curve(self, metrics: EfficiencyMetrics) -> List[OptimizationOpportunity]:
        opportunities = []
        dm = metrics.degree_minutes
        curve = metrics.heating_curve
        if dm < -300:
            suggested_curve = min(15.0, curve + 0.5)
            opportunities.append(OptimizationOpportunity(parameter_id=self.PARAM_HEATING_CURVE, parameter_name="Heating curve", current_value=curve, suggested_value=suggested_curve, expected_impact="Increase indoor temperature and comfort", reasoning=f"Degree minutes at {dm:.0f} indicates system is too cold. Target is around -200 DM for optimal comfort and efficiency.", confidence=0.85))
        elif dm > -100:
            suggested_curve = max(0.0, curve - 0.5)
            opportunities.append(OptimizationOpportunity(parameter_id=self.PARAM_HEATING_CURVE, parameter_name="Heating curve", current_value=curve, suggested_value=suggested_curve, expected_impact="Reduce energy consumption while maintaining comfort", reasoning=f"Degree minutes at {dm:.0f} indicates system is too warm. Target is around -200 DM for optimal efficiency.", confidence=0.85))
        if metrics.delta_t < 3:
            opportunities.append(OptimizationOpportunity(parameter_id=self.PARAM_CURVE_OFFSET, parameter_name="Curve offset", current_value=metrics.curve_offset, suggested_value=max(-10.0, metrics.curve_offset - 1.0), expected_impact="Reduce supply temperature, improve efficiency", reasoning=f"Supply-return differential is only {metrics.delta_t:.1f}°C. Low differential suggests water is too hot, reducing efficiency. Target differential is 5-8°C.", confidence=0.70))
        elif metrics.delta_t > 10:
            opportunities.append(OptimizationOpportunity(parameter_id=self.PARAM_CURVE_OFFSET, parameter_name="Curve offset", current_value=metrics.curve_offset, suggested_value=min(10.0, metrics.curve_offset + 1.0), expected_impact="Increase heat output to meet demand", reasoning=f"Supply-return differential is {metrics.delta_t:.1f}°C. Large differential suggests insufficient heat output. Target differential is 5-8°C.", confidence=0.70))
        return opportunities

    def analyze_efficiency(self, metrics: EfficiencyMetrics) -> List[OptimizationOpportunity]:
        opportunities = []
        if metrics.estimated_cop and metrics.estimated_cop < 2.5:
            opportunities.append(OptimizationOpportunity(parameter_id=self.PARAM_HEATING_CURVE, parameter_name="System efficiency", current_value=metrics.estimated_cop, suggested_value=3.0, expected_impact="Improve overall system efficiency", reasoning=f"Estimated COP of {metrics.estimated_cop:.2f} is below optimal. This may be due to outdoor temperature, but consider reducing supply temperature if comfort allows. Target COP > 2.5.", confidence=0.60))
        if metrics.compressor_runtime_hours:
            hours_in_period = (metrics.period_end - metrics.period_start).total_seconds() / 3600
            runtime_ratio = metrics.compressor_runtime_hours / hours_in_period
            if runtime_ratio > 0.8:
                opportunities.append(OptimizationOpportunity(parameter_id=self.PARAM_HEATING_CURVE, parameter_name="Compressor runtime", current_value=runtime_ratio * 100, suggested_value=70.0, expected_impact="Reduce compressor wear and allow defrost cycles", reasoning=f"Compressor running {runtime_ratio*100:.0f}% of the time. Continuous operation prevents efficient defrost and increases wear. Consider if heating demand is too high.", confidence=0.75))
        return opportunities

    def generate_recommendations(self, hours_back: int = 24, min_confidence: float = 0.6) -> List[OptimizationOpportunity]:
        logger.info(f"Generating recommendations based on last {hours_back} hours")
        metrics = self.calculate_metrics(hours_back)
        opportunities = []
        opportunities.extend(self.analyze_heating_curve(metrics))
        opportunities.extend(self.analyze_efficiency(metrics))
        opportunities = [o for o in opportunities if o.confidence >= min_confidence]
        opportunities.sort(key=lambda x: x.confidence, reverse=True)
        logger.info(f"Generated {len(opportunities)} recommendations")
        return opportunities

    def save_recommendation(self, opportunity: OptimizationOpportunity) -> Recommendation:
        device = self.get_device()
        param = self.session.query(Parameter).filter_by(parameter_id=opportunity.parameter_id).first()
        recommendation = Recommendation(device_id=device.id, parameter_id=param.id if param else None, current_value=opportunity.current_value, recommended_value=opportunity.suggested_value, expected_impact=opportunity.expected_impact, status='pending')
        self.session.add(recommendation)
        self.session.commit()
        logger.info(f"Saved recommendation: {opportunity.parameter_name} " f"{opportunity.current_value:.1f} → {opportunity.suggested_value:.1f}")
        return recommendation


def main():
    analyzer = HeatPumpAnalyzer()
    logger.info("="*80)
    logger.info("HEAT PUMP EFFICIENCY ANALYSIS")
    logger.info("="*80)
    metrics = analyzer.calculate_metrics(hours_back=24)
    logger.info(f"\nPeriod: {metrics.period_start} to {metrics.period_end}")
    logger.info(f"\nTemperatures:")
    logger.info(f"  Outdoor:  {metrics.avg_outdoor_temp:>6.1f}°C")
    logger.info(f"  Indoor:   {metrics.avg_indoor_temp:>6.1f}°C")
    logger.info(f"  Supply:   {metrics.avg_supply_temp:>6.1f}°C")
    logger.info(f"  Return:   {metrics.avg_return_temp:>6.1f}°C")
    logger.info(f"\nΔT (Supply-Return):")
    logger.info(f"  All readings: {metrics.delta_t:.1f}°C")
    if metrics.delta_t_active is not None: logger.info(f"  Space heating (active): {metrics.delta_t_active:.1f}°C  {'✅' if 3 <= metrics.delta_t_active <= 8 else '⚠️'}")
    if metrics.delta_t_hot_water is not None: logger.info(f"  Hot water production: {metrics.delta_t_hot_water:.1f}°C")
    logger.info(f"\nSystem Status:")
    logger.info(f"  Heating curve: {metrics.heating_curve}")
    logger.info(f"  Curve offset:  {metrics.curve_offset}")
    logger.info(f"  Degree minutes: {metrics.degree_minutes:.0f}")
    logger.info(f"  Avg compressor freq: {metrics.avg_compressor_freq:.0f} Hz")
    if metrics.estimated_cop: logger.info(f"  Estimated COP: {metrics.estimated_cop:.2f}")
    if metrics.compressor_runtime_hours: logger.info(f"  Compressor runtime: {metrics.compressor_runtime_hours:.1f} hours")
    if metrics.heating_metrics:
        logger.info("\n" + "="*80)
        logger.info("SPACE HEATING METRICS")
        logger.info("="*80)
        hm = metrics.heating_metrics
        if hm.cop: logger.info(f"  COP (Heating):        {hm.cop:.2f}")
        if hm.delta_t: logger.info(f"  Delta T:              {hm.delta_t:.1f}°C  {'✅' if 3 <= hm.delta_t <= 8 else '⚠️'}")
        if hm.avg_outdoor_temp: logger.info(f"  Avg Outdoor Temp:     {hm.avg_outdoor_temp:.1f}°C")
        if hm.avg_supply_temp: logger.info(f"  Avg Supply Temp:      {hm.avg_supply_temp:.1f}°C")
        if hm.avg_compressor_freq: logger.info(f"  Avg Compressor Freq:  {hm.avg_compressor_freq:.0f} Hz")
        if hm.runtime_hours: logger.info(f"  Runtime:              {hm.runtime_hours:.1f} hours")
        logger.info(f"  Heating Cycles:       {hm.num_cycles}")
    if metrics.hot_water_metrics:
        logger.info("\n" + "="*80)
        logger.info("HOT WATER PRODUCTION METRICS")
        logger.info("="*80)
        hwm = metrics.hot_water_metrics
        if hwm.cop: logger.info(f"  COP (Hot Water):      {hwm.cop:.2f}")
        if hwm.delta_t: logger.info(f"  Delta T:              {hwm.delta_t:.1f}°C")
        if hwm.avg_hot_water_temp: logger.info(f"  Avg Hot Water Temp:   {hwm.avg_hot_water_temp:.1f}°C")
        if hwm.avg_outdoor_temp: logger.info(f"  Avg Outdoor Temp:     {hwm.avg_outdoor_temp:.1f}°C")
        if hwm.avg_compressor_freq: logger.info(f"  Avg Compressor Freq:  {hwm.avg_compressor_freq:.0f} Hz")
        if hwm.runtime_hours: logger.info(f"  Runtime:              {hwm.runtime_hours:.1f} hours")
        logger.info(f"  Hot Water Cycles:     {hwm.num_cycles}")
    logger.info("\n" + "="*80)
    logger.info("OPTIMIZATION RECOMMENDATIONS")
    logger.info("="*80 + "\n")
    opportunities = analyzer.generate_recommendations(hours_back=24)
    if opportunities:
        for i, opp in enumerate(opportunities, 1):
            logger.info(f"[{i}] {opp.parameter_name}")
            logger.info(f"    Current: {opp.current_value:.1f}")
            logger.info(f"    Suggested: {opp.suggested_value:.1f}")
            logger.info(f"    Impact: {opp.expected_impact}")
            logger.info(f"    Reasoning: {opp.reasoning}")
            logger.info(f"    Confidence: {opp.confidence*100:.0f}%")
            logger.info("")
            analyzer.save_recommendation(opp)
    else:
        logger.info("No optimization opportunities identified.")
        logger.info("System appears to be operating efficiently.")
    logger.info("="*80)


if __name__ == '__main__':
    main()