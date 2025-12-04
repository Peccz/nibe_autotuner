import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath('src'))

from models import init_db, Parameter
from sqlalchemy.orm import sessionmaker

# Initialize DB connection
try:
    engine = init_db('sqlite:///data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()

    # Fetch all parameters
    params = session.query(Parameter).order_by(Parameter.parameter_id).all()

    print(f"{'ID':<8} | {'RW':<4} | {'Unit':<6} | {'Name'}")
    print("-" * 80)

    for p in params:
        # Check if writable (assuming 'writable' column exists and is boolean)
        # If unknown, we mark as 'R' (Read)
        rw = "R/W" if p.writable else "R"
        unit = p.parameter_unit if p.parameter_unit else "-"
        print(f"{p.parameter_id:<8} | {rw:<4} | {unit:<6} | {p.parameter_name}")

except Exception as e:
    print(f"Error: {e}")
