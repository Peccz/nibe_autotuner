#!/usr/bin/env python3
"""
Reset and Inject Scientific Tests
Clears all existing planned tests and injects new scientific test series.
"""
import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models import init_db, PlannedTest, Parameter
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

def reset_and_inject_tests(db_path='data/nibe_autotuner.db'):
    """Reset planned_tests table and inject new scientific tests"""

    # Initialize database
    engine = init_db(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print("=" * 80)
        print("RESET AND INJECT SCIENTIFIC TESTS")
        print("=" * 80)
        print()

        # Step 1: Count existing tests
        existing_count = session.query(PlannedTest).count()
        print(f"📊 Found {existing_count} existing tests in planned_tests table")

        # Step 2: Delete all existing tests
        if existing_count > 0:
            session.query(PlannedTest).delete()
            session.commit()
            print(f"🗑️  Deleted all {existing_count} existing tests")
        else:
            print("ℹ️  No existing tests to delete")

        print()
        print("-" * 80)
        print("INJECTING NEW SCIENTIFIC TESTS")
        print("-" * 80)
        print()

        # Step 3: Define new scientific tests
        new_tests = [
            {
                'parameter_id': '47011',  # curve_offset
                'parameter_name': 'curve_offset',
                'current_value': None,  # Will be fetched from system
                'proposed_value': -10.0,
                'hypothesis': 'Mäta husets tidskonstant/avkylning',
                'expected_improvement': 'Fastställa termisk tidskonstant',
                'priority': 'high',
                'priority_score': 85.0,
                'execution_order': 1,
                'confidence': 0.9,
                'reasoning': 'Sänker inomhustemperaturen för att mäta värmeavgivningshastighet och fastställa husets termiska tidskonstant'
            },
            {
                'parameter_id': '47206',  # start_compressor
                'parameter_name': 'start_compressor',
                'current_value': None,
                'proposed_value': -160.0,
                'hypothesis': 'Minimera kompressorstarter',
                'expected_improvement': 'Högre COP genom längre cykler',
                'priority': 'medium',
                'priority_score': 65.0,
                'execution_order': 2,
                'confidence': 0.8,
                'reasoning': 'Höjer start-tröskeln för kompressor för att minska antalet starter och öka COP genom längre driftcykler'
            },
            {
                'parameter_id': '47041',  # hot_water_demand
                'parameter_name': 'hot_water_demand',
                'current_value': None,
                'proposed_value': 2.0,  # Large
                'hypothesis': 'Testa max temp utan elpatron',
                'expected_improvement': 'Högre varmvattentemp utan el',
                'priority': 'medium',
                'priority_score': 60.0,
                'execution_order': 3,
                'confidence': 0.75,
                'reasoning': 'Höjer varmvattenbehov till Large för att testa max temperatur värmepumpen kan uppnå utan elpatronens hjälp'
            }
        ]

        # Step 4: Insert tests into database
        created_tests = []
        for i, test_data in enumerate(new_tests, 1):
            # Get parameter from database
            param = session.query(Parameter).filter_by(
                parameter_id=test_data['parameter_id']
            ).first()

            if not param:
                print(f"⚠️  Warning: Parameter {test_data['parameter_id']} not found in database, skipping...")
                continue

            # Create test
            test = PlannedTest(
                parameter_id=param.id,
                current_value=test_data['current_value'],
                proposed_value=test_data['proposed_value'],
                hypothesis=test_data['hypothesis'],
                expected_improvement=test_data['expected_improvement'],
                priority=test_data['priority'],
                priority_score=test_data['priority_score'],
                execution_order=test_data['execution_order'],
                confidence=test_data['confidence'],
                reasoning=test_data['reasoning'],
                status='planned',
                proposed_at=datetime.utcnow()
            )

            session.add(test)
            created_tests.append(test_data)

            print(f"✅ Test {i}: {test_data['parameter_name']} = {test_data['proposed_value']}")
            print(f"   Parameter ID: {test_data['parameter_id']}")
            print(f"   Hypothesis: {test_data['hypothesis']}")
            print(f"   Expected Improvement: {test_data['expected_improvement']}")
            print(f"   Priority: {test_data['priority'].upper()} (Score: {test_data['priority_score']})")
            print(f"   Execution Order: #{test_data['execution_order']}")
            print(f"   Reasoning: {test_data['reasoning'][:80]}...")
            print()

        # Commit all changes
        session.commit()

        print("-" * 80)
        print(f"✅ Successfully created {len(created_tests)} new tests")
        print("-" * 80)
        print()

        # Step 5: Verify and display current state
        print("=" * 80)
        print("VERIFICATION - CURRENT PLANNED TESTS IN DATABASE")
        print("=" * 80)
        print()

        all_tests = session.query(PlannedTest).order_by(PlannedTest.execution_order).all()

        if not all_tests:
            print("⚠️  No tests found in database!")
        else:
            for test in all_tests:
                param = session.query(Parameter).filter_by(id=test.parameter_id).first()
                print(f"🧪 Test #{test.execution_order}: {param.parameter_id if param else 'Unknown'}")
                print(f"   Parameter Name: {param.parameter_name if param else 'Unknown'}")
                print(f"   Proposed Value: {test.proposed_value}")
                print(f"   Hypothesis: {test.hypothesis}")
                print(f"   Expected Improvement: {test.expected_improvement}")
                print(f"   Priority: {test.priority.upper()} (Score: {test.priority_score})")
                print(f"   Status: {test.status}")
                print(f"   Confidence: {test.confidence*100:.0f}%")
                print(f"   Proposed At: {test.proposed_at}")
                print()

        print("=" * 80)
        print("RESET AND INJECTION COMPLETE")
        print("=" * 80)

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
        return False

    finally:
        session.close()

if __name__ == "__main__":
    # Determine database path
    db_paths = [
        'data/nibe_autotuner.db',
        '../data/nibe_autotuner.db',
        os.path.expanduser('~/nibe_autotuner/data/nibe_autotuner.db')
    ]

    db_path = None
    for path in db_paths:
        if os.path.exists(path):
            db_path = path
            break

    if not db_path:
        print("❌ Error: Could not find database file!")
        print("Searched paths:")
        for path in db_paths:
            print(f"  - {path}")
        sys.exit(1)

    print(f"📁 Using database: {db_path}")
    print()

    success = reset_and_inject_tests(db_path)
    sys.exit(0 if success else 1)
