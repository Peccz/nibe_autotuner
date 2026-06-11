"""
Smart Planner V14.0 — Two-Zone Optimizer
Uses deterministic two-zone simulation (floor + radiators) to schedule heating.
Falls back to DB outdoor temps if weather API is unavailable.
"""
import sys
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from loguru import logger

sys.path.append('src')
from core.config import settings
from services.price_service import price_service
from services.weather_service import SMHIWeatherService
from services.optimizer import optimize_24h_plan, predict_temperatures, predict_temperatures_two_zone
from services.v15_mpc import compare_shadow_summary, plan_v15_shadow, plan_v16_robust
from services.outdoor_temperature import effective_outdoor_temp_from_recent_sensor_values
from services.ventilation_guard import ZoneReading, detect_ventilation_events
from services.comfort_profile import (
    DAY_DEXTER_MAX_C,
    DAY_DEXTER_MIN_C,
    DAY_FLOOR_MAX_C,
    DAY_FLOOR_MIN_C,
    comfort_bounds_for_time,
    to_local,
)

HA_SENSOR_MAX_AGE_MINUTES = 30
DEFAULT_DEXTER_GAP_C = -1.0
FLOOR_COMFORT_MIN_C = DAY_FLOOR_MIN_C
FLOOR_COMFORT_MAX_C = DAY_FLOOR_MAX_C
DEXTER_COMFORT_MIN_C = DAY_DEXTER_MIN_C
DEXTER_COMFORT_MAX_C = DAY_DEXTER_MAX_C


def _load_calibration(conn):
    """Return (k_leak, k_gain_floor) from latest calibration row, or config defaults."""
    try:
        row = conn.execute("""
            SELECT k_leak, k_gain_floor FROM calibration_history
            ORDER BY date DESC LIMIT 1
        """).fetchone()
        if row:
            logger.info(f"Using calibrated constants: K_LEAK={row[0]:.5f}, K_GAIN_FLOOR={row[1]:.4f}")
            return float(row[0]), float(row[1])
    except Exception as e:
        logger.warning(f"Could not load calibration: {e}")
    return settings.OPTIMIZER_K_LEAK, settings.K_GAIN_FLOOR


def _get_vv_must_run_hours(conn, now) -> set:
    """Return set of hour indices (0–23 within next 24h) that should not be REST.
    Index i = hour i from now. Includes confirmed VV hours and their pre-heat (i-1).
    Requires >= 3 historical observations and mean duration >= 15 minutes."""
    candidates = {}
    try:
        rows = conn.execute("""
            SELECT hour, weekday, COUNT(*) as n, AVG(duration_minutes) as avg_duration
            FROM hot_water_usage
            WHERE end_time IS NOT NULL
              AND duration_minutes IS NOT NULL
            GROUP BY hour, weekday
            HAVING COUNT(*) >= 3 AND AVG(duration_minutes) >= 15
        """).fetchall()
        if not rows:
            return set()
        pattern = {(int(r[0]), int(r[1])): (int(r[2]), float(r[3] or 0.0)) for r in rows}
        for i in range(24):
            future = now + timedelta(hours=i)
            stats = pattern.get((future.hour, future.weekday()))
            if stats:
                n, avg_duration = stats
                score = n * avg_duration
                candidates[i] = max(candidates.get(i, 0.0), score * 2.0)  # VV hour itself
                if i > 0:
                    candidates[i - 1] = max(candidates.get(i - 1, 0.0), score)  # pre-heat hour

        if len(candidates) > 4:
            logger.warning(
                f"VV pre-heat matched {len(candidates)} hours; limiting REST block to 4 strongest hours"
            )
        must_run = {
            h for h, _ in sorted(candidates.items(), key=lambda item: (-item[1], item[0]))[:4]
        }
        if must_run:
            logger.info(f"VV pre-heat: must_run_hours={sorted(must_run)}")
    except Exception as e:
        logger.warning(f"VV pattern query failed: {e}")
        return set()
    return must_run


def _parse_db_timestamp(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def _get_latest_readings(conn, parameter_ids, now, max_age_days=14):
    placeholders = ",".join("?" for _ in parameter_ids)
    rows = conn.execute(f"""
        SELECT p.parameter_id, r.value, r.timestamp
        FROM parameter_readings r
        JOIN parameters p ON r.parameter_id = p.id
        WHERE r.timestamp > ?
          AND p.parameter_id IN ({placeholders})
        ORDER BY r.timestamp DESC
    """, (now - timedelta(days=max_age_days), *parameter_ids)).fetchall()

    latest = {}
    for parameter_id, value, timestamp in rows:
        if parameter_id not in latest:
            latest[parameter_id] = (float(value), _parse_db_timestamp(timestamp))
    return latest


def _avg_same_timestamp_gap(conn, warm_param, base_param, default_gap, now, days=14):
    try:
        row = conn.execute("""
            SELECT AVG(warm.value - base.value)
            FROM parameter_readings warm
            JOIN parameters warm_p ON warm.parameter_id = warm_p.id
            JOIN parameter_readings base ON base.timestamp = warm.timestamp
            JOIN parameters base_p ON base.parameter_id = base_p.id
            WHERE warm_p.parameter_id = ?
              AND base_p.parameter_id = ?
              AND warm.timestamp > ?
        """, (warm_param, base_param, now - timedelta(days=days))).fetchone()
        if row and row[0] is not None:
            return float(row[0])
    except Exception as e:
        logger.debug(f"Could not calculate historical gap {warm_param}-{base_param}: {e}")
    return default_gap


def _avg_bucketed_bt50_downstairs_gap(conn, default_gap, now, days=30, bucket_seconds=300, min_pairs=24):
    """Calibrate BT50 to downstairs HA using 5-minute buckets.

    BT50 and IKEA/HA readings are not always written with identical timestamps.
    Bucket matching avoids falling back to 0.0 just because the seconds differ.
    """
    try:
        row = conn.execute("""
            WITH readings AS (
                SELECT p.parameter_id, r.value, CAST(strftime('%s', r.timestamp) / ? AS INTEGER) AS bucket
                FROM parameter_readings r
                JOIN parameters p ON r.parameter_id = p.id
                WHERE p.parameter_id IN ('HA_TEMP_DOWNSTAIRS', '40033')
                  AND r.timestamp > ?
                  AND r.value BETWEEN 10.0 AND 30.0
            ),
            bucketed AS (
                SELECT parameter_id, bucket, AVG(value) AS value
                FROM readings
                GROUP BY parameter_id, bucket
            ),
            gaps AS (
                SELECT down.value - bt.value AS gap
                FROM bucketed down
                JOIN bucketed bt ON bt.bucket = down.bucket
                WHERE down.parameter_id = 'HA_TEMP_DOWNSTAIRS'
                  AND bt.parameter_id = '40033'
                  AND ABS(down.value - bt.value) <= 2.0
            )
            SELECT COUNT(*), AVG(gap)
            FROM gaps
        """, (bucket_seconds, now - timedelta(days=days))).fetchone()
        if row and int(row[0] or 0) >= min_pairs and row[1] is not None:
            return float(row[1])
    except Exception as e:
        logger.debug(f"Could not calculate bucketed BT50 calibration gap: {e}")
    return default_gap


def _resolve_zone_temperatures(conn, now, opt_target_temp):
    latest = _get_latest_readings(
        conn,
        ["HA_TEMP_DOWNSTAIRS", "HA_TEMP_DEXTER", "40033"],
        now,
    )

    def is_fresh(parameter_id):
        reading = latest.get(parameter_id)
        if not reading:
            return False
        return now - reading[1] <= timedelta(minutes=HA_SENSOR_MAX_AGE_MINUTES)

    downstairs = latest["HA_TEMP_DOWNSTAIRS"][0] if is_fresh("HA_TEMP_DOWNSTAIRS") else None
    dexter = latest["HA_TEMP_DEXTER"][0] if is_fresh("HA_TEMP_DEXTER") else None
    sensor_mode = "normal"

    if downstairs is None or dexter is None:
        sensor_mode = "fallback"
        bt50 = latest.get("40033")
        bt50_fresh = bool(bt50 and now - bt50[1] <= timedelta(minutes=HA_SENSOR_MAX_AGE_MINUTES))

        if downstairs is None:
            if bt50_fresh:
                downstairs_bt50_gap = _avg_bucketed_bt50_downstairs_gap(
                    conn, default_gap=0.0, now=now
                )
                downstairs = bt50[0] + downstairs_bt50_gap
                logger.warning(
                    f"sensor_mode=fallback downstairs={downstairs:.2f}C from BT50 "
                    f"{bt50[0]:.2f}C gap {downstairs_bt50_gap:+.2f}C"
                )
            else:
                downstairs = dexter if dexter is not None else opt_target_temp
                logger.warning("sensor_mode=fallback no fresh downstairs/BT50; using conservative target fallback")

        if dexter is None:
            dexter_gap = _avg_same_timestamp_gap(
                conn, "HA_TEMP_DEXTER", "HA_TEMP_DOWNSTAIRS", DEFAULT_DEXTER_GAP_C, now
            )
            dexter = downstairs + dexter_gap
            logger.warning(
                f"sensor_mode=fallback dexter={dexter:.2f}C from downstairs "
                f"{downstairs:.2f}C gap {dexter_gap:+.2f}C"
            )

    logger.info(
        f"sensor_mode={sensor_mode} start_downstairs={downstairs:.2f}C start_dexter={dexter:.2f}C"
    )
    return downstairs, dexter, sensor_mode


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
    """Return filtered recent outdoor temp from DB when weather API is unavailable."""
    try:
        rows = conn.execute("""
            SELECT r.value
            FROM parameter_readings r
            JOIN parameters p ON r.parameter_id = p.id
            WHERE p.parameter_id = '40004'
              AND r.timestamp > datetime('now', '-6 hours')
            ORDER BY r.timestamp DESC
            LIMIT 72
        """).fetchall()
        filtered = effective_outdoor_temp_from_recent_sensor_values([r[0] for r in rows])
        if filtered is not None:
            return filtered
    except Exception:
        pass
    return 5.0  # Safe default for Sweden


def _replace_future_plan_rows(conn, plan_start: datetime, plan_rows):
    """Replace the active horizon from the same timestamp used for new rows."""
    conn.execute("DELETE FROM planned_heating_schedule WHERE timestamp >= ?", (plan_start,))
    conn.execute("DELETE FROM planned_heating_schedule WHERE timestamp < datetime('now', '-48 hours')")
    conn.executemany("""
        INSERT INTO planned_heating_schedule
        (timestamp, planned_action, planned_offset, electricity_price,
         simulated_indoor_temp, simulated_dexter_temp, outdoor_temp, wind_speed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, plan_rows)


def _build_comfort_profiles(start_utc: datetime, hours: int):
    floor_min = []
    floor_max = []
    dexter_min = []
    dexter_max = []
    boost_allowed = set()
    profile_counts = {}

    for i in range(hours):
        bounds = comfort_bounds_for_time(start_utc + timedelta(hours=i))
        floor_min.append(bounds["floor_min"])
        floor_max.append(bounds.get("planning_floor_max", bounds["floor_max"]))
        dexter_min.append(bounds["dexter_min"])
        dexter_max.append(bounds.get("planning_dexter_max", bounds["dexter_max"]))
        if bounds["boost_allowed"]:
            boost_allowed.add(i)
        profile_counts[bounds["profile"]] = profile_counts.get(bounds["profile"], 0) + 1

    return floor_min, floor_max, dexter_min, dexter_max, boost_allowed, profile_counts


def _calculate_room_heat_surplus(start_floor: float, start_radiator: float, bounds: dict) -> float:
    """Estimate room heat surplus above the active planning upper band."""
    floor_max = bounds.get("planning_floor_max", bounds["floor_max"])
    dexter_max = bounds.get("planning_dexter_max", bounds["dexter_max"])
    floor_surplus = max(0.0, float(start_floor) - float(floor_max))
    dexter_surplus = max(0.0, float(start_radiator) - float(dexter_max))
    return min(2.0, max(floor_surplus, dexter_surplus))


def _load_ventilation_readings(conn, now: datetime) -> dict:
    """Load recent zone readings for local ventilation disturbance detection."""
    parameter_map = {
        "floor": "HA_TEMP_DOWNSTAIRS",
        "dexter": "HA_TEMP_DEXTER",
        "bt50": "40033",
    }
    readings = {zone: [] for zone in parameter_map}
    try:
        rows = conn.execute("""
            SELECT p.parameter_id, r.value, r.timestamp
            FROM parameter_readings r
            JOIN parameters p ON r.parameter_id = p.id
            WHERE r.timestamp >= ?
              AND p.parameter_id IN ('HA_TEMP_DOWNSTAIRS', 'HA_TEMP_DEXTER', '40033')
            ORDER BY r.timestamp
        """, (now - timedelta(hours=2),)).fetchall()
        reverse_map = {parameter: zone for zone, parameter in parameter_map.items()}
        for parameter_id, value, timestamp in rows:
            zone = reverse_map.get(parameter_id)
            if zone:
                readings[zone].append(ZoneReading(_parse_db_timestamp(timestamp), float(value)))
    except Exception as e:
        logger.debug(f"ventilation_guard reading query failed: {e}")
    return readings


def _log_ventilation_events(events):
    if not events:
        return
    parts = [
        (
            f"{event.zone}:drop={event.temp_drop:.2f}C "
            f"ref_drop={event.reference_drop:.2f}C conf={event.confidence:.2f} "
            f"until={event.active_until.isoformat()}"
        )
        for event in events
    ]
    logger.warning("ventilation_event active " + "; ".join(parts))


def _calculate_heat_in_flight(conn, now: datetime) -> float:
    """Estimate residual heat already in the hydronic system, in degC forecast bias."""
    score = 0.0
    try:
        rows = conn.execute("""
            SELECT supply_actual, supply_target, action, gm_written, timestamp
            FROM gm_transactions
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
        """, (now - timedelta(minutes=60),)).fetchall()
        positive_surplus = [
            max(0.0, float(row[0]) - float(row[1]))
            for row in rows
            if row[0] is not None and row[1] is not None
        ]
        if positive_surplus:
            score += min(1.0, (sum(positive_surplus) / len(positive_surplus)) / 15.0)

        hot_supply = [
            max(0.0, float(row[0]) - 35.0)
            for row in rows
            if row[0] is not None
        ]
        if hot_supply:
            score += min(0.5, (sum(hot_supply) / len(hot_supply)) / 30.0)

        recent_boost = any(str(row[2]) == "BOOST" or (row[3] is not None and float(row[3]) <= -300) for row in rows)
        if recent_boost:
            score += 0.25
    except Exception as e:
        logger.debug(f"heat_in_flight GM query failed: {e}")

    try:
        row = conn.execute("""
            SELECT MAX(planned_offset)
            FROM planned_heating_schedule
            WHERE timestamp >= ? AND timestamp < ?
        """, (now - timedelta(hours=2), now)).fetchone()
        if row and row[0] is not None and float(row[0]) > 0.0:
            score += min(0.35, float(row[0]) * 0.08)
    except Exception as e:
        logger.debug(f"heat_in_flight plan query failed: {e}")

    return min(1.6, max(0.0, score))


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
    opt_min_temp      = FLOOR_COMFORT_MIN_C
    opt_target_temp   = FLOOR_COMFORT_MAX_C
    opt_radiator_min  = DEXTER_COMFORT_MIN_C
    opt_radiator_temp = DEXTER_COMFORT_MAX_C

    if device_row:
        away_enabled = bool(device_row[0])
        away_end_str = device_row[1]
        away_end = datetime.fromisoformat(away_end_str) if away_end_str else None

        if away_enabled and (away_end is None or away_end > datetime.now()):
            away_mode = True
            opt_min_temp    = 16.0
            opt_target_temp = 17.0
            opt_radiator_min = None
            opt_radiator_temp = None
            logger.info("BORTA-LÄGE aktivt — optimerar för 16–17°C")
        else:
            opt_min_temp = FLOOR_COMFORT_MIN_C
            opt_target_temp = FLOOR_COMFORT_MAX_C
            opt_radiator_min = DEXTER_COMFORT_MIN_C
            opt_radiator_temp = DEXTER_COMFORT_MAX_C

    # Priority logic for floor zone start temp
    # 1. Get current temperatures. HA/IKEA sensors older than 30 minutes are
    # stale; continue with BT50 + historical zone gaps without changing schema.
    # Use naive UTC throughout — SQLite/SQLAlchemy can't handle tz-aware timestamps
    # stored by sqlite3 raw connections (parameter_readings uses naive, plan must match)
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    sensor_now = datetime.utcnow().replace(microsecond=0)
    downstairs, dexter, sensor_mode = _resolve_zone_temperatures(conn, sensor_now, opt_target_temp)

    current_bounds = comfort_bounds_for_time(sensor_now)
    min_dexter = current_bounds["dexter_min"] if not away_mode else opt_min_temp - 0.5
    max_dexter = current_bounds["dexter_max"] if not away_mode else opt_target_temp

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
    wind_list    = []
    cloud_list   = []
    price_fallback_hours = set()

    for i in range(24):
        future_time = now + timedelta(hours=i)

        p_obj = next(
            (p for p in all_prices
             if p.time_start.astimezone(timezone.utc).hour == future_time.hour
             and p.time_start.astimezone(timezone.utc).day  == future_time.day),
            None
        )
        if p_obj:
            price_list.append(p_obj.price_per_kwh)
        else:
            price_list.append(price_service.FALLBACK_PRICE_SEK)
            price_fallback_hours.add(i)

        if forecasts:
            w_obj = next(
                (f for f in forecasts
                 if f.timestamp.hour == future_time.hour
                 and f.timestamp.day  == future_time.day),
                None
            )
            outdoor_list.append(w_obj.temperature if w_obj else fallback_outdoor or 5.0)
            wind_list.append(float(w_obj.wind_speed) if w_obj else 0.0)
            cloud_list.append(float(w_obj.cloud_cover) if w_obj else 8.0)
        else:
            outdoor_list.append(fallback_outdoor)
            wind_list.append(0.0)
            cloud_list.append(8.0)

    # 3. Load calibrated constants and VV patterns
    cal_k_leak, cal_k_gain = _load_calibration(conn)
    must_run = _get_vv_must_run_hours(conn, now) if not away_mode else set()
    if away_mode:
        floor_min_profile = [opt_min_temp] * 24
        floor_max_profile = [opt_target_temp] * 24
        dexter_min_profile = [opt_min_temp - 0.5] * 24
        dexter_max_profile = [opt_target_temp] * 24
        boost_allowed = set()
        profile_counts = {"away": 24}
    else:
        (
            floor_min_profile,
            floor_max_profile,
            dexter_min_profile,
            dexter_max_profile,
            boost_allowed,
            profile_counts,
        ) = _build_comfort_profiles(now, 24)
    logger.info(
        f"comfort_profile local_start={to_local(now).isoformat()} "
        f"profiles={profile_counts} boost_allowed={sorted(boost_allowed)}"
    )
    heat_in_flight = _calculate_heat_in_flight(conn, sensor_now)
    current_bounds = comfort_bounds_for_time(now)
    room_heat_surplus = _calculate_room_heat_surplus(start_floor, start_radiator, current_bounds)
    ventilation_events = detect_ventilation_events(_load_ventilation_readings(conn, sensor_now), sensor_now)
    _log_ventilation_events(ventilation_events)
    logger.info(
        f"lag_state heat_in_flight={heat_in_flight:.2f}C "
        f"room_heat_surplus={room_heat_surplus:.2f}C profile={current_bounds['profile']}"
    )

    # 4. Run two-zone optimization
    offsets = optimize_24h_plan(
        current_temp          = start_floor,
        outdoor_temps         = outdoor_list,
        prices                = price_list,
        min_temp              = floor_min_profile,
        target_temp           = floor_max_profile,
        current_radiator_temp = start_radiator if not away_mode else None,
        min_radiator_temp     = dexter_min_profile if not away_mode else None,
        target_radiator_temp  = dexter_max_profile if not away_mode else None,
        must_run_hours        = must_run,
        boost_allowed_hours   = boost_allowed,
        heat_in_flight        = heat_in_flight,
        room_heat_surplus     = room_heat_surplus,
        lead_shed_hours       = 4,
        k_leak                = cal_k_leak,
        k_gain_floor          = cal_k_gain,
    )

    try:
        v15_shadow = plan_v15_shadow(
            start_utc          = now,
            start_floor        = start_floor,
            start_dexter       = start_radiator,
            outdoor_temps      = outdoor_list,
            prices             = price_list,
            wind_speeds        = wind_list,
            cloud_cover        = cloud_list,
            must_run_hours     = must_run,
            heat_in_flight     = heat_in_flight,
            room_heat_surplus  = room_heat_surplus,
            k_leak_floor       = cal_k_leak,
            k_gain_floor       = cal_k_gain,
            ventilation_events = ventilation_events,
        )
        shadow = compare_shadow_summary(offsets, v15_shadow, price_list)
        logger.info(
            "v15_shadow "
            f"actions={{'REST': {shadow.get('v15_rest', 0)}, "
            f"'RUN': {v15_shadow.actions.count('RUN')}, "
            f"'BOOST': {shadow.get('v15_boost', 0)}}} "
            f"min_floor={shadow.get('v15_min_floor', 0.0):.2f}C "
            f"min_dexter={shadow.get('v15_min_dexter', 0.0):.2f}C "
            f"weighted_price={shadow.get('v15_weighted_price', 0.0):.3f} "
            f"vs_v14={shadow.get('v14_weighted_price', 0.0):.3f} "
            f"reasons={v15_shadow.reasons} first_offsets={v15_shadow.offsets[:6]}"
        )
    except Exception as e:
        v15_shadow = None
        logger.warning(f"v15_shadow failed: {e}")

    try:
        v16_plan = plan_v16_robust(
            start_utc            = now,
            start_floor          = start_floor,
            start_dexter         = start_radiator,
            outdoor_temps        = outdoor_list,
            prices               = price_list,
            wind_speeds          = wind_list,
            cloud_cover          = cloud_list,
            must_run_hours       = must_run,
            heat_in_flight       = heat_in_flight,
            room_heat_surplus    = room_heat_surplus,
            k_leak_floor         = cal_k_leak,
            k_gain_floor         = cal_k_gain,
            ventilation_events   = ventilation_events,
            price_fallback_hours = price_fallback_hours,
            sensor_mode          = sensor_mode,
        )
        logger.info(
            "v16_candidate "
            f"actions={{'REST': {v16_plan.actions.count('REST')}, "
            f"'RUN': {v16_plan.actions.count('RUN')}, "
            f"'BOOST': {v16_plan.actions.count('BOOST')}}} "
            f"min_floor={min(v16_plan.floor_temps):.2f}C "
            f"max_floor={max(v16_plan.floor_temps):.2f}C "
            f"min_dexter={min(v16_plan.dexter_temps):.2f}C "
            f"max_dexter={max(v16_plan.dexter_temps):.2f}C "
            f"sensor_mode={sensor_mode} price_fallback_hours={sorted(price_fallback_hours)} "
            f"reasons={v16_plan.reasons} first_offsets={v16_plan.offsets[:6]}"
        )
    except Exception as e:
        v16_plan = None
        logger.warning(f"v16_candidate failed: {e}")

    planner_engine = str(getattr(settings, "PLANNER_ENGINE", "v15_shadow")).lower()
    active_offsets = offsets
    active_engine = "v14"
    if planner_engine == "v16_active" and v16_plan is not None:
        active_offsets = v16_plan.offsets
        active_engine = "v16"
        logger.warning("PLANNER_ENGINE=v16_active — writing V16 robust plan to planned_heating_schedule")
    elif planner_engine == "v16_active":
        logger.warning("PLANNER_ENGINE=v16_active requested but V16 failed; falling back to V15/V14 writer")
        if v15_shadow is not None:
            active_offsets = v15_shadow.offsets
            active_engine = "v15"
    elif planner_engine == "v15_active" and v15_shadow is not None:
        active_offsets = v15_shadow.offsets
        active_engine = "v15"
        logger.warning("PLANNER_ENGINE=v15_active — writing V15 plan to planned_heating_schedule")
    elif planner_engine == "v15_active":
        logger.warning("PLANNER_ENGINE=v15_active requested but V15 failed; falling back to V14 writer")
    elif planner_engine not in ("v14", "v15_shadow"):
        logger.warning(f"Unknown PLANNER_ENGINE={planner_engine}; using V14 writer")

    # 5. Simulate both zones for plan storage (use same calibrated constants)
    if active_engine == "v16" and v16_plan is not None:
        floor_temps, rad_temps = v16_plan.floor_temps, v16_plan.dexter_temps
    elif active_engine == "v15" and v15_shadow is not None:
        floor_temps, rad_temps = v15_shadow.floor_temps, v15_shadow.dexter_temps
    else:
        floor_temps, rad_temps = predict_temperatures_two_zone(
            start_floor, start_radiator, outdoor_list, active_offsets,
            k_leak_floor=cal_k_leak, k_gain_floor=cal_k_gain,
        )

    # 6. Save plan
    plan_rows = []
    for i in range(24):
        future_time = now + timedelta(hours=i)

        action = "RUN"
        if active_offsets[i] <= settings.OPTIMIZER_REST_THRESHOLD:
            action = "REST"
        elif active_offsets[i] > 0.0:
            action = "BOOST"

        plan_rows.append((
            future_time,
            action,
            float(active_offsets[i]),
            price_list[i],
            floor_temps[i],
            rad_temps[i],
            outdoor_list[i],
            wind_list[i],
        ))

    action_counts = {}
    for _, action, *_ in plan_rows:
        action_counts[action] = action_counts.get(action, 0) + 1
    logger.info(
        f"planned_actions={action_counts} engine={active_engine} "
        f"min_offset={min(active_offsets):.1f} max_offset={max(active_offsets):.1f}"
    )

    try:
        conn.execute("BEGIN EXCLUSIVE")
        _replace_future_plan_rows(conn, now, plan_rows)
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
