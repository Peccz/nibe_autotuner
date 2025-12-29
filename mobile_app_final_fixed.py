from flask import Flask, render_template, jsonify, request, redirect, url_for
from datetime import datetime, timedelta
import os
import sys
import json

# Add src to path
sys.path.insert(0, os.path.abspath('src'))

from data.database import SessionLocal
from data.models import Device, Parameter, ParameterReading, GMAccount, PlannedHeatingSchedule, AIDecisionLog
from services.analyzer import HeatPumpAnalyzer
from services.price_service import price_service

app = Flask(__name__)
analyzer = HeatPumpAnalyzer()

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

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
    """Combined status endpoint for the dashboard header"""
    session = SessionLocal()
    try:
        # 1. Device / Metrics
        device = session.query(Device).first()
        metrics = analyzer.calculate_metrics(hours_back=1)
        
        # Fallback indoor temp
        indoor = metrics.avg_indoor_temp if metrics and metrics.avg_indoor_temp else None
        if indoor is None and device:
            indoor = analyzer.get_latest_value(device, '40033') # BT50

        # Fallback outdoor temp
        outdoor = metrics.avg_outdoor_temp if metrics and metrics.avg_outdoor_temp else None
        if outdoor is None and device:
            outdoor = analyzer.get_latest_value(device, '40004') # Outdoor

        # 2. GM Account
        account = session.query(GMAccount).first()
        gm_balance = account.balance if account else 0.0
        gm_mode = account.mode if account else 'NORMAL'

        # 3. Current Price
        price_val = price_service.get_current_price()

        return jsonify({
            'indoor_temp': round(indoor, 1) if indoor else None,
            'outdoor_temp': round(outdoor, 1) if outdoor else None,
            'target_temp': device.target_indoor_temp_min if device else 21.0,
            'gm_balance': round(gm_balance, 0),
            'gm_mode': gm_mode,
            'current_price': round(price_val, 2),
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    finally:
        session.close()

@app.route('/api/plan')
def get_plan():
    """Returns the 24h SmartPlanner schedule for charting"""
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        # Fetch plan starting from 2 hours ago
        schedule = session.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp >= now - timedelta(hours=2)
        ).order_by(PlannedHeatingSchedule.timestamp).all()
        
        data = []
        for s in schedule:
            # Color code action for frontend convenience
            is_running = 0
            if s.planned_action in ['RUN', 'MUST_RUN']: is_running = 1
            
            data.append({
                'timestamp': s.timestamp.isoformat() + 'Z',
                'action': s.planned_action,
                'gm_load': s.planned_gm_value,
                'is_running': is_running,
                'price': s.electricity_price,
                'indoor_sim': s.simulated_indoor_temp,
                'outdoor': s.outdoor_temp
            })
        return jsonify(data)
    finally:
        session.close()

@app.route('/api/changes')
def get_changes():
    """Returns parameter change history"""
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
