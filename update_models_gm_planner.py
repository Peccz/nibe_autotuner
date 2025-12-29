with open('models_gm_planner.py', 'r') as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if "class GMAccount" in line:
        insert_idx = i
        break

if insert_idx != -1:
    new_class = """
class PlannedHeatingSchedule(Base):
    __tablename__ = "planned_heating_schedule"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    outdoor_temp = Column(Float)
    electricity_price = Column(Float)
    simulated_indoor_temp = Column(Float)
    planned_action = Column(String, nullable=False) # MUST_RUN, MUST_REST, RUN, REST, HOLD
    planned_gm_value = Column(Float) # GM value to write to pump (40940)

    def __repr__(self):
        return f"<PlannedHeatingSchedule(timestamp='{self.timestamp}', action='{self.planned_action}')>"

"""
    lines.insert(insert_idx, new_class)

with open('models_with_gm_planner.py', 'w') as f:
    f.writelines(lines)