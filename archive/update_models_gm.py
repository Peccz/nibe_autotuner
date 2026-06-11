with open('models_latest.py', 'r') as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if "class LearningEvent" in line:
        insert_idx = i
        break

if insert_idx != -1:
    new_class = """class GMAccount(Base):
    __tablename__ = "gm_account"
    id = Column(Integer, primary_key=True)
    balance = Column(Float, default=0.0) # Virtual GM balance
    mode = Column(String, default="NORMAL") # AUTO, SAVE, SPEND
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<GMAccount(balance={self.balance}, mode='{self.mode}')>"

"""
    lines.insert(insert_idx, new_class)

with open('models_with_gm.py', 'w') as f:
    f.writelines(lines)