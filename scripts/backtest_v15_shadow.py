#!/usr/bin/env python3
"""Compare historical V14 plan rows with the V15 shadow planner.

The script is read-only. It uses historical temperatures, prices and forecast
values already present in SQLite and prints aggregate comfort/price/action
metrics for V14 vs V15.
"""
import argparse
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional

os.environ.setdefault("MYUPLINK_CLIENT_ID", "backtest-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "backtest-secret")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.config import settings
from services.comfort_profile import comfort_bounds_for_time
from services.optimizer import predict_temperatures_two_zone
from services.v15_mpc import compare_shadow_summary, plan_v15_shadow


@dataclass(frozen=True)
class PlanPoint:
    timestamp: datetime
    action: str
    offset: float
    price: float
    outdoor: float
    wind: float
    cloud: float


@dataclass
class WindowResult:
    start: datetime
    start_floor: float
    start_dexter: float
    v14_rest: int
    v15_rest: int
    v14_boost: int
    v15_boost: int
    v14_min_floor: float
    v15_min_floor: float
    v14_min_dexter: float
    v15_min_dexter: float
    v14_under_floor_hours: int
    v15_under_floor_hours: int
    v14_over_floor_hours: int
    v15_over_floor_hours: int
    v14_avoidable_over_hours: int
    v15_avoidable_over_hours: int
    v14_weighted_price: float
    v15_weighted_price: float


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def _sql_ts(value: datetime) -> str:
    return value.isoformat(sep=" ")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _parameter_db_id(conn: sqlite3.Connection, parameter_id: str) -> Optional[int]:
    row = conn.execute("SELECT id FROM parameters WHERE parameter_id = ?", (parameter_id,)).fetchone()
    return int(row["id"]) if row else None


def _latest_value(
    conn: sqlite3.Connection,
    parameter_id: str,
    at: datetime,
    max_age_hours: float,
) -> Optional[float]:
    db_id = _parameter_db_id(conn, parameter_id)
    if db_id is None:
        return None
    row = conn.execute(
        """
        SELECT value, timestamp
        FROM parameter_readings
        WHERE parameter_id = ?
          AND timestamp <= ?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (db_id, _sql_ts(at)),
    ).fetchone()
    if not row:
        return None
    ts = _parse_dt(row["timestamp"])
    if at - ts > timedelta(hours=max_age_hours):
        return None
    return float(row["value"])


def _plan_window(conn: sqlite3.Connection, start: datetime, hours: int) -> List[PlanPoint]:
    rows = conn.execute(
        """
        SELECT timestamp, planned_action, planned_offset, electricity_price,
               outdoor_temp, wind_speed, cloud_cover
        FROM planned_heating_schedule
        WHERE timestamp >= ?
        ORDER BY timestamp
        LIMIT ?
        """,
        (_sql_ts(start), hours),
    ).fetchall()
    if len(rows) < hours:
        return []
    return [
        PlanPoint(
            timestamp=_parse_dt(row["timestamp"]),
            action=str(row["planned_action"] or "RUN"),
            offset=float(row["planned_offset"] or 0.0),
            price=float(row["electricity_price"] or 1.0),
            outdoor=float(row["outdoor_temp"] if row["outdoor_temp"] is not None else 5.0),
            wind=float(row["wind_speed"] or 0.0),
            cloud=float(row["cloud_cover"] if row["cloud_cover"] is not None else 8.0),
        )
        for row in rows
    ]


def _candidate_starts(
    conn: sqlite3.Connection,
    start: datetime,
    end: datetime,
    stride_hours: int,
) -> Iterable[datetime]:
    rows = conn.execute(
        """
        SELECT timestamp
        FROM planned_heating_schedule
        WHERE timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp
        """,
        (_sql_ts(start), _sql_ts(end)),
    ).fetchall()
    stride_hours = max(1, stride_hours)
    for index, row in enumerate(rows):
        if index % stride_hours == 0:
            yield _parse_dt(row["timestamp"])


def _weighted_price(offsets: List[float], prices: List[float]) -> float:
    load = [max(0.0, offset - settings.OPTIMIZER_MIN_OFFSET) for offset in offsets]
    total = sum(load)
    if total <= 0:
        return 0.0
    return sum(load[i] * prices[i] for i in range(len(offsets))) / total


def _count_band_hours(floor_temps, dexter_temps, start: datetime, under: bool) -> int:
    count = 0
    for i, (floor, dexter) in enumerate(zip(floor_temps, dexter_temps)):
        bounds = comfort_bounds_for_time(start + timedelta(hours=i))
        floor_max = bounds.get("planning_floor_max", bounds["floor_max"])
        dexter_max = bounds.get("planning_dexter_max", bounds["dexter_max"])
        if under:
            if floor < bounds["floor_min"] - 0.05 or dexter < bounds["dexter_min"] - 0.05:
                count += 1
        else:
            if floor > floor_max + 0.05 or dexter > dexter_max + 0.05:
                count += 1
    return count


def _count_avoidable_overheat_hours(floor_temps, dexter_temps, start: datetime) -> int:
    count = 0
    for i, (floor, dexter) in enumerate(zip(floor_temps, dexter_temps)):
        bounds = comfort_bounds_for_time(start + timedelta(hours=i))
        floor_max = bounds.get("planning_floor_max", bounds["floor_max"])
        dexter_max = bounds.get("planning_dexter_max", bounds["dexter_max"])
        overheated = floor > floor_max + 0.05 or dexter > dexter_max + 0.05
        floor_margin = floor - bounds["floor_min"]
        dexter_margin = dexter - bounds["dexter_min"]
        if overheated and floor_margin > 0.25 and dexter_margin > 0.25:
            count += 1
    return count


def evaluate_window(conn: sqlite3.Connection, start: datetime, hours: int = 24) -> Optional[WindowResult]:
    points = _plan_window(conn, start, hours)
    if not points:
        return None

    start_floor = _latest_value(conn, "HA_TEMP_DOWNSTAIRS", start, max_age_hours=3.0)
    start_dexter = _latest_value(conn, "HA_TEMP_DEXTER", start, max_age_hours=3.0)
    if start_floor is None or start_dexter is None:
        return None

    offsets = [p.offset for p in points]
    prices = [p.price for p in points]
    outdoor = [p.outdoor for p in points]
    wind = [p.wind for p in points]
    cloud = [p.cloud for p in points]

    v14_floor, v14_dexter = predict_temperatures_two_zone(
        start_floor,
        start_dexter,
        outdoor,
        offsets,
    )
    v15 = plan_v15_shadow(
        start_utc=start,
        start_floor=start_floor,
        start_dexter=start_dexter,
        outdoor_temps=outdoor,
        prices=prices,
        wind_speeds=wind,
        cloud_cover=cloud,
    )
    shadow = compare_shadow_summary(offsets, v15, prices)

    return WindowResult(
        start=start,
        start_floor=start_floor,
        start_dexter=start_dexter,
        v14_rest=sum(1 for offset in offsets if offset <= settings.OPTIMIZER_REST_THRESHOLD),
        v15_rest=int(shadow.get("v15_rest", 0)),
        v14_boost=sum(1 for offset in offsets if offset > 0.0),
        v15_boost=int(shadow.get("v15_boost", 0)),
        v14_min_floor=min(v14_floor),
        v15_min_floor=min(v15.floor_temps),
        v14_min_dexter=min(v14_dexter),
        v15_min_dexter=min(v15.dexter_temps),
        v14_under_floor_hours=_count_band_hours(v14_floor, v14_dexter, start, under=True),
        v15_under_floor_hours=_count_band_hours(v15.floor_temps, v15.dexter_temps, start, under=True),
        v14_over_floor_hours=_count_band_hours(v14_floor, v14_dexter, start, under=False),
        v15_over_floor_hours=_count_band_hours(v15.floor_temps, v15.dexter_temps, start, under=False),
        v14_avoidable_over_hours=_count_avoidable_overheat_hours(v14_floor, v14_dexter, start),
        v15_avoidable_over_hours=_count_avoidable_overheat_hours(v15.floor_temps, v15.dexter_temps, start),
        v14_weighted_price=_weighted_price(offsets, prices),
        v15_weighted_price=float(shadow.get("v15_weighted_price", 0.0)),
    )


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def print_summary(results: List[WindowResult]) -> None:
    if not results:
        print("No comparable windows found. Check DB path, date range and HA sensor availability.")
        return

    print(f"Comparable windows: {len(results)}")
    print(f"Period: {results[0].start} -> {results[-1].start}")
    print()
    print("Metric                         V14        V15        Delta")
    print("-----------------------------  ---------  ---------  ---------")

    rows = [
        ("REST h / window", _mean([r.v14_rest for r in results]), _mean([r.v15_rest for r in results])),
        ("BOOST h / window", _mean([r.v14_boost for r in results]), _mean([r.v15_boost for r in results])),
        ("min floor C", _mean([r.v14_min_floor for r in results]), _mean([r.v15_min_floor for r in results])),
        ("min Dexter C", _mean([r.v14_min_dexter for r in results]), _mean([r.v15_min_dexter for r in results])),
        ("under floor h", _mean([r.v14_under_floor_hours for r in results]), _mean([r.v15_under_floor_hours for r in results])),
        ("over upper h", _mean([r.v14_over_floor_hours for r in results]), _mean([r.v15_over_floor_hours for r in results])),
        ("avoidable over h", _mean([r.v14_avoidable_over_hours for r in results]), _mean([r.v15_avoidable_over_hours for r in results])),
        ("weighted price", _mean([r.v14_weighted_price for r in results]), _mean([r.v15_weighted_price for r in results])),
    ]
    for label, v14, v15 in rows:
        print(f"{label:<29}  {v14:>9.2f}  {v15:>9.2f}  {v15 - v14:>9.2f}")

    worst_v15 = min(results, key=lambda r: min(r.v15_min_floor, r.v15_min_dexter))
    print()
    print(
        "Worst V15 comfort window: "
        f"{worst_v15.start} floor={worst_v15.v15_min_floor:.2f}C "
        f"dexter={worst_v15.v15_min_dexter:.2f}C"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/nibe_autotuner.db", help="SQLite DB path")
    parser.add_argument("--start", required=True, help="Start timestamp, e.g. 2026-05-10T08:00:00")
    parser.add_argument("--end", required=True, help="End timestamp, e.g. 2026-05-13T06:00:00")
    parser.add_argument("--stride-hours", type=int, default=1, help="Evaluate every Nth hourly plan window")
    parser.add_argument("--hours", type=int, default=24, help="Planning horizon")
    args = parser.parse_args()

    start = _parse_dt(args.start)
    end = _parse_dt(args.end)
    conn = _connect(args.db)
    try:
        results = []
        for candidate in _candidate_starts(conn, start, end, args.stride_hours):
            result = evaluate_window(conn, candidate, args.hours)
            if result is not None:
                results.append(result)
        print_summary(results)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
