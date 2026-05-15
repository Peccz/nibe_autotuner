import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("MYUPLINK_CLIENT_ID", "test-client")
os.environ.setdefault("MYUPLINK_CLIENT_SECRET", "test-secret")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from backtest_v15_shadow import evaluate_window


def _make_backtest_conn(start):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE parameters (id integer primary key, parameter_id text)")
    conn.execute(
        """
        CREATE TABLE parameter_readings (
            parameter_id integer,
            timestamp timestamp,
            value real
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE planned_heating_schedule (
            timestamp timestamp,
            planned_action text,
            planned_offset real,
            electricity_price real,
            outdoor_temp real,
            wind_speed real,
            cloud_cover real
        )
        """
    )
    conn.execute("INSERT INTO parameters VALUES (1, 'HA_TEMP_DOWNSTAIRS')")
    conn.execute("INSERT INTO parameters VALUES (2, 'HA_TEMP_DEXTER')")
    conn.execute(
        "INSERT INTO parameter_readings VALUES (1, ?, ?)",
        ((start - timedelta(minutes=5)).isoformat(sep=" "), 22.0),
    )
    conn.execute(
        "INSERT INTO parameter_readings VALUES (2, ?, ?)",
        ((start - timedelta(minutes=5)).isoformat(sep=" "), 21.2),
    )

    for i in range(24):
        ts = start + timedelta(hours=i)
        conn.execute(
            "INSERT INTO planned_heating_schedule VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts.isoformat(sep=" "), "RUN", 0.0, 1.0, 8.0, 2.0, 8.0),
        )
    return conn


def test_evaluate_window_compares_v14_and_v15_without_db_writes():
    start = datetime(2026, 5, 8, 15, 0, 0)
    conn = _make_backtest_conn(start)

    before = conn.execute("SELECT COUNT(*) FROM planned_heating_schedule").fetchone()[0]
    result = evaluate_window(conn, start, hours=24)
    after = conn.execute("SELECT COUNT(*) FROM planned_heating_schedule").fetchone()[0]

    assert result is not None
    assert before == after
    assert result.v15_rest >= result.v14_rest
    assert result.v15_over_floor_hours <= result.v14_over_floor_hours
