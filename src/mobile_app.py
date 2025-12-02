"""
Nibe Autotuner - Mobile PWA
Lightweight Flask app optimized for mobile devices
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
from datetime import datetime, timedelta
import sys
import os
import logging

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer import HeatPumpAnalyzer
from models import ParameterChange, Device, Parameter, ABTestResult, init_db
from sqlalchemy.orm import sessionmaker
from ab_tester import ABTester
from optimizer import SmartOptimizer
from api_client import MyUplinkClient
from auth import MyUplinkAuth
from auto_optimizer import AutoOptimizer

app = Flask(__name__,
            template_folder='mobile/templates',
            static_folder='mobile/static')

# Initialize database and analyzer
# HeatPumpAnalyzer expects a relative path from working directory
# The systemd service sets WorkingDirectory to the project root
analyzer = HeatPumpAnalyzer('data/nibe_autotuner.db')
engine = analyzer.engine
SessionMaker = sessionmaker(bind=engine)
ab_tester = ABTester(analyzer)
optimizer = SmartOptimizer(analyzer)

# Initialize myUplink API client
auth = MyUplinkAuth()
api_client = MyUplinkClient(auth)

# Initialize auto optimizer
def get_auto_optimizer():
    """Get AutoOptimizer instance"""
    device = SessionMaker().query(Device).first()
    if not device:
        return None
    return AutoOptimizer(
        analyzer=analyzer,
        api_client=api_client,
        device_id=device.device_id,
        dry_run=False  # Live mode
    )

@app.route('/')
def index():
    """Main dashboard"""
    return render_template('dashboard.html')

@app.route('/api/metrics')
def get_metrics():
    """Get current metrics for dashboard"""
    hours = request.args.get('hours', 24, type=int)

    try:
        metrics = analyzer.calculate_metrics(hours_back=hours)

        # Calculate yesterday's metrics for trend comparison
        # Only do this if looking at recent data (<=24 hours)
        yesterday_metrics = None
        if hours <= 24:
            try:
                # Calculate metrics for 24h period ending 24h ago
                yesterday_metrics = analyzer.calculate_metrics(hours_back=24, end_offset_hours=24)
            except Exception as e:
                logger.warning(f"Could not calculate yesterday metrics: {e}")

        # Format metrics for JSON
        data = {
            'cop': float(metrics.estimated_cop) if metrics.estimated_cop else None,
            'degree_minutes': float(metrics.degree_minutes),
            'delta_t_active': float(metrics.delta_t_active) if metrics.delta_t_active else None,
            'delta_t_hot_water': float(metrics.delta_t_hot_water) if metrics.delta_t_hot_water else None,
            'avg_compressor_freq': float(metrics.avg_compressor_freq),
            'avg_outdoor_temp': float(metrics.avg_outdoor_temp),
            'avg_indoor_temp': float(metrics.avg_indoor_temp),
            'avg_supply_temp': float(metrics.avg_supply_temp),
            'avg_return_temp': float(metrics.avg_return_temp),
            'heating_curve': float(metrics.heating_curve),
            'curve_offset': float(metrics.curve_offset),
            'period_start': metrics.period_start.isoformat(),
            'period_end': metrics.period_end.isoformat(),
            'timestamp': datetime.now().isoformat()
        }

        # Add yesterday's values for trend indicators
        if yesterday_metrics:
            data['cop_yesterday'] = float(yesterday_metrics.estimated_cop) if yesterday_metrics.estimated_cop else None
            data['degree_minutes_yesterday'] = float(yesterday_metrics.degree_minutes)
            data['delta_t_active_yesterday'] = float(yesterday_metrics.delta_t_active) if yesterday_metrics.delta_t_active else None

        # Add separate heating metrics
        if metrics.heating_metrics:
            hm = metrics.heating_metrics
            cop_rating = analyzer.get_cop_rating_heating(hm.cop)
            delta_t_rating = analyzer.get_delta_t_rating(hm.delta_t)

            data['heating'] = {
                'cop': float(hm.cop) if hm.cop else None,
                'cop_rating': cop_rating,
                'delta_t': float(hm.delta_t) if hm.delta_t else None,
                'delta_t_rating': delta_t_rating,
                'avg_outdoor_temp': float(hm.avg_outdoor_temp) if hm.avg_outdoor_temp else None,
                'avg_supply_temp': float(hm.avg_supply_temp) if hm.avg_supply_temp else None,
                'avg_return_temp': float(hm.avg_return_temp) if hm.avg_return_temp else None,
                'avg_compressor_freq': float(hm.avg_compressor_freq) if hm.avg_compressor_freq else None,
                'runtime_hours': float(hm.runtime_hours) if hm.runtime_hours else None,
                'num_cycles': hm.num_cycles
            }

        # Add separate hot water metrics
        if metrics.hot_water_metrics:
            hwm = metrics.hot_water_metrics
            cop_rating = analyzer.get_cop_rating_hot_water(hwm.cop)
            delta_t_rating = analyzer.get_delta_t_rating(hwm.delta_t)

            data['hot_water'] = {
                'cop': float(hwm.cop) if hwm.cop else None,
                'cop_rating': cop_rating,
                'delta_t': float(hwm.delta_t) if hwm.delta_t else None,
                'delta_t_rating': delta_t_rating,
                'avg_outdoor_temp': float(hwm.avg_outdoor_temp) if hwm.avg_outdoor_temp else None,
                'avg_hot_water_temp': float(hwm.avg_hot_water_temp) if hwm.avg_hot_water_temp else None,
                'avg_supply_temp': float(hwm.avg_supply_temp) if hwm.avg_supply_temp else None,
                'avg_return_temp': float(hwm.avg_return_temp) if hwm.avg_return_temp else None,
                'avg_compressor_freq': float(hwm.avg_compressor_freq) if hwm.avg_compressor_freq else None,
                'runtime_hours': float(hwm.runtime_hours) if hwm.runtime_hours else None,
                'num_cycles': hwm.num_cycles
            }

        # Add cost analysis
        if metrics.heating_metrics or metrics.hot_water_metrics:
            cost_analysis = analyzer.calculate_cost_analysis(
                metrics.heating_metrics,
                metrics.hot_water_metrics
            )
            data['cost_analysis'] = cost_analysis

        # Add optimization score
        opt_score = analyzer.calculate_optimization_score(metrics)
        data['optimization_score'] = opt_score

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cop_analysis')
def get_cop_analysis():
    """Get COP vs outdoor temperature analysis"""
    hours = request.args.get('hours', 168, type=int)  # Default 1 week

    try:
        device = analyzer.get_device()
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        cop_data = analyzer.get_cop_vs_outdoor_temp(device, start_time, end_time)

        return jsonify({'success': True, 'data': cop_data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chart/<chart_type>')
def get_chart_data(chart_type):
    """Get data for charts"""
    hours = request.args.get('hours', 24, type=int)

    try:
        device = analyzer.get_device()
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        # Map chart types to parameter IDs
        param_map = {
            'outdoor': 40004,    # Outdoor temp
            'indoor': 40033,     # Indoor temp
            'supply': 40008,     # Supply temp
            'return': 40012,     # Return temp
            'compressor': 43424, # Compressor frequency
            'hot_water': 40013,  # Hot water temp
            'pump_speed': 43437  # Circulation pump speed (GP1)
        }

        # Handle special chart types that need calculation
        if chart_type == 'delta_t':
            # Calculate delta T from supply and return temps
            supply_readings = analyzer.get_readings(device, 40008, start_time, end_time)
            return_readings = analyzer.get_readings(device, 40012, start_time, end_time)

            # Match timestamps and calculate delta
            delta_readings = []
            return_dict = {r[0]: r[1] for r in return_readings}
            for timestamp, supply_val in supply_readings:
                if timestamp in return_dict:
                    delta = supply_val - return_dict[timestamp]
                    delta_readings.append((timestamp, delta))

            readings = delta_readings
        elif chart_type == 'cop':
            # Calculate COP over time periods
            readings = analyzer.get_cop_timeseries(device, start_time, end_time)
        elif chart_type in param_map:
            readings = analyzer.get_readings(device, param_map[chart_type], start_time, end_time)
        else:
            return jsonify({'success': False, 'error': 'Invalid chart type'}), 400

        # Decimate data for performance (max 200 points for charts)
        max_points = 200
        if len(readings) > max_points:
            step = len(readings) // max_points
            readings = readings[::step]

        # Format for Chart.js
        data = {
            'labels': [r[0].isoformat() for r in readings],
            'values': [float(r[1]) for r in readings]
        }

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/changes')
def changes():
    """Change log page"""
    return render_template('changes.html')

@app.route('/api/changes', methods=['GET', 'POST'])
def handle_changes():
    """Get or create parameter changes"""
    session = SessionMaker()

    try:
        if request.method == 'POST':
            # Create new change
            data = request.json

            # Get device and parameter from database
            device = session.query(Device).first()
            if not device:
                return jsonify({'success': False, 'error': 'No device found'}), 404

            # Get parameter by ID
            parameter = session.query(Parameter).filter_by(
                parameter_id=int(data.get('parameter_id', 0))
            ).first()

            if not parameter:
                return jsonify({'success': False, 'error': 'Parameter not found'}), 404

            change = ParameterChange(
                device_id=device.id,
                parameter_id=parameter.id,
                timestamp=datetime.fromisoformat(data['timestamp']),
                old_value=data.get('old_value'),
                new_value=data.get('new_value'),
                reason=data.get('reason'),
                applied_by=data.get('applied_by', 'user')
            )

            session.add(change)
            session.commit()

            return jsonify({'success': True, 'message': 'Change logged successfully'})

        else:
            # Get all changes with parameter info
            changes = session.query(ParameterChange)\
                .join(Parameter)\
                .order_by(ParameterChange.timestamp.desc())\
                .limit(100)\
                .all()

            data = [{
                'id': c.id,
                'timestamp': c.timestamp.isoformat(),
                'parameter_id': c.parameter.parameter_id,
                'parameter_name': c.parameter.parameter_name,
                'old_value': c.old_value,
                'new_value': c.new_value,
                'reason': c.reason,
                'applied_by': c.applied_by
            } for c in changes]

            return jsonify({'success': True, 'data': data})

    except Exception as e:
        session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

    finally:
        session.close()

@app.route('/visualizations')
def visualizations():
    """Visualizations page"""
    return render_template('visualizations.html')

@app.route('/baseline')
def baseline():
    """Baseline documentation"""
    return render_template('baseline.html')

@app.route('/ab-testing')
def ab_testing():
    """A/B Testing page"""
    return render_template('ab_testing.html')

@app.route('/api/ab-tests')
def get_ab_tests():
    """Get all A/B test results"""
    session = SessionMaker()
    try:
        limit = request.args.get('limit', 20, type=int)

        results = session.query(ABTestResult)\
            .join(ParameterChange)\
            .join(Parameter)\
            .order_by(ABTestResult.created_at.desc())\
            .limit(limit)\
            .all()

        data = []
        for result in results:
            change = result.parameter_change
            data.append({
                'id': result.id,
                'change_id': change.id,
                'parameter_name': change.parameter.parameter_name,
                'old_value': change.old_value,
                'new_value': change.new_value,
                'timestamp': change.timestamp.isoformat(),
                'cop_before': result.cop_before,
                'cop_after': result.cop_after,
                'cop_change_percent': result.cop_change_percent,
                'delta_t_before': result.delta_t_before,
                'delta_t_after': result.delta_t_after,
                'indoor_temp_before': result.indoor_temp_before,
                'indoor_temp_after': result.indoor_temp_after,
                'indoor_temp_change': result.indoor_temp_change,
                'cost_savings_per_day': result.cost_savings_per_day,
                'cost_savings_per_year': result.cost_savings_per_year,
                'success_score': result.success_score,
                'recommendation': result.recommendation,
                'evaluated_at': result.created_at.isoformat()
            })

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/ab-test/<int:change_id>')
def get_ab_test_detail(change_id):
    """Get detailed A/B test result for a specific change"""
    session = SessionMaker()
    try:
        result = session.query(ABTestResult)\
            .filter_by(parameter_change_id=change_id)\
            .first()

        if not result:
            return jsonify({'success': False, 'error': 'No test result found'}), 404

        change = result.parameter_change

        data = {
            'id': result.id,
            'change': {
                'id': change.id,
                'parameter_name': change.parameter.parameter_name,
                'parameter_id': change.parameter.parameter_id,
                'old_value': change.old_value,
                'new_value': change.new_value,
                'timestamp': change.timestamp.isoformat(),
                'reason': change.reason,
                'applied_by': change.applied_by
            },
            'periods': {
                'before_start': result.before_start.isoformat(),
                'before_end': result.before_end.isoformat(),
                'after_start': result.after_start.isoformat(),
                'after_end': result.after_end.isoformat()
            },
            'cop': {
                'before': result.cop_before,
                'after': result.cop_after,
                'change_percent': result.cop_change_percent
            },
            'delta_t': {
                'before': result.delta_t_before,
                'after': result.delta_t_after,
                'change_percent': result.delta_t_change_percent
            },
            'temperature': {
                'indoor_before': result.indoor_temp_before,
                'indoor_after': result.indoor_temp_after,
                'indoor_change': result.indoor_temp_change,
                'outdoor_before': result.outdoor_temp_before,
                'outdoor_after': result.outdoor_temp_after
            },
            'compressor': {
                'freq_before': result.compressor_freq_before,
                'freq_after': result.compressor_freq_after,
                'cycles_before': result.compressor_cycles_before,
                'cycles_after': result.compressor_cycles_after
            },
            'runtime': {
                'before': result.runtime_hours_before,
                'after': result.runtime_hours_after
            },
            'cost': {
                'per_day_before': result.cost_per_day_before,
                'per_day_after': result.cost_per_day_after,
                'savings_per_day': result.cost_savings_per_day,
                'savings_per_year': result.cost_savings_per_year
            },
            'evaluation': {
                'success_score': result.success_score,
                'recommendation': result.recommendation,
                'evaluated_at': result.created_at.isoformat()
            }
        }

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/evaluate-pending', methods=['POST'])
def evaluate_pending_changes():
    """Manually trigger evaluation of pending changes"""
    try:
        ab_tester.evaluate_all_pending()
        return jsonify({'success': True, 'message': 'Evaluation completed'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/performance-score')
def get_performance_score():
    """Get overall performance score"""
    hours = request.args.get('hours', 72, type=int)

    try:
        score = optimizer.calculate_performance_score(hours_back=hours)

        data = {
            'total_score': score.total_score,
            'cop_score': score.cop_score,
            'delta_t_score': score.delta_t_score,
            'comfort_score': score.comfort_score,
            'efficiency_score': score.efficiency_score,
            'grade': score.grade,
            'emoji': score.emoji
        }

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cost-analysis')
def get_cost_analysis():
    """Get detailed cost analysis"""
    hours = request.args.get('hours', 72, type=int)

    try:
        costs = optimizer.calculate_costs(hours_back=hours)

        data = {
            'daily_cost_sek': costs.daily_cost_sek,
            'monthly_cost_sek': costs.monthly_cost_sek,
            'yearly_cost_sek': costs.yearly_cost_sek,
            'heating_cost_daily': costs.heating_cost_daily,
            'hot_water_cost_daily': costs.hot_water_cost_daily,
            'cop_avg': costs.cop_avg,
            'baseline_yearly_cost': costs.baseline_yearly_cost,
            'savings_yearly': costs.savings_yearly
        }

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/optimization-suggestions')
def get_optimization_suggestions():
    """Get AI-powered optimization suggestions"""
    hours = request.args.get('hours', 72, type=int)

    try:
        suggestions = optimizer.generate_suggestions(hours_back=hours)

        data = [{
            'id': f"{s.parameter_id}_{s.suggested_value}",  # Unique ID for each suggestion
            'priority': s.priority,
            'title': s.title,
            'description': s.description,
            'parameter_name': s.parameter_name,
            'parameter_id': s.parameter_id,
            'current_value': s.current_value,
            'suggested_value': s.suggested_value,
            'expected_cop_improvement': s.expected_cop_improvement,
            'expected_savings_yearly': s.expected_savings_yearly,
            'confidence': s.confidence,
            'reasoning': s.reasoning
        } for s in suggestions]

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/optimization-suggestions/apply', methods=['POST'])
def apply_suggestion():
    """Apply an AI-powered optimization suggestion"""
    try:
        data = request.get_json()
        parameter_id = data.get('parameter_id')
        parameter_name = data.get('parameter_name')
        current_value = data.get('current_value')
        new_value = data.get('suggested_value')
        reasoning = data.get('reasoning', 'AI suggestion applied')

        if not all([parameter_id, parameter_name, new_value is not None]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400

        device_id = get_device_id()
        if not device_id:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        # Apply the change via API
        api_client.set_point_value(device_id, parameter_id, new_value)

        # Log the change
        log_parameter_change(
            device_id=device_id,
            parameter_id=parameter_id,
            parameter_name=parameter_name,
            old_value=current_value,
            new_value=new_value,
            reason=f"AI Recommendation: {reasoning[:100]}"
        )

        logger.info(f"Applied AI suggestion: {parameter_name} {current_value} → {new_value}")

        return jsonify({
            'success': True,
            'message': f'{parameter_name} har ändrats från {current_value} till {new_value}',
            'parameter_name': parameter_name,
            'old_value': current_value,
            'new_value': new_value
        })

    except Exception as e:
        logger.error(f"Error applying suggestion: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/optimization-suggestions/dismiss', methods=['POST'])
def dismiss_suggestion():
    """Dismiss an AI-powered optimization suggestion"""
    try:
        data = request.get_json()
        suggestion_id = data.get('id')
        reason = data.get('reason', 'User dismissed')

        if not suggestion_id:
            return jsonify({'success': False, 'error': 'Missing suggestion ID'}), 400

        # For now, just log the dismissal
        # In the future, we could store this in a database to learn user preferences
        logger.info(f"Suggestion dismissed: {suggestion_id}, reason: {reason}")

        return jsonify({
            'success': True,
            'message': 'Rekommendation avfärdad'
        })

    except Exception as e:
        logger.error(f"Error dismissing suggestion: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ========== GEMINI AI CHAT ==========

@app.route('/api/gemini/chat', methods=['POST'])
def gemini_chat():
    """Chat with Gemini AI agent about heat pump performance"""
    try:
        from gemini_agent import GeminiAgent

        data = request.get_json()
        message = data.get('message', '').strip()
        conversation_history = data.get('history', [])

        if not message:
            return jsonify({'success': False, 'error': 'Message cannot be empty'}), 400

        # Initialize Gemini agent
        # Context is now handled by frontend
        agent = GeminiAgent()

        # Get response
        response = agent.chat(message, conversation_history)

        return jsonify({
            'success': True,
            'response': response
        })

    except ValueError as e:
        logger.error(f"Gemini not configured: {e}")
        return jsonify({
            'success': False,
            'error': 'AI-funktionen är inte aktiverad. Kontakta administratören.'
        }), 503

    except Exception as e:
        logger.error(f"Gemini chat error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/gemini/analyze', methods=['POST'])
def gemini_analyze():
    """Get AI analysis and recommendations from Gemini"""
    try:
        from gemini_agent import GeminiAgent

        data = request.get_json()
        hours = data.get('hours', 24)

        # Get current metrics
        metrics = analyzer.calculate_metrics(hours_back=hours)

        # Get yesterday's metrics for comparison
        yesterday_metrics = None
        if hours <= 24:
            try:
                yesterday_metrics = analyzer.calculate_metrics(
                    hours_back=24,
                    end_offset_hours=24
                )
            except:
                pass

        # Build metrics dict
        metrics_dict = {
            'cop': float(metrics.estimated_cop) if metrics.estimated_cop else None,
            'degree_minutes': float(metrics.degree_minutes),
            'delta_t_active': float(metrics.delta_t_active) if metrics.delta_t_active else None,
            'avg_compressor_frequency': float(metrics.avg_compressor_frequency) if metrics.avg_compressor_frequency else None,
            'runtime_hours': float(metrics.heating_metrics.runtime_hours) if metrics.heating_metrics else None,
            'room_temp': float(metrics.avg_indoor_temp) if metrics.avg_indoor_temp else None,
            'outdoor_temp': float(metrics.avg_outdoor_temp) if metrics.avg_outdoor_temp else None,
            'supply_temp': float(metrics.avg_supply_temp) if metrics.avg_supply_temp else None,
            'return_temp': float(metrics.avg_return_temp) if metrics.avg_return_temp else None,
        }

        if yesterday_metrics:
            metrics_dict['cop_yesterday'] = float(yesterday_metrics.estimated_cop) if yesterday_metrics.estimated_cop else None
            metrics_dict['degree_minutes_yesterday'] = float(yesterday_metrics.degree_minutes)

        # Get recent changes
        session = SessionMaker()
        recent_changes = []
        try:
            changes = session.query(ParameterChange).order_by(
                ParameterChange.timestamp.desc()
            ).limit(5).all()
            recent_changes = [{
                'timestamp': c.timestamp.isoformat(),
                'parameter_name': c.parameter_name,
                'old_value': c.old_value,
                'new_value': c.new_value,
                'reason': c.reason
            } for c in changes]
        finally:
            session.close()

        # Get current parameters (only use verified API-accessible parameters)
        current_parameters = {
            '47011': metrics.curve_offset if metrics.curve_offset else 0,
            # Note: 47007 removed - not accessible via API on F730
        }

        # Initialize Gemini and analyze
        agent = GeminiAgent()
        result = agent.analyze_and_recommend(
            metrics=metrics_dict,
            recent_changes=recent_changes,
            current_parameters=current_parameters
        )

        return jsonify({
            'success': True,
            'data': result
        })

    except ValueError as e:
        logger.error(f"Gemini not configured: {e}")
        return jsonify({
            'success': False,
            'error': 'AI-funktionen är inte aktiverad. Lägg till GOOGLE_API_KEY i .env'
        }), 503

    except Exception as e:
        logger.error(f"Gemini analyze error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ========== QUICK ACTIONS ==========

def get_device_id():
    """Helper to get device ID from database"""
    session = SessionMaker()
    try:
        device = session.query(Device).first()
        return device.device_id if device else None
    finally:
        session.close()

def log_parameter_change(device_id: str, parameter_id: str, parameter_name: str, old_value: float, new_value: float, reason: str):
    """Log a parameter change to database"""
    session = SessionMaker()
    try:
        change = ParameterChange(
            device_id=device_id,
            parameter_id=parameter_id,
            parameter_name=parameter_name,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            timestamp=datetime.utcnow()
        )
        session.add(change)
        session.commit()
    finally:
        session.close()

@app.route('/api/quick-action/adjust-offset', methods=['POST'])
def quick_action_adjust_offset():
    """Quick action: Adjust curve offset by delta (Premium Manage required)"""
    try:
        data = request.get_json()
        delta = data.get('delta', 0)

        if delta == 0:
            return jsonify({'success': False, 'error': 'Delta cannot be 0'}), 400

        device_id = get_device_id()
        if not device_id:
            return jsonify({'success': False, 'error': 'No device found'}), 404

        # Get current offset value (parameter 47011)
        current_data = api_client.get_point_data(device_id, '47011')
        current_value = current_data.get('value')

        # Calculate new value (ensure it's an integer)
        new_value = int(round(current_value + delta))

        # Clamp to valid range (-10 to 10)
        new_value = max(-10, min(10, new_value))

        # Set new value using Premium Manage API
        api_client.set_point_value(device_id, '47011', new_value)

        # Log the change
        reason = f"Quick Action: {'Höj' if delta > 0 else 'Sänk'} offset ({delta:+d})"
        log_parameter_change(device_id, '47011', 'Kurvjustering', current_value, new_value, reason)

        return jsonify({
            'success': True,
            'message': f'Kurvjustering ändrad från {current_value} till {new_value}',
            'old_value': current_value,
            'new_value': new_value
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/quick-action/optimize-efficiency', methods=['POST'])
def quick_action_optimize_efficiency():
    """Quick action: Optimize for maximum COP (Premium Manage required)"""
    try:
        device_id = get_device_id()
        if not device_id:
            return jsonify({'success': False, 'error': 'No device found'}), 404

        changes = []
        metrics = analyzer.calculate_metrics(hours_back=72)

        # Strategy: Lower room temp setpoint if COP is low and indoor temp allows
        if metrics.estimated_cop and metrics.estimated_cop < 3.5 and metrics.avg_indoor_temp > 20.5:
            # Get current room temp setpoint (47011)
            current_setpoint_data = api_client.get_point_data(device_id, '47011')
            current_setpoint = current_setpoint_data.get('value')

            # Lower by 0.5°C
            new_setpoint = round(current_setpoint - 0.5, 1)
            new_setpoint = max(18.0, min(24.0, new_setpoint))

            if new_setpoint != current_setpoint:
                api_client.set_point_value(device_id, '47011', new_setpoint)
                log_parameter_change(device_id, '47011', 'Room temp setpoint', current_setpoint, new_setpoint,
                                    'Quick Action: Optimera för COP')
                changes.append({
                    'parameter': 'Room temp setpoint',
                    'old_value': current_setpoint,
                    'new_value': new_setpoint
                })

        if changes:
            return jsonify({
                'success': True,
                'message': 'Systemet optimerat för maximal COP',
                'changes': changes
            })
        else:
            return jsonify({
                'success': True,
                'message': 'Systemet är redan optimalt för COP, inga ändringar behövs',
                'changes': []
            })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/quick-action/optimize-comfort', methods=['POST'])
def quick_action_optimize_comfort():
    """Quick action: Optimize for comfort (21°C indoor temp, Premium Manage required)"""
    try:
        device_id = get_device_id()
        if not device_id:
            return jsonify({'success': False, 'error': 'No device found'}), 404

        changes = []
        metrics = analyzer.calculate_metrics(hours_back=72)

        # Strategy: Adjust offset to reach 21°C
        target_temp = 21.0
        current_temp = metrics.avg_indoor_temp

        if current_temp:
            temp_diff = target_temp - current_temp

            # If more than 0.5°C off target, adjust offset
            if abs(temp_diff) > 0.5:
                # Get current offset (47011)
                current_offset_data = api_client.get_point_data(device_id, '47011')
                current_offset = current_offset_data.get('value')

                # Adjust offset (1 step per degree difference, rounded to integer)
                delta = int(round(temp_diff))
                delta = max(-2, min(2, delta))  # Limit to +/-2 steps
                new_offset = int(round(current_offset + delta))
                new_offset = max(-10, min(10, new_offset))

                if new_offset != current_offset:
                    api_client.set_point_value(device_id, '47011', new_offset)
                    log_parameter_change(device_id, '47011', 'Kurvjustering', current_offset, new_offset,
                                        f'Quick Action: Optimera komfort (mål 21°C, nu {current_temp:.1f}°C)')
                    changes.append({
                        'parameter': 'Kurvjustering',
                        'old_value': current_offset,
                        'new_value': new_offset
                    })

        if changes:
            return jsonify({
                'success': True,
                'message': f'Systemet justerat för komfort. Nuvarande temp: {current_temp:.1f}°C, mål: 21°C',
                'changes': changes
            })
        else:
            return jsonify({
                'success': True,
                'message': f'Temperaturen är redan bra ({current_temp:.1f}°C), inga ändringar behövs',
                'changes': []
            })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ========== AUTO OPTIMIZER ==========

@app.route('/api/auto-optimize/analyze', methods=['POST'])
def auto_optimize_analyze():
    """Analyze system and suggest automatic optimizations (dry-run)"""
    try:
        data = request.get_json() or {}
        hours = data.get('hours', 72)

        auto_opt = get_auto_optimizer()
        if not auto_opt:
            return jsonify({'success': False, 'error': 'No device found'}), 404

        # Run in dry-run mode (suggestions only)
        auto_opt.dry_run = True
        result = auto_opt.run_optimization_cycle(
            hours_back=hours,
            auto_apply=False
        )

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auto-optimize/run', methods=['POST'])
def auto_optimize_run():
    """Run automatic optimization and apply changes"""
    try:
        data = request.get_json() or {}
        hours = data.get('hours', 72)
        max_actions = data.get('max_actions', 1)
        confirm = data.get('confirm', False)

        if not confirm:
            return jsonify({
                'success': False,
                'error': 'Must confirm with "confirm": true to apply changes'
            }), 400

        auto_opt = get_auto_optimizer()
        if not auto_opt:
            return jsonify({'success': False, 'error': 'No device found'}), 404

        # Check if we can make changes
        can_change, reason = auto_opt.can_make_change()
        if not can_change:
            return jsonify({
                'success': False,
                'error': f'Cannot make automatic changes: {reason}'
            }), 403

        # Run with auto-apply
        auto_opt.dry_run = False
        result = auto_opt.run_optimization_cycle(
            hours_back=hours,
            auto_apply=True,
            max_actions=max_actions
        )

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Ventilation Routes
@app.route('/api/ventilation/status')
def get_ventilation_status():
    """Get current ventilation status and strategy"""
    session = SessionMaker()
    try:
        from ventilation_optimizer import VentilationOptimizer

        device = session.query(Device).first()
        if not device:
            return jsonify({'success': False, 'error': 'No device found'}), 404

        # Create ventilation optimizer
        vent_optimizer = VentilationOptimizer(
            api_client=api_client,
            analyzer=analyzer,
            device_id=device.device_id
        )

        # Get current status
        analysis = vent_optimizer.analyze_current_status()

        # Format response
        current = analysis['current_settings']
        recommended = analysis['recommended_settings']

        data = {
            'outdoor_temp': analysis['outdoor_temp'],
            'indoor_temp': analysis['indoor_temp'],
            'exhaust_temp': analysis['exhaust_temp'],
            'fan_speed_pct': analysis['fan_speed_pct'],
            'current_strategy': analysis['recommended_strategy'],
            'needs_adjustment': analysis['needs_adjustment'],
            'reasoning': analysis['reasoning'],
            'current_settings': {
                'increased_ventilation': current.increased_ventilation,
                'start_temp_exhaust': current.start_temp_exhaust,
                'min_diff_outdoor_exhaust': current.min_diff_outdoor_exhaust
            },
            'recommended_settings': {
                'increased_ventilation': recommended.increased_ventilation,
                'start_temp_exhaust': recommended.start_temp_exhaust,
                'min_diff_outdoor_exhaust': recommended.min_diff_outdoor_exhaust
            },
            'estimated_rh_drop_pct': analysis['estimated_rh_drop_pct'],
            'temp_lift': analysis['temp_lift']
        }

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

# AI Agent Routes
@app.route('/ai-agent')
def ai_agent():
    """AI Agent page"""
    return render_template('ai_agent.html')

@app.route('/api/ai-agent/status')
def get_ai_agent_status():
    """Get AI agent status"""
    session = SessionMaker()
    try:
        from models import AIDecisionLog
        import os

        # Count total analyses and adjustments
        total_analyses = session.query(AIDecisionLog).count()
        total_adjustments = session.query(AIDecisionLog).filter_by(applied=True).count()

        # Get last run
        last_decision = session.query(AIDecisionLog).order_by(
            AIDecisionLog.timestamp.desc()
        ).first()

        # Estimate monthly cost (assuming 60 analyses/month at ~0.10 kr each)
        monthly_cost_sek = total_analyses * 0.10 / max(1, total_analyses / 60)

        status = {
            'enabled': os.getenv('GOOGLE_API_KEY') is not None,
            'last_run': last_decision.timestamp.isoformat() if last_decision else None,
            'next_run': 'Schemalagd via auto_optimizer cron',
            'total_analyses': total_analyses,
            'total_adjustments': total_adjustments,
            'monthly_cost_sek': round(monthly_cost_sek, 2) if total_analyses > 0 else 0
        }

        return jsonify({'success': True, 'data': status})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/ai-agent/latest-decision')
def get_latest_ai_decision():
    """Get latest AI decision"""
    session = SessionMaker()
    try:
        from models import AIDecisionLog, Parameter

        decision_log = session.query(AIDecisionLog).order_by(
            AIDecisionLog.timestamp.desc()
        ).first()

        if not decision_log:
            return jsonify({'success': True, 'data': None})

        decision = {
            'timestamp': decision_log.timestamp.isoformat(),
            'action': decision_log.action,
            'parameter_name': decision_log.parameter.parameter_name if decision_log.parameter else None,
            'old_value': decision_log.current_value,
            'new_value': decision_log.suggested_value,
            'reasoning': decision_log.reasoning,
            'confidence': decision_log.confidence,
            'expected_impact': decision_log.expected_impact,
            'applied': decision_log.applied
        }

        return jsonify({'success': True, 'data': decision})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/ai-agent/planned-tests')
def get_planned_tests():
    """Get planned tests"""
    session = SessionMaker()
    try:
        from models import PlannedTest

        tests = session.query(PlannedTest).filter_by(status='pending').order_by(
            PlannedTest.priority.desc(),
            PlannedTest.confidence.desc()
        ).all()

        data = []
        for test in tests:
            data.append({
                'id': test.id,
                'parameter_name': test.parameter.parameter_name if test.parameter else 'Unknown',
                'current_value': test.current_value,
                'proposed_value': test.proposed_value,
                'hypothesis': test.hypothesis,
                'expected_improvement': test.expected_improvement,
                'priority': test.priority,
                'confidence': test.confidence * 100,
                'reasoning': test.reasoning,
                'scheduled_date': test.proposed_at.isoformat()
            })

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/ai-agent/active-tests')
def get_active_tests():
    """Get active tests"""
    session = SessionMaker()
    try:
        from models import PlannedTest

        tests = session.query(PlannedTest).filter_by(status='active').all()

        data = []
        for test in tests:
            if test.started_at:
                elapsed = (datetime.utcnow() - test.started_at).total_seconds() / 3600
                progress = min(100, (elapsed / 48) * 100)  # 48h test period
                hours_remaining = max(0, 48 - elapsed)
            else:
                progress = 0
                hours_remaining = 48

            data.append({
                'id': test.id,
                'parameter_name': test.parameter.parameter_name if test.parameter else 'Unknown',
                'old_value': test.current_value,
                'new_value': test.proposed_value,
                'started_date': test.started_at.isoformat() if test.started_at else None,
                'end_date': (test.started_at + timedelta(hours=48)).isoformat() if test.started_at else None,
                'progress': int(progress),
                'hours_remaining': int(hours_remaining)
            })

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/ai-agent/completed-tests')
def get_completed_tests():
    """Get completed tests with results"""
    session = SessionMaker()
    try:
        from models import PlannedTest, ABTestResult

        limit = request.args.get('limit', 10, type=int)

        tests = session.query(PlannedTest).filter_by(status='completed').join(
            ABTestResult, PlannedTest.result_id == ABTestResult.id, isouter=True
        ).order_by(PlannedTest.completed_at.desc()).limit(limit).all()

        data = []
        for test in tests:
            result = test.result if test.result else None

            data.append({
                'id': test.id,
                'parameter_name': test.parameter.parameter_name if test.parameter else 'Unknown',
                'old_value': test.current_value,
                'new_value': test.proposed_value,
                'completed_date': test.completed_at.isoformat() if test.completed_at else None,
                'success': result.success_score > 70 if result else False,
                'confidence': int(test.confidence * 100),
                'cop_before': result.cop_before if result else None,
                'cop_after': result.cop_after if result else None,
                'cop_change': result.cop_change_percent if result else None,
                'result_summary': test.hypothesis,
                'recommendation': result.recommendation if result else None
            })

        return jsonify({'success': True, 'data': data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/ai-agent/learning-stats')
def get_learning_stats():
    """Get learning statistics"""
    session = SessionMaker()
    try:
        from models import PlannedTest, ABTestResult

        # Get all completed tests with results
        completed_tests = session.query(PlannedTest).filter_by(status='completed').join(
            ABTestResult, PlannedTest.result_id == ABTestResult.id
        ).all()

        if not completed_tests:
            return jsonify({'success': True, 'data': {
                'success_rate': 0,
                'avg_cop_improvement': 0,
                'avg_confidence': 0,
                'total_tests': 0,
                'best_findings': []
            }})

        # Calculate statistics
        successes = sum(1 for t in completed_tests if t.result.success_score > 70)
        success_rate = (successes / len(completed_tests)) * 100

        cop_improvements = [t.result.cop_change_percent for t in completed_tests if t.result.cop_change_percent]
        avg_cop_improvement = sum(cop_improvements) / len(cop_improvements) if cop_improvements else 0

        confidences = [t.confidence * 100 for t in completed_tests]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        # Best findings (top 3 by COP improvement)
        best_tests = sorted(
            [t for t in completed_tests if t.result.cop_change_percent and t.result.cop_change_percent > 0],
            key=lambda t: t.result.cop_change_percent,
            reverse=True
        )[:3]

        best_findings = []
        for test in best_tests:
            best_findings.append({
                'parameter_name': test.parameter.parameter_name if test.parameter else 'Unknown',
                'improvement': test.result.cop_change_percent,
                'description': test.hypothesis
            })

        stats = {
            'success_rate': success_rate,
            'avg_cop_improvement': avg_cop_improvement,
            'avg_confidence': avg_confidence,
            'total_tests': len(completed_tests),
            'best_findings': best_findings
        }

        return jsonify({'success': True, 'data': stats})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()

@app.route('/manifest.json')
def manifest():
    """PWA manifest"""
    return jsonify({
        'name': 'Nibe Autotuner',
        'short_name': 'Nibe',
        'description': 'Nibe F730 Heat Pump Monitor & Optimizer',
        'start_url': '/',
        'display': 'standalone',
        'background_color': '#1e1e1e',
        'theme_color': '#2d5f8e',
        'orientation': 'portrait',
        'icons': [
            {
                'src': '/static/icons/icon-192.png',
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any maskable'
            },
            {
                'src': '/static/icons/icon-512.png',
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any maskable'
            }
        ]
    })

@app.route('/sw.js')
def service_worker():
    """Service Worker for offline support"""
    return send_from_directory('mobile/static/js', 'sw.js')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8502, debug=False)
