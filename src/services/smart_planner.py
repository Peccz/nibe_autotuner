"""
Smart Planner V14.0 — Two-Zone Optimizer
Uses deterministic two-zone simulation (floor + radiators) to schedule heating.
Falls back to DB outdoor temps if weather API is unavailable.
"""
import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta, timezone
from loguru import logger

sys.path.append('src')
from core.config import settings
from services.price_service import price_service
from services.weather_service import SMHIWeatherService
from services.optimizer import optimize_24h_plan, predict_temperatures, predict_temperatures_two_zone


def get_db_connection():
    db_path = settings.DATABASE_URL.replace('sqlite:///', '')
    if not os.path.isabs(db_path):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if db_path.startswith('./'):
            db_path = os.path.join(project_root, db_path[2:])
        else:
            db_path = os.path.join(project_root, db_path)
    return sqlite3.connect(db_path)


def _outdoor_fallback_from_db(conn) -> float:
    """Return most recent outdoor temp from DB when weather API is unavailable."""
    try:
        row = conn.execute("""
            SELECT r.value FROM parameter_readings r
            JOIN parameters p ON r.parameter_id = p.id
            WHERE p.parameter_id = '40004'
            ORDER BY r.timestamp DESC LIMIT 1
        """).fetchone()
        if row:
            return float(row[0])
    except Exception:
        pass
    return 5.0  # Safe default for Sweden


def calculate_plan():
    logger.info("Starting V14.0 Two-Zone Optimizer...")
    conn = get_db_connection()
    weather_service = SMHIWeatherService()

    # 0. Load device settings (comfort temps + away mode)
    device_row = conn.execute("""
        SELECT away_mode_enabled, away_mode_end_date,
               target_indoor_temp_min, target_indoor_temp_max,
               min_indoor_temp_user_setting, target_radiator_temp
        FROM devices LIMIT 1
    """).fetchone()

    away_mode = False
    opt_min_temp      = settings.OPTIMIZER_MIN_TEMP
    opt_target_temp   = settings.OPTIMIZER_TARGET_TEMP
    opt_radiator_temp = settings.DEXTER_TARGET_TEMP

    if device_row:
        away_enabled = bool(device_row[0])
        away_end_str = device_row[1]
        away_end = datetime.fromisoformat(away_end_str) if away_end_str else None

        if away_enabled and (away_end is None or away_end > datetime.now()):
            away_mode = True
            opt_min_temp    = 16.0
            opt_target_temp = 17.0
            logger.info("BORTA-LÄGE aktivt — optimerar för 16–17°C")
        else:
            if device_row[2]:
                opt_min_temp = float(device_row[2])
            if device_row[3]:
                opt_target_temp = float(device_row[3])
            if device_row[5]:
                opt_radiator_temp = float(device_row[5])

    # 1. Get current temperatures
    query = """
    SELECT p.parameter_id, r.value
    FROM parameter_readings r
    JOIN parameters p ON r.parameter_id = p.id
    WHERE r.timestamp > datetime('now', '-1 hour')
    AND p.parameter_id IN ('HA_TEMP_DOWNSTAIRS', 'HA_TEMP_DEXTER', '40004')
    ORDER BY r.timestamp DESC
    """
    df = pd.read_sql_query(query, conn)

    dexter     = df[df['parameter_id'] == 'HA_TEMP_DEXTER']['value'].iloc[0] \
                 if not df[df['parameter_id'] == 'HA_TEMP_DEXTER'].empty else None
    downstairs = df[df['parameter_id'] == 'HA_TEMP_DOWNSTAIRS']['value'].iloc[0] \
                 if not df[df['parameter_id'] == 'HA_TEMP_DOWNSTAIRS'].empty else None

    # Priority logic for floor zone start temp
    min_dexter = opt_min_temp - 0.5
    max_dexter = opt_target_temp

    start_floor = opt_target_temp  # fallback

    if downstairs is None:
        start_floor = dexter if dexter is not None else opt_target_temp
    else:
        start_floor = downstairs
        if dexter is not None and dexter < min_dexter:
            dexter_equiv = dexter + 1.5
            if dexter_equiv < start_floor:
                start_floor = dexter_equiv
                logger.info(f"Dexter for kall ({dexter:.2f}C < {min_dexter:.2f}C). Equiv {dexter_equiv:.2f}C som starttemp.")
        elif dexter is not None and dexter > max_dexter:
            dexter_equiv = dexter - 1.5
            if dexter_equiv > start_floor:
                start_floor = dexter_equiv
                logger.info(f"Dexter for varm ({dexter:.2f}C > {max_dexter:.2f}C). Equiv {dexter_equiv:.2f}C som starttemp.")

    # Radiator zone start temp (Dexter's actual reading, or estimated)
    start_radiator = dexter if dexter is not None else (start_floor - 1.0)

    # 2. Get 24h data
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    prices_today    = price_service.get_prices_today()
    prices_tomorrow = price_service.get_prices_tomorrow()
    all_prices      = prices_today + prices_tomorrow

    forecasts = weather_service.get_forecast()

    # Outdoor fallback: if weather API failed, use last known DB outdoor temp
    fallback_outdoor = None
    if not forecasts:
        fallback_outdoor = _outdoor_fallback_from_db(conn)
        logger.warning(f"Weather API unavailable — using DB outdoor fallback: {fallback_outdoor:.1f}°C")

    # Align data to 24h grid
    price_list   = []
    outdoor_list = []

    for i in range(24):
        future_time = now + timedelta(hours=i)

        p_obj = next(
            (p for p in all_prices
             if p.time_start.astimezone(timezone.utc).hour == future_time.hour
             and p.time_start.astimezone(timezone.utc).day  == future_time.day),
            None
        )
        price_list.append(p_obj.price_per_kwh if p_obj else 1.0)

        if forecasts:
            w_obj = next(
                (f for f in forecasts
                 if f.timestamp.hour == future_time.hour
                 and f.timestamp.day  == future_time.day),
                None
            )
            outdoor_list.append(w_obj.temperature if w_obj else fallback_outdoor or 5.0)
        else:
            outdoor_list.append(fallback_outdoor)

    # 3. Run two-zone optimization
    offsets = optimize_24h_plan(
        current_temp          = start_floor,
        outdoor_temps         = outdoor_list,
        prices                = price_list,
        min_temp              = opt_min_temp,
        target_temp           = opt_target_temp,
        current_radiator_temp = start_radiator if not away_mode else None,
        min_radiator_temp     = settings.DEXTER_MIN_TEMP if not away_mode else None,
        target_radiator_temp  = opt_radiator_temp if not away_mode else None,
    )

    # 4. Simulate both zones for plan storage
    floor_temps, rad_temps = predict_temperatures_two_zone(
        start_floor, start_radiator, outdoor_list, offsets
    )

    # 5. Save plan
    plan_rows = []
    for i in range(24):
        future_time = now + timedelta(hours=i)

        action = "RUN"
        if offsets[i] <= settings.OPTIMIZER_REST_THRESHOLD:
            action = "REST"

        plan_rows.append((
            future_time,
            action,
            float(offsets[i]),
            price_list[i],
            floor_temps[i],
            rad_temps[i],
            outdoor_list[i],
            0,  # wind_speed placeholder
        ))

    try:
        conn.execute("BEGIN EXCLUSIVE")
        # Delete from now onwards (keeps past rows for prediction_accuracy validation)
        conn.execute("DELETE FROM planned_heating_schedule WHERE timestamp >= datetime('now')")
        # Prune rows older than 48h to prevent unbounded growth
        conn.execute("DELETE FROM planned_heating_schedule WHERE timestamp < datetime('now', '-48 hours')")
        conn.executemany("""
            INSERT INTO planned_heating_schedule
            (timestamp, planned_action, planned_offset, electricity_price,
             simulated_indoor_temp, simulated_dexter_temp, outdoor_temp, wind_speed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, plan_rows)
        conn.commit()
        logger.success("✓ V14.0 Two-Zone Plan Generated.")
    except Exception as e:
        conn.rollback()
        logger.error(f"✗ Failed to update heating schedule: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    calculate_plan()
