import sys
import os
import sqlite3
from datetime import datetime
import traceback # Added

# Setup path
sys.path.insert(0, os.path.abspath('src'))

from services.analyzer import HeatPumpAnalyzer
# from integrations.autonomous_ai_agent_v2 import AutonomousAIAgentV2 # Avoid import issues
from data.models import Parameter, ParameterReading, Device
from data.database import SessionLocal

def diagnose():
    print("="*60)
    print("DIAGNOSING OFFSET VALUE CHAIN")
    print("="*60)

    # 1. DATABASE RAW LEVEL
    print("\n1. RAW DATABASE CHECK (SQLite)")
    try:
        conn = sqlite3.connect('data/nibe_autotuner.db')
        c = conn.cursor()
        
        # Get parameter internal ID
        c.execute("SELECT id, parameter_id, parameter_name FROM parameters WHERE parameter_id='47011'")
        param_row = c.fetchone()
        
        if not param_row:
            print("❌ ERROR: Parameter 47011 not found in 'parameters' table!")
        else:
            p_id, p_str_id, p_name = param_row
            print(f"✓ Found Parameter: ID={p_id}, StrID='{p_str_id}', Name='{p_name}'")
            
            # Get latest reading
            c.execute("SELECT value, timestamp FROM parameter_readings WHERE parameter_id=? ORDER BY timestamp DESC LIMIT 1", (p_id,))
            reading_row = c.fetchone()
            
            if not reading_row:
                print("❌ ERROR: No readings found for this parameter!")
            else:
                val, ts = reading_row
                print(f"✓ Latest Raw Reading: Value={val}, Timestamp={ts}")
                
        conn.close()
    except Exception as e:
        print(f"❌ Database error: {e}")

    # 2. ANALYZER LEVEL
    print("\n2. ANALYZER SERVICE CHECK")
    try:
        analyzer = HeatPumpAnalyzer()
        # Create a session to fetch device
        session = SessionLocal()
        device = session.query(Device).first()
        
        if not device:
            print("❌ ERROR: No device found via ORM")
        else:
            print(f"✓ Device found: {device.product_name} (ID: {device.id})")
            
            # Test get_latest_value
            val = analyzer.get_latest_value(device, '47011')
            print(f"✓ Analyzer.get_latest_value(47011): {val}")
            
            # Test calculate_metrics
            metrics = analyzer.calculate_metrics(hours_back=1)
            print(f"✓ Analyzer.calculate_metrics().curve_offset: {metrics.curve_offset}")
            
            if val is None or metrics.curve_offset is None:
                print("⚠️ WARNING: Analyzer returned None. Is the fallback removed?")
    except Exception as e:
        print(f"❌ Analyzer error: {e}")
        traceback.print_exc() # Print stack trace

    # 3. PROMPT GENERATION CHECK
    print("\n3. AGENT PROMPT LOGIC CHECK")
    try:
        # We already have metrics from step 2.
        current_offset = -3.0 # Default in agent
        if 'metrics' in locals() and metrics and metrics.curve_offset is not None:
            current_offset = metrics.curve_offset
            print(f"✓ Agent would use offset from metrics: {current_offset}")
        else:
            print(f"⚠️ Agent would use fallback offset: {current_offset}")
            
        print(f"-> This value ({current_offset}) will be injected into prompt as 'Current Curve Offset'")

    except Exception as e:
        print(f"❌ Agent logic error: {e}")

    print("\n" + "="*60)

if __name__ == "__main__":
    diagnose()
