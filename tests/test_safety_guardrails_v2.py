import os
import sqlite3
from datetime import datetime, timedelta

os.environ.setdefault("MYUPLINK_CLIENT_ID", "test-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "test-secret")

from services.smart_planner import _replace_future_plan_rows


def create_plan_table(conn):
    conn.execute("""
        CREATE TABLE planned_heating_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            planned_action TEXT,
            planned_offset REAL,
            electricity_price REAL,
            simulated_indoor_temp REAL,
            simulated_dexter_temp REAL,
            outdoor_temp REAL,
            wind_speed REAL
        )
    """)


def plan_row(ts, action="RUN", offset=0.0):
    return (
        ts,
        action,
        offset,
        1.0,
        21.0,
        20.5,
        5.0,
        0.0,
    )


def test_replace_future_plan_rows_deletes_from_plan_start_not_wall_clock_now():
    conn = sqlite3.connect(":memory:")
    create_plan_table(conn)
    plan_start = datetime.utcnow().replace(minute=0, second=0, microsecond=0)

    conn.executemany("""
        INSERT INTO planned_heating_schedule
        (timestamp, planned_action, planned_offset, electricity_price,
         simulated_indoor_temp, simulated_dexter_temp, outdoor_temp, wind_speed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        plan_row(plan_start - timedelta(hours=1), "KEEP", -1.0),
        plan_row(plan_start, "OLD", -2.0),
        plan_row(plan_start + timedelta(hours=1), "OLD", -3.0),
    ])

    _replace_future_plan_rows(conn, plan_start, [
        plan_row(plan_start, "NEW", 1.0),
        plan_row(plan_start + timedelta(hours=1), "NEW", 2.0),
    ])

    rows = conn.execute("""
        SELECT timestamp, planned_action, planned_offset
        FROM planned_heating_schedule
        ORDER BY timestamp
    """).fetchall()

    assert rows == [
        ((plan_start - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"), "KEEP", -1.0),
        (plan_start.strftime("%Y-%m-%d %H:%M:%S"), "NEW", 1.0),
        ((plan_start + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"), "NEW", 2.0),
    ]
