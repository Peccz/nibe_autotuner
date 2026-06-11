with open('mobile_app.py', 'r') as f:
    lines = f.readlines()

# Add imports
for i, line in enumerate(lines):
    if "from data.models import" in line:
        if "GMAccount" not in line:
            lines[i] = line.strip() + ", GMAccount, PlannedHeatingSchedule\n"
        break

# Add endpoints
# Find end of file or appropriate place
insert_idx = len(lines)
for i, line in enumerate(lines):
    if "if __name__ == '__main__':" in line:
        insert_idx = i
        break

new_endpoints = """
@app.route('/api/gm-status')
def get_gm_status():
    session = SessionLocal()
    try:
        account = session.query(GMAccount).first()
        if not account:
            return jsonify({'balance': 0, 'mode': 'UNKNOWN'})
        return jsonify({
            'balance': account.balance,
            'mode': account.mode,
            'last_updated': account.last_updated.isoformat() if account.last_updated else None
        })
    finally:
        session.close()

@app.route('/api/schedule')
def get_schedule():
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        schedule = session.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp >= now - timedelta(hours=1)
        ).order_by(PlannedHeatingSchedule.timestamp).all()
        
        return jsonify([{
            'timestamp': s.timestamp.isoformat() + 'Z',
            'action': s.planned_action,
            'gm': s.planned_gm_value,
            'price': s.electricity_price,
            'indoor_sim': s.simulated_indoor_temp
        } for s in schedule])
    finally:
        session.close()
"""
lines.insert(insert_idx, new_endpoints)

with open('mobile_app_with_gm.py', 'w') as f:
    f.writelines(lines)
