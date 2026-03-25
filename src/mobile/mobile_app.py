from flask import Flask, render_template, jsonify, request, redirect, url_for
from datetime import datetime, timedelta, timezone
import os
import sys
import json

# Add src to path
sys.path.insert(0, os.path.abspath('src'))

from data.database import SessionLocal
from data.models import Device, Parameter, ParameterReading, GMAccount, PlannedHeatingSchedule, AIDecisionLog
from data.performance_model import DailyPerformance
from services.analyzer import HeatPumpAnalyzer
from services.price_service import price_service
from core.config import settings

from sqlalchemy import text

app = Flask(__name__)

# --- V7 DASHBOARD (The Strategist) ---
@app.route('/api/v7/dashboard')
def get_dashboard_v7():
    session = SessionLocal()
    analyzer = HeatPumpAnalyzer()
    device = analyzer.get_device()
    
    try:
        # 1. LIVE STATUS
        outdoor = analyzer.get_latest_value(device, analyzer.PARAM_OUTDOOR_TEMP) or 0.0
        in_down = analyzer.get_latest_value(device, 'HA_TEMP_DOWNSTAIRS')
        in_dexter = analyzer.get_latest_value(device, 'HA_TEMP_DEXTER')
        
        # Determine actual control temperature
        # Logic from SmartPlanner V12:
        target_temp = 21.5
        min_dexter = 20.5
        
        control_temp = in_down if in_down else (in_dexter if in_dexter else 21.0)
        priority_msg = "Normal (Nere)"
        
        if in_dexter and in_dexter < min_dexter:
             dexter_equiv = in_dexter + 1.5
             if dexter_equiv < (in_down or 99):
                 control_temp = dexter_equiv
                 priority_msg = "Säkerhet (Dexter)"

        supply = analyzer.get_latest_value(device, analyzer.PARAM_SUPPLY_TEMP) or 0.0
        
        # Calculate Target Supply (The Truth)
        # 20 + (20-Out)*Curve*0.12 + Offset
        # We need the current planned offset
        now = datetime.now(timezone.utc)
        current_plan = session.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp <= now,
            PlannedHeatingSchedule.timestamp > now - timedelta(hours=1)
        ).order_by(PlannedHeatingSchedule.timestamp.desc()).first()
        
        current_offset = current_plan.planned_offset if current_plan else 0.0
        target_supply = 20 + (20 - outdoor) * settings.DEFAULT_HEATING_CURVE * 0.12 + current_offset

        gm = session.query(GMAccount).first()
        gm_balance = gm.balance if gm else 0.0
        
        # Calculate GM Rate (Delta)
        # Rate = Actual - Target
        gm_rate = supply - target_supply
        
        # 2. CHART DATA (History + Future)
        hist_start = now - timedelta(hours=12)
        
        # Helper for history
        def get_series(param_id):
            pid = session.query(Parameter).filter_by(parameter_id=param_id).first()
            if not pid: return []
            readings = session.query(ParameterReading).filter(
                ParameterReading.parameter_id == pid.id,
                ParameterReading.timestamp >= hist_start
            ).order_by(ParameterReading.timestamp).all()
            return [{'x': r.timestamp.isoformat(), 'y': r.value} for r in readings]

        hist_indoor = get_series('HA_TEMP_DOWNSTAIRS')
        hist_dexter = get_series('HA_TEMP_DEXTER')
        
        # Helper for future
        plan_rows = session.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp >= now
        ).order_by(PlannedHeatingSchedule.timestamp).all()
        
        future_indoor = [{'x': p.timestamp.isoformat(), 'y': p.simulated_indoor_temp} for p in plan_rows]
        future_offset = [{'x': p.timestamp.isoformat(), 'y': p.planned_offset} for p in plan_rows]
        future_price = [{'x': p.timestamp.isoformat(), 'y': p.electricity_price} for p in plan_rows]

        return jsonify({
            "status": {
                "control_temp": round(control_temp, 2),
                "target_temp": target_temp,
                "outdoor": outdoor,
                "supply": supply,
                "target_supply": round(target_supply, 1),
                "gm_actual": analyzer.get_latest_value(device, '40941') or 0,
                "gm_bank": round(gm_balance, 0),
                "gm_rate": round(gm_rate, 1),
                "offset": current_offset,
                "priority": priority_msg
            },
            "chart": {
                "hist_indoor": hist_indoor,
                "hist_dexter": hist_dexter,
                "future_indoor": future_indoor,
                "future_offset": future_offset,
                "future_price": future_price
            }
        })
    finally:
        session.close()

# --- LEGACY ENDPOINTS (Keeping for compatibility) ---
@app.route('/api/v4/dashboard')
def get_dashboard_v4():
    return jsonify({}) # Deprecated

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard_v7.html')

@app.route('/api/changes')
def get_changes():
    session = SessionLocal()
    try:
        logs = session.query(AIDecisionLog).order_by(AIDecisionLog.timestamp.desc()).limit(50).all()
        data = []
        for log in logs:
            data.append({
                'timestamp': log.timestamp.isoformat(),
                'parameter_name': 'AI Decision',
                'old_value': str(log.current_value) if log.current_value is not None else '--',
                'new_value': str(log.suggested_value) if log.suggested_value is not None else (log.reasoning[:20] if log.reasoning else ''),
                'reason': log.reasoning,
                'applied_by': 'ai'
            })
        return jsonify({'success': True, 'data': data})
    finally:
        session.close()

@app.route('/performance')
def performance():
    return render_template('performance.html')

@app.route('/api/performance')
def get_performance():
    session = SessionLocal()
    try:
        # Load per-device comfort thresholds
        device = session.query(Device).first()
        comfort_min = float(device.target_indoor_temp_min) if device and device.target_indoor_temp_min else 20.5
        comfort_max = float(device.target_indoor_temp_max) if device and device.target_indoor_temp_max else 22.0

        # --- Daily comfort stats (HA_TEMP_DOWNSTAIRS preferred, BT50 fallback) ---
        daily_rows = session.execute(text("""
            SELECT
              DATE(r.timestamp) as day,
              COUNT(*) as total,
              SUM(CASE WHEN r.value BETWEEN :cmin AND :cmax THEN 1 ELSE 0 END) as in_comfort,
              ROUND(SUM(CASE WHEN r.value < :cmin THEN (:cmin - r.value) ELSE 0 END), 2) as cold_debt,
              ROUND(AVG(r.value), 2) as avg_temp,
              ROUND(MIN(r.value), 1) as min_temp,
              ROUND(MAX(r.value), 1) as max_temp
            FROM parameter_readings r
            JOIN parameters p ON r.parameter_id = p.id
            WHERE p.parameter_id = (
                CASE WHEN EXISTS (
                    SELECT 1 FROM parameters WHERE parameter_id = 'HA_TEMP_DOWNSTAIRS'
                ) THEN 'HA_TEMP_DOWNSTAIRS' ELSE '40033' END
            )
              AND r.timestamp > datetime('now', '-14 days')
            GROUP BY day
            ORDER BY day DESC
        """), {'cmin': comfort_min, 'cmax': comfort_max}).fetchall()

        # --- Daily compressor on-time (41778 > 5 Hz = running) ---
        comp_rows = session.execute(text("""
            SELECT
              DATE(r.timestamp) as day,
              ROUND(100.0 * SUM(CASE WHEN r.value > 5 THEN 1 ELSE 0 END) / COUNT(*), 1) as on_pct,
              ROUND(AVG(CASE WHEN r.value > 5 THEN r.value ELSE NULL END), 1) as avg_hz
            FROM parameter_readings r
            JOIN parameters p ON r.parameter_id = p.id
            WHERE p.parameter_id = '41778'
              AND r.timestamp > datetime('now', '-14 days')
            GROUP BY day
            ORDER BY day DESC
        """)).fetchall()
        comp_map = {r[0]: {'on_pct': r[1], 'avg_hz': r[2]} for r in comp_rows}

        # --- Daily price stats (from plan — only non-fallback prices) ---
        price_rows = session.execute(text("""
            SELECT
              DATE(timestamp) as day,
              ROUND(AVG(electricity_price), 3) as avg_price,
              ROUND(MIN(electricity_price), 3) as min_price,
              ROUND(MAX(electricity_price), 3) as max_price
            FROM planned_heating_schedule
            WHERE electricity_price != 1.0
              AND timestamp > datetime('now', '-14 days')
            GROUP BY day
            ORDER BY day DESC
        """)).fetchall()
        price_map = {r[0]: {'avg': r[1], 'min': r[2], 'max': r[3]} for r in price_rows}

        # --- Today's hourly prices from plan ---
        today_prices = session.execute(text("""
            SELECT
              strftime('%H', timestamp) as hour,
              ROUND(electricity_price, 3) as price,
              planned_action,
              planned_offset
            FROM planned_heating_schedule
            WHERE DATE(timestamp) = DATE('now')
            ORDER BY hour
        """)).fetchall()

        # Assemble daily array
        daily = []
        for row in daily_rows:
            day = row[0]
            total = row[1] or 1
            comfort_pct = round(100.0 * (row[2] or 0) / total, 1)
            cold_debt = row[3] or 0.0
            c = comp_map.get(day, {})
            p = price_map.get(day, {})
            daily.append({
                'date': day,
                'comfort_pct': comfort_pct,
                'cold_debt': cold_debt,
                'avg_temp': row[4],
                'min_temp': row[5],
                'max_temp': row[6],
                'compressor_on_pct': c.get('on_pct'),
                'avg_hz': c.get('avg_hz'),
                'avg_price': p.get('avg'),
            })

        # --- Prediction accuracy (last 14 days) ---
        accuracy_rows = session.execute(text("""
            SELECT
              DATE(forecast_hour) as day,
              ROUND(AVG(ABS(error_c)), 3) as mae,
              ROUND(AVG(error_c), 3) as bias,
              COUNT(*) as n
            FROM prediction_accuracy
            WHERE forecast_hour > datetime('now', '-14 days')
            GROUP BY day
            ORDER BY day DESC
        """)).fetchall()
        accuracy = [{'date': r[0], 'mae': r[1], 'bias': r[2], 'n': r[3]} for r in accuracy_rows]

        # Summary (last 7 full days)
        recent = daily[:7]
        summary = {}
        if recent:
            summary['comfort_7d_pct'] = round(sum(d['comfort_pct'] for d in recent) / len(recent), 1)
            summary['cold_debt_7d'] = round(sum(d['cold_debt'] for d in recent), 1)
            summary['compressor_on_pct'] = round(sum(d['compressor_on_pct'] or 0 for d in recent) / len(recent), 1)
            prices_with_data = [d['avg_price'] for d in recent if d['avg_price']]
            summary['avg_price'] = round(sum(prices_with_data) / len(prices_with_data), 3) if prices_with_data else None
            summary['price_available'] = bool(prices_with_data)

        # MAE summary for KPI card
        recent_acc = accuracy[:7]
        if recent_acc:
            summary['model_mae_7d'] = round(sum(a['mae'] for a in recent_acc if a['mae']) / len(recent_acc), 3)
            summary['model_bias_7d'] = round(sum(a['bias'] for a in recent_acc if a['bias']) / len(recent_acc), 3)

        return jsonify({
            'summary': summary,
            'daily': daily,
            'accuracy': accuracy,
            'hourly_today': [
                {'hour': int(r[0]), 'price': r[1], 'action': r[2], 'offset': r[3]}
                for r in today_prices
            ]
        })
    finally:
        session.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
