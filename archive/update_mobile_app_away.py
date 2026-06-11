with open('temp_mobile_app_v4.py', 'r') as f:
    lines = f.readlines()

# 1. Update get_settings response
for i, line in enumerate(lines):
    if "'target_indoor_temp_max': device.target_indoor_temp_max," in line:
        lines.insert(i+1, "                'away_mode_enabled': device.away_mode_enabled,\n")
        lines.insert(i+2, "                'away_mode_end_date': device.away_mode_end_date.isoformat() if device.away_mode_end_date else None,\n")
        break

# 2. Add set_away_mode route
insert_pos = -1
for i, line in enumerate(lines):
    if "@app.route('/api/settings', methods=['POST'])" in line:
        insert_pos = i # Insert before this one
        break

if insert_pos != -1:
    new_route = """
@app.route('/api/settings/away-mode', methods=['POST'])
def set_away_mode():
    try:
        data = request.json
        enabled = data.get('enabled', False)
        end_date_str = data.get('end_date') # ISO format string or None
        
        session = SessionLocal()
        device = session.query(Device).first()
        if not device:
            return jsonify({'success': False, 'error': 'No device'}), 404
            
        device.away_mode_enabled = enabled
        
        if end_date_str:
            try:
                # Handle empty string
                if not end_date_str:
                    device.away_mode_end_date = None
                else:
                    device.away_mode_end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            except ValueError:
                # Try simple date parsing if isoformat fails
                pass 
        else:
            device.away_mode_end_date = None
            
        session.commit()
        
        status = "ON" if enabled else "OFF"
        logger.info(f"Away mode set to {status}")
        
        return jsonify({'success': True, 'message': f'Away mode {status}'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'session' in locals():
            session.close()
"""
    lines.insert(insert_pos, new_route + "\n")

with open('mobile_app_with_away.py', 'w') as f:
    f.writelines(lines)
