#!/usr/bin/env python3
"""
Test PlannedTest Scientific Evaluation
Simulates a completed PlannedTest and runs the scientific evaluation.
"""
import sys
import os
from datetime import datetime, timedelta
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models import init_db, PlannedTest, Parameter
from sqlalchemy.orm import sessionmaker
from ab_tester import ABTester
from analyzer import HeatPumpAnalyzer

def test_planned_test_evaluation():
    """Test the PlannedTest evaluation workflow"""

    print("=" * 80)
    print("PLANNED TEST SCIENTIFIC EVALUATION - TEST")
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
        # Get first planned test
        test = session.query(PlannedTest).order_by(PlannedTest.execution_order).first()

        if not test:
            print("❌ No planned tests found in database")
            return False

        param = session.query(Parameter).filter_by(id=test.parameter_id).first()

        print(f"📋 Found Test:")
        print(f"   ID: {test.id}")
        print(f"   Parameter: {param.parameter_id if param else 'Unknown'} - {param.parameter_name if param else 'Unknown'}")
        print(f"   Hypothesis: {test.hypothesis}")
        print(f"   Current Status: {test.status}")
        print()

        # Simulate test completion by setting timestamps
        if test.status == 'planned':
            print("🔧 Simulating test execution...")
            # Simulate that test was started 48h ago and completed now
            test.started_at = datetime.utcnow() - timedelta(hours=48)
            test.completed_at = datetime.utcnow()
            test.status = 'completed'
            session.commit()
            print(f"✅ Simulated test completion:")
            print(f"   Started: {test.started_at}")
            print(f"   Completed: {test.completed_at}")
            print()

        # Initialize ABTester
        print("🔧 Initializing ABTester...")
        analyzer = HeatPumpAnalyzer(db_path)
        ab_tester = ABTester(analyzer)
        print("✅ ABTester initialized")
        print()

        # Check for completed tests ready for evaluation
        print("-" * 80)
        print("CHECKING FOR COMPLETED TESTS...")
        print("-" * 80)
        print()

        completed_tests = ab_tester.get_completed_planned_tests_for_evaluation()
        print(f"Found {len(completed_tests)} completed PlannedTest(s) ready for evaluation")
        print()

        if not completed_tests:
            print("ℹ️ No completed tests to evaluate")
            return True

        # Evaluate all completed tests
        print("-" * 80)
        print("RUNNING SCIENTIFIC EVALUATION...")
        print("-" * 80)
        print()

        results = ab_tester.evaluate_all_completed_planned_tests()

        print()
        print("=" * 80)
        print("EVALUATION RESULTS")
        print("=" * 80)
        print()

        if results:
            print(f"✅ Successfully evaluated {len(results)} test(s)")
            print()

            for result in results:
                print(f"📊 Result ID: {result.id}")
                print(f"   Period: {result.after_start} to {result.after_end}")
                print(f"   Success Score: {result.success_score}")
                print()

                # Parse and display the JSON recommendation
                try:
                    eval_data = json.loads(result.recommendation)
                    print("   Scientific Analysis:")
                    print(f"   - Parameter: {eval_data.get('parameter_name', 'N/A')}")
                    print(f"   - Hypothesis: {eval_data.get('hypothesis', 'N/A')}")
                    print(f"   - Duration: {eval_data.get('duration_hours', 'N/A')}h")
                    print(f"   - Conclusion: {eval_data.get('conclusion', 'N/A')}")
                    print()

                    if 'analysis' in eval_data:
                        analysis = eval_data['analysis']

                        if 'cooling_rate' in analysis:
                            cr = analysis['cooling_rate']
                            print(f"   🌡️  Cooling Rate:")
                            print(f"      Rate: {cr.get('cooling_rate_c_per_hour', 'N/A')} °C/h")
                            print(f"      R²: {cr.get('r_squared', 'N/A')}")
                            print()

                        if 'compressor_starts' in analysis:
                            cs = analysis['compressor_starts']
                            print(f"   ⚙️  Compressor Starts:")
                            print(f"      Total: {cs.get('start_count', 'N/A')}")
                            print(f"      Avg Runtime: {cs.get('avg_runtime_minutes', 'N/A')} min")
                            print()

                        if 'hot_water' in analysis:
                            hw = analysis['hot_water']
                            print(f"   💧 Hot Water:")
                            print(f"      Max Temp: {hw.get('max_temperature', 'N/A')}°C")
                            print()

                except json.JSONDecodeError:
                    print(f"   Raw Recommendation: {result.recommendation[:200]}...")
                    print()

        else:
            print("⚠️ No results generated")

        print("=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)

        return True

    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        session.close()

if __name__ == "__main__":
    success = test_planned_test_evaluation()
    sys.exit(0 if success else 1)
