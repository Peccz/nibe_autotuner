"""
Nibe Autotuner - Mobile PWA
Lightweight Flask app optimized for mobile devices
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer import HeatPumpAnalyzer
from models import ParameterChange, Device, Parameter, init_db
from sqlalchemy.orm import sessionmaker

app = Flask(__name__,
            template_folder='mobile/templates',
            static_folder='mobile/static')

# Initialize database and analyzer
# HeatPumpAnalyzer expects a relative path from working directory
# The systemd service sets WorkingDirectory to the project root
analyzer = HeatPumpAnalyzer('data/nibe_autotuner.db')
engine = analyzer.engine
SessionMaker = sessionmaker(bind=engine)

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
