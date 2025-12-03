#!/usr/bin/env python3
"""
Add 20 optimization test proposals to the database

This script creates a comprehensive test plan with 20 carefully designed
optimization tests, ranked by priority using a multi-factor scoring algorithm.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models import Parameter, PlannedTest, init_db
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from loguru import logger


def calculate_priority_score(expected_cop_gain_pct, cost_savings_month, confidence_pct, risk_level, num_parameters):
    """
    Calculate priority score using weighted factors

    Priority Score = (Expected_COP_Gain × 0.30) +
                     (Cost_Savings × 0.25) +
                     (Confidence × 0.20) +
                     (Safety × 0.15) +
                     (Simplicity × 0.10)

    Returns: 0-100 score
    """
    # Normalize inputs to 0-100 scale
    cop_score = min(100, expected_cop_gain_pct * 10)  # 10% = 100 points
    cost_score = min(100, cost_savings_month / 2)      # 200kr = 100 points
    confidence_score = confidence_pct

    # Safety score (inverse of risk)
    risk_scores = {'low': 90, 'medium': 60, 'high': 30, 'very_high': 10}
    safety_score = risk_scores.get(risk_level, 50)

    # Simplicity score (fewer parameters = better)
    if num_parameters == 1:
        simplicity_score = 100
    elif num_parameters <= 3:
        simplicity_score = 50
    else:
        simplicity_score = 10

    # Weighted sum
    priority = (
        cop_score * 0.30 +
        cost_score * 0.25 +
        confidence_score * 0.20 +
        safety_score * 0.15 +
        simplicity_score * 0.10
    )

    return round(priority, 2)


# Define all 20 tests with their parameters
TESTS = [
    {
        'id': 1,
        'parameter_id': '47011',
        'current_value': -3.0,
        'proposed_value': -2.0,
        'hypothesis': 'Nuvarande offset är extremt låg. Genom att öka med 1 steg kan vi förbättra Delta T och effektivitet utan att göra det för varmt',
        'expected_improvement': 'Delta T ökar till 5.5-6.0°C, COP +3-5% (~50-70 kr/mån)',
        'expected_cop_gain': 4.0,
        'cost_savings': 60,
        'confidence': 0.85,
        'risk': 'low',
        'priority_calc': 'high',
        'num_params': 1,
        'reasoning': 'Offset -3 är mycket låg vilket förklarar låg Delta T (4.9°C). Detta är högsta prioritet eftersom det adresserar känd ineffektivitet med låg risk.'
    },
    {
        'id': 2,
        'parameter_id': '47011',
        'current_value': -3.0,
        'proposed_value': -1.0,
        'hypothesis': 'Mer aggressiv ökning av offset för snabbare resultat',
        'expected_improvement': 'Delta T ökar till 6.0-6.5°C, COP +5-7% (~80-100 kr/mån)',
        'expected_cop_gain': 6.0,
        'cost_savings': 90,
        'confidence': 0.70,
        'risk': 'medium',
        'priority_calc': 'medium',
        'num_params': 1,
        'reasoning': 'Större hopp i offset kan ge snabbare förbättring men risk för överkorrigering. Bättre att testa efter Test #1.'
    },
    {
        'id': 3,
        'parameter_id': '47007',
        'current_value': 7.0,
        'proposed_value': 6.5,
        'hypothesis': 'I milt väder (4.5°C) behövs inte lika brant kurva',
        'expected_improvement': 'COP +5-8% (~80-120 kr/mån), inomhustemp sjunker till 21.0-21.2°C',
        'expected_cop_gain': 6.5,
        'cost_savings': 100,
        'confidence': 0.75,
        'risk': 'medium',
        'priority_calc': 'high',
        'num_params': 1,
        'reasoning': 'Värmekurva 7.0 kan vara för hög för milt väder. Vetenskapligt belagt att kurvoptimering ger 4-8% förbättring.'
    },
    {
        'id': 4,
        'parameter_id': '47007',
        'current_value': 7.0,
        'proposed_value': 6.0,
        'hypothesis': 'Mer aggressiv kurvsänkning för maximalt COP-lyft',
        'expected_improvement': 'COP +10-12% (~120-160 kr/mån), inomhustemp 20.5-21.0°C',
        'expected_cop_gain': 11.0,
        'cost_savings': 140,
        'confidence': 0.60,
        'risk': 'high',
        'priority_calc': 'medium',
        'num_params': 1,
        'reasoning': 'Större förändring med högre potential men också högre risk. Endast vid gynnsamt väder >5°C.'
    },
    {
        'id': 5,
        'parameter_id': '47011,47007',
        'current_value': -3.0,
        'proposed_value': -2.0,
        'hypothesis': 'Kombinera offset +1 och curve -0.5 för dubbel optimering',
        'expected_improvement': 'COP +8-10% (~100-140 kr/mån), optimal Delta T',
        'expected_cop_gain': 9.0,
        'cost_savings': 120,
        'confidence': 0.70,
        'risk': 'medium',
        'priority_calc': 'high',
        'num_params': 2,
        'reasoning': 'Kombinerar de två bästa enskilda testerna. Kör efter Test #1 och #3 för att validera effekterna separat först.'
    },
    {
        'id': 6,
        'parameter_id': '47015',
        'current_value': 20.0,
        'proposed_value': 20.5,
        'hypothesis': 'Faktisk temp (21.5°C) är mycket högre än setpoint (20°C), indikerar obalans',
        'expected_improvement': 'Bättre matchning mellan setpoint och faktisk temp',
        'expected_cop_gain': 0.5,
        'cost_savings': 20,
        'confidence': 0.65,
        'risk': 'low',
        'priority_calc': 'low',
        'num_params': 1,
        'reasoning': 'Liten förväntat effekt, mer av kalibrering än optimering. Låg prioritet.'
    },
    {
        'id': 7,
        'parameter_id': '47015',
        'current_value': 20.0,
        'proposed_value': 19.5,
        'hypothesis': 'Kompensera för att faktisk temp är högre än setpoint',
        'expected_improvement': 'Faktisk temp sjunker till 21.0°C, COP +2-3% (~60-80 kr/mån)',
        'expected_cop_gain': 2.5,
        'cost_savings': 70,
        'confidence': 0.70,
        'risk': 'low',
        'priority_calc': 'high',
        'num_params': 1,
        'reasoning': 'Säkert sätt att sänka inomhustemp från 21.5 till 21.0°C vilket är optimalt för både komfort och energi.'
    },
    {
        'id': 8,
        'parameter_id': '47020',
        'current_value': 15.0,
        'proposed_value': 18.0,
        'hypothesis': 'Högre minimum kan förbättra Delta T vid låg drift',
        'expected_improvement': 'Delta T förbättras vid låglast (~30-50 kr/mån)',
        'expected_cop_gain': 1.5,
        'cost_savings': 40,
        'confidence': 0.60,
        'risk': 'low',
        'priority_calc': 'low',
        'num_params': 1,
        'reasoning': 'Begränsad effekt, främst vid låglast. Lägre prioritet.'
    },
    {
        'id': 9,
        'parameter_id': '47020',
        'current_value': 15.0,
        'proposed_value': 12.0,
        'hypothesis': 'Lägre minimum tillåter mer effektiv drift i milt väder',
        'expected_improvement': 'COP +2-3% (~40-60 kr/mån) i milt väder',
        'expected_cop_gain': 2.5,
        'cost_savings': 50,
        'confidence': 0.65,
        'risk': 'medium',
        'priority_calc': 'medium',
        'num_params': 1,
        'reasoning': 'Bra för milt väder men kan ge sämre komfort i kallt väder. Säsongsspecifikt test.'
    },
    {
        'id': 10,
        'parameter_id': '47206',
        'current_value': -200.0,
        'proposed_value': -250.0,
        'hypothesis': 'Längre cykler genom senare start = högre COP',
        'expected_improvement': 'Färre starter, +3-5% COP (~50-80 kr/mån)',
        'expected_cop_gain': 4.0,
        'cost_savings': 65,
        'confidence': 0.75,
        'risk': 'medium',
        'priority_calc': 'high',
        'num_params': 1,
        'reasoning': 'Vetenskapligt belagt att längre cykler förbättrar effektivitet. God kandidat för tidig testning.'
    },
    {
        'id': 11,
        'parameter_id': '47206',
        'current_value': -200.0,
        'proposed_value': -150.0,
        'hypothesis': 'Tidigare start = jämnare temperatur = bättre komfort',
        'expected_improvement': 'Förbättrad komfort, COP -2% (kostnad ~30 kr/mån)',
        'expected_cop_gain': -2.0,
        'cost_savings': -30,
        'confidence': 0.70,
        'risk': 'low',
        'priority_calc': 'medium',
        'num_params': 1,
        'reasoning': 'Komforttest snarare än effektivitetstest. Användbart för att verifiera trade-offs.'
    },
    {
        'id': 12,
        'parameter_id': '47206',
        'current_value': -200.0,
        'proposed_value': -300.0,
        'hypothesis': 'Maximera cykellängd för maximal effektivitet',
        'expected_improvement': 'COP +5-8% (~80-120 kr/mån), risk för komfortproblem',
        'expected_cop_gain': 6.5,
        'cost_savings': 100,
        'confidence': 0.50,
        'risk': 'high',
        'priority_calc': 'low',
        'num_params': 1,
        'reasoning': 'Extremtest med hög potential men också hög risk. Endast vid >6°C utomhus.'
    },
    {
        'id': 13,
        'parameter_id': '50005',
        'current_value': 0.0,
        'proposed_value': 1.0,
        'hypothesis': 'Ökad ventilation ger torrare luft men kallare frånluft',
        'expected_improvement': 'Bättre luftkvalitet, COP -5-10% (kostnad ~80-120 kr/mån)',
        'expected_cop_gain': -7.5,
        'cost_savings': -100,
        'confidence': 0.80,
        'risk': 'low',
        'priority_calc': 'low',
        'num_params': 1,
        'reasoning': 'Negativt för COP men användbart vid fuktproblem. Lägre prioritet för effektivitetsoptimering.'
    },
    {
        'id': 14,
        'parameter_id': '47538',
        'current_value': 24.0,
        'proposed_value': 20.0,
        'hypothesis': 'Tidigare start av frånluftsvärmning = mer värmeutvinning',
        'expected_improvement': 'COP +3-5% (~50-80 kr/mån) genom bättre värmeutvinning',
        'expected_cop_gain': 4.0,
        'cost_savings': 65,
        'confidence': 0.70,
        'risk': 'low',
        'priority_calc': 'high',
        'num_params': 1,
        'reasoning': 'Låg risk med god potential. F730 är frånluftsvärmepump så detta är relevant optimering.'
    },
    {
        'id': 15,
        'parameter_id': '47538',
        'current_value': 24.0,
        'proposed_value': 28.0,
        'hypothesis': 'Vänta med frånluftsvärmning = energibesparing i milt väder',
        'expected_improvement': 'COP +2-4% (~30-60 kr/mån) i milt väder',
        'expected_cop_gain': 3.0,
        'cost_savings': 45,
        'confidence': 0.65,
        'risk': 'low',
        'priority_calc': 'medium',
        'num_params': 1,
        'reasoning': 'Bra för milt väder. Alternativ strategi till Test #14.'
    },
    {
        'id': 16,
        'parameter_id': '47011,47007,47206,47538',
        'current_value': -3.0,
        'proposed_value': -2.0,
        'hypothesis': 'Kombinera de fyra bästa enkeltesterna för maximal effekt',
        'expected_improvement': 'COP +12-15% (~150-200 kr/mån)',
        'expected_cop_gain': 13.5,
        'cost_savings': 175,
        'confidence': 0.55,
        'risk': 'high',
        'priority_calc': 'medium',
        'num_params': 4,
        'reasoning': 'Multi-parameter test med högsta potential men svårt att isolera effekter. Kör sent i testcykeln.'
    },
    {
        'id': 17,
        'parameter_id': '47011,47015,47206',
        'current_value': -3.0,
        'proposed_value': -1.0,
        'hypothesis': 'Optimera för jämn temperatur över effektivitet',
        'expected_improvement': 'Bättre komfort, COP -2-3% (kostnad ~40 kr/mån)',
        'expected_cop_gain': -2.5,
        'cost_savings': -40,
        'confidence': 0.70,
        'risk': 'low',
        'priority_calc': 'low',
        'num_params': 3,
        'reasoning': 'Komfortprofil för användare som prioriterar stabilitet över energibesparing.'
    },
    {
        'id': 18,
        'parameter_id': '47011,47007,47015',
        'current_value': -3.0,
        'proposed_value': -2.0,
        'hypothesis': 'Hitta perfekt balans mellan komfort och effektivitet',
        'expected_improvement': 'COP +5-7% (~80-100 kr/mån), god komfort',
        'expected_cop_gain': 6.0,
        'cost_savings': 90,
        'confidence': 0.75,
        'risk': 'medium',
        'priority_calc': 'high',
        'num_params': 3,
        'reasoning': 'Balansprofil som kombinerar måttliga förbättringar med behållen komfort. God kandidat för "slutlig" konfiguration.'
    },
    {
        'id': 19,
        'parameter_id': '47007,47011,47015,47020',
        'current_value': 7.0,
        'proposed_value': 5.5,
        'hypothesis': 'Drastisk sänkning för maximal effektivitet',
        'expected_improvement': 'COP +15-20%, risk för dålig komfort',
        'expected_cop_gain': 17.5,
        'cost_savings': 250,
        'confidence': 0.40,
        'risk': 'very_high',
        'priority_calc': 'low',
        'num_params': 4,
        'reasoning': 'Extremtest med högsta potential men också högsta risk. Endast vid >8°C och med kontinuerlig övervakning.'
    },
    {
        'id': 20,
        'parameter_id': '47007,47011',
        'current_value': 7.0,
        'proposed_value': 9.0,
        'hypothesis': 'Återställ till fabriksinställningar för baseline-verifiering',
        'expected_improvement': 'Sämre COP än nuvarande, bekräftar att optimeringar fungerat',
        'expected_cop_gain': -5.0,
        'cost_savings': -80,
        'confidence': 0.90,
        'risk': 'medium',
        'priority_calc': 'low',
        'num_params': 2,
        'reasoning': 'Verifieringstest för att etablera ny baseline. Viktigt för att bevisa värdet av optimeringar.'
    }
]


def main():
    logger.info("=" * 80)
    logger.info("Adding 20 Optimization Tests to Database")
    logger.info("=" * 80)

    # Initialize database
    engine = init_db('sqlite:///./data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Delete existing pending tests (clean slate)
        deleted = session.query(PlannedTest).filter_by(status='pending').delete()
        session.commit()
        logger.info(f"Deleted {deleted} existing pending test(s)")

        # Calculate priority scores and add tests
        tests_with_scores = []

        for test_data in TESTS:
            # Calculate priority score
            priority_score = calculate_priority_score(
                expected_cop_gain_pct=test_data['expected_cop_gain'],
                cost_savings_month=test_data['cost_savings'],
                confidence_pct=test_data['confidence'] * 100,
                risk_level=test_data['risk'],
                num_parameters=test_data['num_params']
            )

            test_data['priority_score'] = priority_score
            tests_with_scores.append(test_data)

        # Sort by priority score (highest first)
        tests_with_scores.sort(key=lambda x: x['priority_score'], reverse=True)

        # Add tests to database
        added_count = 0
        for rank, test_data in enumerate(tests_with_scores, 1):
            # Get primary parameter
            param_ids = test_data['parameter_id'].split(',')
            primary_param_id = param_ids[0]

            # Get parameter from database
            parameter = session.query(Parameter).filter_by(
                parameter_id=primary_param_id
            ).first()

            if not parameter:
                logger.warning(f"Parameter {primary_param_id} not found in database, skipping test #{test_data['id']}")
                continue

            # Create planned test
            planned_test = PlannedTest(
                parameter_id=parameter.id,
                current_value=test_data['current_value'],
                proposed_value=test_data['proposed_value'],
                hypothesis=test_data['hypothesis'],
                expected_improvement=test_data['expected_improvement'],
                priority='high' if test_data['priority_score'] >= 65 else
                        'medium' if test_data['priority_score'] >= 45 else 'low',
                confidence=test_data['confidence'],
                reasoning=test_data['reasoning'],
                status='pending',
                proposed_at=datetime.utcnow()
            )

            session.add(planned_test)
            added_count += 1

            logger.info(f"Rank #{rank}: Test #{test_data['id']} - Priority Score: {test_data['priority_score']:.1f} - {test_data['hypothesis'][:60]}...")

        # Commit all tests
        session.commit()

        logger.success(f"✅ Successfully added {added_count} tests to database!")
        logger.info("")
        logger.info("=" * 80)
        logger.info("PRIORITY DISTRIBUTION")
        logger.info("=" * 80)

        high_count = session.query(PlannedTest).filter_by(status='pending', priority='high').count()
        medium_count = session.query(PlannedTest).filter_by(status='pending', priority='medium').count()
        low_count = session.query(PlannedTest).filter_by(status='pending', priority='low').count()

        logger.info(f"HIGH priority:   {high_count} tests (score >= 65)")
        logger.info(f"MEDIUM priority: {medium_count} tests (score 45-64)")
        logger.info(f"LOW priority:    {low_count} tests (score < 45)")
        logger.info("")
        logger.info(f"Total: {high_count + medium_count + low_count} tests ready for execution")
        logger.info("")
        logger.info("View tests at: http://192.168.86.34:8502/ai-agent")

    except Exception as e:
        logger.error(f"Failed to add tests: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == '__main__':
    main()
