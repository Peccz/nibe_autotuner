#!/usr/bin/env python3
"""
Test Scientific Test Evaluation
Dry run of the evaluate_scientific_test_results method.
"""
import sys
import os
from datetime import datetime, timedelta
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from data.models import init_db, PlannedTest, Parameter
from sqlalchemy.orm import sessionmaker
from autonomous_ai_agent_v2 import AutonomousAIAgentV2
from services.analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from weather_service import SMHIWeatherService

def test_scientific_evaluation():
    """Test the scientific test evaluation on the first planned test"""

    print("=" * 80)
    print("SCIENTIFIC TEST EVALUATION - DRY RUN")
    print("=" * 80)
    print()

    # Initialize database
    db_path = 'data/nibe_autotuner.db'
    if not os.path.exists(db_path):
        db_path = os.path.expanduser('~/nibe_autotuner/data/nibe_autotuner.db')

    engine = init_db(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get the first planned test
        test = session.query(PlannedTest).order_by(PlannedTest.execution_order).first()

        if not test:
            print("❌ No planned tests found in database")
            return False

        # Get parameter info
        param = session.query(Parameter).filter_by(id=test.parameter_id).first()

        print(f"📋 Found Test:")
        print(f"   ID: {test.id}")
        print(f"   Parameter: {param.parameter_id if param else 'Unknown'} - {param.parameter_name if param else 'Unknown'}")
        print(f"   Proposed Value: {test.proposed_value}")
        print(f"   Hypothesis: {test.hypothesis}")
        print(f"   Priority: {test.priority} (Score: {test.priority_score})")
        print(f"   Status: {test.status}")
        print()

        # Create AI agent components
        print("🔧 Initializing AI Agent components...")
        analyzer = HeatPumpAnalyzer(db_path)
        api_client = MyUplinkClient()
        weather_service = SMHIWeatherService()

        # Get device from database
        from data.models import Device
        device = session.query(Device).first()
        if not device:
            print("❌ No device found in database")
            return False

        # Create AI Agent V2
        agent = AutonomousAIAgentV2(
            analyzer=analyzer,
            api_client=api_client,
            weather_service=weather_service,
            device_id=device.device_id
        )

        print("✅ AI Agent V2 initialized")
        print()

        # Simulate a test period (last 24 hours)
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)

        print(f"📅 Simulating test period:")
        print(f"   Start: {start_time}")
        print(f"   End: {end_time}")
        print(f"   Duration: 24 hours")
        print()

        print("-" * 80)
        print("RUNNING EVALUATION...")
        print("-" * 80)
        print()

        # Call the evaluation method
        evaluation = agent.evaluate_scientific_test_results(test, start_time, end_time)

        print()
        print("=" * 80)
        print("EVALUATION RESULTS")
        print("=" * 80)
        print()

        # Pretty print results
        print(json.dumps(evaluation, indent=2, default=str))

        print()
        print("=" * 80)
        print("KEY FINDINGS")
        print("=" * 80)
        print()

        if evaluation['success']:
            print(f"✅ Evaluation Successful")
            print()
            print(f"📊 Conclusion:")
            print(f"   {evaluation['conclusion']}")
            print()

            if 'cooling_rate' in evaluation['analysis']:
                cr = evaluation['analysis']['cooling_rate']
                print(f"🌡️  Cooling Rate Analysis:")
                print(f"   Rate: {cr['cooling_rate_c_per_hour']} °C/hour")
                print(f"   Start Temp: {cr['start_temp']}°C")
                print(f"   End Temp: {cr['end_temp']}°C")
                print(f"   R²: {cr['r_squared']}")
                print()

            if 'compressor_starts' in evaluation['analysis']:
                cs = evaluation['analysis']['compressor_starts']
                print(f"⚙️  Compressor Starts Analysis:")
                print(f"   Total Starts: {cs['start_count']}")
                print(f"   Avg Runtime: {cs['avg_runtime_minutes']} min")
                print(f"   Total Runtime: {cs['total_runtime_hours']} hours")
                print()

            if 'hot_water' in evaluation['analysis']:
                hw = evaluation['analysis']['hot_water']
                print(f"💧 Hot Water Analysis:")
                print(f"   Max Temperature: {hw.get('max_temperature', 'N/A')}°C")
                print(f"   Note: {hw.get('note', 'N/A')}")
                print()

        else:
            print(f"❌ Evaluation Failed")
            print(f"   Error: {evaluation.get('error', 'Unknown error')}")

        print("=" * 80)
        print("DRY RUN COMPLETE")
        print("=" * 80)

        return evaluation['success']

    except Exception as e:
        print(f"❌ Error during evaluation: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        session.close()

if __name__ == "__main__":
    success = test_scientific_evaluation()
    sys.exit(0 if success else 1)
