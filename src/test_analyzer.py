"""
Test the analyzer module with current data
"""
from loguru import logger
from analyzer import HeatPumpAnalyzer
from models import init_db, ParameterReading
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func

def check_data_availability():
    """Check how much data is available in the database"""
    engine = init_db('sqlite:///./data/nibe_autotuner.db')
    SessionMaker = sessionmaker(bind=engine)
    session = SessionMaker()

    # Count total readings
    total_readings = session.query(func.count(ParameterReading.id)).scalar()

    # Count unique timestamps
    unique_timestamps = session.query(
        func.count(func.distinct(ParameterReading.timestamp))
    ).scalar()

    # Get time range
    first_reading = session.query(
        func.min(ParameterReading.timestamp)
    ).scalar()

    last_reading = session.query(
        func.max(ParameterReading.timestamp)
    ).scalar()

    session.close()

    logger.info("="*80)
    logger.info("DATABASE STATUS")
    logger.info("="*80)
    logger.info(f"Total readings: {total_readings}")
    logger.info(f"Unique timestamps: {unique_timestamps}")
    logger.info(f"First reading: {first_reading}")
    logger.info(f"Last reading: {last_reading}")

    if first_reading and last_reading:
        duration = last_reading - first_reading
        hours = duration.total_seconds() / 3600
        logger.info(f"Data span: {hours:.1f} hours ({duration})")

    logger.info("")

    return unique_timestamps

def main():
    """Test the analyzer"""
    # Check data availability
    timestamps = check_data_availability()

    if timestamps < 2:
        logger.warning("⚠️  Insufficient data for analysis")
        logger.warning("   Need at least 2 readings (10 minutes of data)")
        logger.warning("   Current readings: {}".format(timestamps))
        logger.warning("")
        logger.warning("💡 The data logger service needs to run for a while to collect data.")
        logger.warning("   Install and start it with: ./install_service.sh")
        logger.warning("")
        logger.info("Testing analyzer with available data anyway...")
        logger.info("")

    # Test the analyzer
    try:
        analyzer = HeatPumpAnalyzer()

        logger.info("Testing metrics calculation...")
        metrics = analyzer.calculate_metrics(hours_back=24)

        logger.info("✅ Metrics calculated successfully")
        logger.info("")

        logger.info("Testing recommendation generation...")
        recommendations = analyzer.generate_recommendations(hours_back=24)

        logger.info(f"✅ Generated {len(recommendations)} recommendations")
        logger.info("")

        if timestamps >= 2:
            # Only run the full report if we have enough data
            logger.info("Running full analysis...")
            from analyzer import main as run_analysis
            run_analysis()
        else:
            logger.info("Skipping full analysis - need more data points")
            logger.info("The analyzer module is ready and will work once data is collected.")

    except Exception as e:
        logger.error(f"❌ Error testing analyzer: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
