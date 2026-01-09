from flask import Flask, render_template, jsonify, request, redirect, url_for
from datetime import datetime, timedelta
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

app = Flask(__name__)
analyzer = HeatPumpAnalyzer()

@app.route('/api/performance')
def get_performance():
    session = SessionLocal()
    try:
        results = session.query(DailyPerformance).order_by(DailyPerformance.date.desc()).limit(14).all()
        return jsonify([{
            'date': p.date.strftime('%Y-%m-%d'),
            'savings_sek': round(p.savings_sek, 2),
            'savings_percent': round(p.savings_percent, 1),
            'actual_kwh': round(p.actual_kwh, 1),
            'baseline_kwh': round(p.baseline_kwh, 1),
            'avg_indoor': round(p.avg_indoor_temp, 1)
        } for p in results])
    finally:
        session.close()

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard_v5.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/log')
def log_page():
    return render_template('changes.html')

@app.route('/settings')
def settings_page():
    session = SessionLocal()
    device = session.query(Device).first()
    session.close()
    return render_template('settings.html', device=device)

# --- API Endpoints ---

@app.route('/api/status')
def get_status():
    session = SessionLocal()
    try:
        device = session.query(Device).first()
        metrics = analyzer.calculate_metrics(hours_back=1)
        
        # DOWNSTAIRS (Prefer IKEA)
        indoor = analyzer.get_latest_value(device, 'HA_TEMP_DOWNSTAIRS')
        if indoor is None:
            indoor = metrics.avg_indoor_temp if metrics and metrics.avg_indoor_temp else None
        
        # DEXTER
        dexter = analyzer.get_latest_value(device, 'HA_TEMP_DEXTER')

        outdoor = metrics.avg_outdoor_temp if metrics and metrics.avg_outdoor_temp else None
        if outdoor is None and device:
            outdoor = analyzer.get_latest_value(device, '40004')

        hw_temp = None
        supply_temp = None
        if device:
            hw_temp = analyzer.get_latest_value(device, '40013')
            supply_temp = analyzer.get_latest_value(device, '40008')

        account = session.query(GMAccount).first()
        gm_balance = account.balance if account else 0.0
        gm_mode = account.mode if account else 'NORMAL'

        price_data = price_service.get_current_price_details()

        # Check Boost status
        latest_log = session.query(AIDecisionLog).order_by(AIDecisionLog.timestamp.desc()).first()
        is_boost = False
        if latest_log and "Dexter boost" in (latest_log.reasoning or ""):
            # Check if log is recent (within 1 hour)
            if (datetime.utcnow() - latest_log.timestamp).total_seconds() < 3600:
                is_boost = True

        return jsonify({
            'indoor_temp': round(indoor, 2) if indoor else None,
            'indoor_dexter': round(dexter, 2) if dexter else None,
            'outdoor_temp': round(outdoor, 1) if outdoor else None,
            'hw_temp': round(hw_temp, 1) if hw_temp else None,
            'supply_temp': round(supply_temp, 1) if supply_temp else None,
            'target_temp': device.target_indoor_temp_min if device else 21.0,
            'gm_balance': round(gm_balance, 0),
            'gm_mode': gm_mode,
            'current_price': round(price_data['total'], 2),
            'spot_price': round(price_data['spot'], 2),
            'is_boost_active': is_boost,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    finally:
        session.close()

@app.route('/api/plan')
def get_plan():
    """Returns historical data + 24h schedule for charting"""
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        history_start = now - timedelta(hours=12)
        
        def get_readings(param_id):
            pid = session.query(Parameter).filter_by(parameter_id=param_id).first()
            if not pid: return []
            readings = (session.query(ParameterReading)
                .filter(ParameterReading.parameter_id == pid.id)
                .filter(ParameterReading.timestamp >= history_start)
                .order_by(ParameterReading.timestamp).all())
            return [{'x': r.timestamp.isoformat() + 'Z', 'y': r.value} for r in readings]

        # 1. History
        hist_indoor = get_readings('HA_TEMP_DOWNSTAIRS')
        if not hist_indoor: hist_indoor = get_readings('40033')
        
        hist_dexter = get_readings('HA_TEMP_DEXTER')
        hist_outdoor = get_readings('40004')
        hist_gm = get_readings('40941')
        hist_bank = get_readings('VP_GM_BANK')
        
        # 2. Plan
        schedule = session.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp >= now
        ).order_by(PlannedHeatingSchedule.timestamp).all()
        
        # Format Plan Data
        plan_indoor = [{'x': s.timestamp.isoformat() + 'Z', 'y': s.simulated_indoor_temp} for s in schedule]
        plan_dexter = [{'x': s.timestamp.isoformat() + 'Z', 'y': s.simulated_dexter_temp} for s in schedule]
        plan_outdoor = [{'x': s.timestamp.isoformat() + 'Z', 'y': s.outdoor_temp} for s in schedule]
        plan_price = [{'x': s.timestamp.isoformat() + 'Z', 'y': s.electricity_price} for s in schedule]
        
        plan_action = []
        for s in schedule:
            val = 0
            if s.planned_action in ['RUN', 'MUST_RUN']: val = 10
            plan_action.append({'x': s.timestamp.isoformat() + 'Z', 'y': val})

        table_data = []
        for s in schedule:
            table_data.append({
                'timestamp': s.timestamp.isoformat() + 'Z',
                'action': s.planned_action,
                'hw_mode': s.planned_hot_water_mode,
                'price': s.electricity_price,
                'indoor_sim': s.simulated_indoor_temp,
                'dexter_sim': s.simulated_dexter_temp,
                'outdoor': s.outdoor_temp
            })

        return jsonify({
            'history': {
                'indoor': hist_indoor,
                'dexter': hist_dexter,
                'outdoor': hist_outdoor,
                'gm': hist_gm,
                'bank': hist_bank
            },
            'plan': {
                'indoor': plan_indoor,
                'dexter': plan_dexter,
                'outdoor': plan_outdoor,
                'price': plan_price,
                'action': plan_action
            },
            'table': table_data
        })
    finally:
        session.close()

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

@app.route('/api/ai-agent/history')
def get_ai_history():
    session = SessionLocal()
    try:
        logs = session.query(AIDecisionLog).order_by(AIDecisionLog.timestamp.desc()).limit(10).all()
        return jsonify([{
            'timestamp': l.timestamp.isoformat() + 'Z',
            'action': l.action,
            'reasoning': l.reasoning
        } for l in logs])
    finally:
        session.close()

@app.route('/api/analytics/data')
def get_analytics_data():
    session = SessionLocal()
    try:
        hours = request.args.get('hours', default=24, type=int)
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        def get_series(param_id):
            param = session.query(Parameter).filter_by(parameter_id=param_id).first()
            if not param: return []
            
            readings = (session.query(ParameterReading)
                .filter(ParameterReading.parameter_id == param.id)
                .filter(ParameterReading.timestamp >= start_time)
                .order_by(ParameterReading.timestamp).all())
            return [{'x': r.timestamp.isoformat() + 'Z', 'y': r.value} for r in readings]

        return jsonify({
            'indoor': get_series('40033'),
            'outdoor': get_series('40004'),
            'gm': get_series('40941'),
            'bank': get_series('VP_GM_BANK'),
            'supply': get_series('40008'),
            'return': get_series('40012')
        })
    finally:
        session.close()

@app.route('/api/settings/update', methods=['POST'])
def update_settings():
    data = request.json
    session = SessionLocal()
    try:
        device = session.query(Device).first()
        if device:
            if 'min_indoor_temp' in data:
                device.min_indoor_temp_user_setting = float(data['min_indoor_temp'])
            if 'target_indoor_temp_min' in data:
                device.target_indoor_temp_min = float(data['target_indoor_temp_min'])
            if 'target_indoor_temp_max' in data:
                device.target_indoor_temp_max = float(data['target_indoor_temp_max'])
            if 'away_mode' in data:
                device.away_mode_enabled = bool(data['away_mode'])
            
            session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'No device found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
