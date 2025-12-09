"""
Analyze heat pump parameters to identify optimization opportunities
"""
import json
from collections import defaultdict
from loguru import logger

def analyze_parameters():
    """Analyze all parameters and categorize them"""

    # Load data
    with open('data/all_data_points.json', 'r', encoding='utf-8') as f:
        points = json.load(f)

    # Categorize parameters
    writable = []
    read_only = []

    temperatures = []
    heating_curve = []
    degree_minutes = []
    compressor_params = []
    hot_water_params = []
    smart_price = []
    operational_stats = []

    for point in points:
        param_id = point['parameterId']
        param_name = point['parameterName']
        is_writable = point['writable']
        value = point['value']
        unit = point.get('parameterUnit', '')

        param_info = {
            'id': param_id,
            'name': param_name,
            'value': value,
            'unit': unit,
            'writable': is_writable,
            'minValue': point.get('minValue'),
            'maxValue': point.get('maxValue'),
            'stepValue': point.get('stepValue')
        }

        if is_writable:
            writable.append(param_info)
        else:
            read_only.append(param_info)

        # Categorize by function
        name_lower = param_name.lower()

        if '°C' in unit and not is_writable:
            temperatures.append(param_info)

        if 'curve' in name_lower or 'flow line temp' in name_lower:
            heating_curve.append(param_info)

        if 'degree' in name_lower and 'minute' in name_lower:
            degree_minutes.append(param_info)

        if 'compressor' in name_lower or 'frequency' in name_lower:
            compressor_params.append(param_info)

        if 'hot water' in name_lower or 'varmvatten' in name_lower:
            hot_water_params.append(param_info)

        if 'smart price' in name_lower:
            smart_price.append(param_info)

        if 'oper' in name_lower and ('time' in name_lower or 'starts' in name_lower):
            operational_stats.append(param_info)

    # Print analysis
    logger.info(f"\n{'='*80}")
    logger.info(f"PARAMETER ANALYSIS - Nibe F730")
    logger.info(f"{'='*80}\n")

    logger.info(f"Total parameters: {len(points)}")
    logger.info(f"  - Writable (can optimize): {len(writable)}")
    logger.info(f"  - Read-only (for monitoring): {len(read_only)}\n")

    # WRITABLE PARAMETERS (OPTIMIZATION TARGETS)
    logger.info(f"{'='*80}")
    logger.info(f"🎯 WRITABLE PARAMETERS (Optimization Targets)")
    logger.info(f"{'='*80}\n")

    # Group writable by category
    writable_heating = [p for p in writable if 'curve' in p['name'].lower() or 'flow line temp' in p['name'].lower() or 'offset' in p['name'].lower()]
    writable_dm = [p for p in writable if 'DM' in p['unit'] or 'degree minute' in p['name'].lower()]
    writable_hw = [p for p in writable if 'hot water' in p['name'].lower()]
    writable_other = [p for p in writable if p not in writable_heating + writable_dm + writable_hw]

    if writable_heating:
        logger.info(f"📈 HEATING CURVE & TEMPERATURE SETTINGS ({len(writable_heating)}):")
        for p in writable_heating:
            logger.info(f"  {p['id']:>6} | {p['name']:<50} | Current: {p['value']:>7} {p['unit']}")
            if p['minValue'] is not None:
                logger.info(f"         | Range: {p['minValue']} to {p['maxValue']}, Step: {p['stepValue']}")
        logger.info("")

    if writable_dm:
        logger.info(f"🌡️  DEGREE MINUTES (Critical for optimization!) ({len(writable_dm)}):")
        for p in writable_dm:
            logger.info(f"  {p['id']:>6} | {p['name']:<50} | Current: {p['value']:>7} {p['unit']}")
            if p['minValue'] is not None:
                logger.info(f"         | Range: {p['minValue']} to {p['maxValue']}, Step: {p['stepValue']}")
        logger.info("")

    if writable_hw:
        logger.info(f"💧 HOT WATER SETTINGS ({len(writable_hw)}):")
        for p in writable_hw:
            logger.info(f"  {p['id']:>6} | {p['name']:<50} | Current: {p['value']:>7} {p['unit']}")
            if p['minValue'] is not None and p['maxValue'] is not None:
                logger.info(f"         | Range: {p['minValue']} to {p['maxValue']}, Step: {p['stepValue']}")
        logger.info("")

    if writable_other:
        logger.info(f"⚙️  OTHER SETTINGS ({len(writable_other)}):")
        for p in writable_other[:10]:  # Show first 10
            logger.info(f"  {p['id']:>6} | {p['name']:<50} | Current: {p['value']:>7} {p['unit']}")
        logger.info("")

    # KEY MONITORING PARAMETERS
    logger.info(f"{'='*80}")
    logger.info(f"📊 KEY MONITORING PARAMETERS (Read-only)")
    logger.info(f"{'='*80}\n")

    key_temps = [
        ('40004', 'Outdoor temperature'),
        ('40067', 'Average outdoor temp'),
        ('13', 'Room temperature'),
        ('40008', 'Supply line (BT2)'),
        ('40012', 'Return line (BT3)'),
        ('40013', 'Hot water top (BT7)'),
        ('40018', 'Discharge (BT14)'),
        ('40020', 'Evaporator (BT16)'),
        ('43009', 'Calculated supply climate system 1')
    ]

    logger.info("🌡️  KEY TEMPERATURES:")
    for param_id, name in key_temps:
        point = next((p for p in temperatures if p['id'] == param_id), None)
        if point:
            logger.info(f"  {point['id']:>6} | {point['name']:<40} | {point['value']:>8} {point['unit']}")
    logger.info("")

    logger.info("⚡ COMPRESSOR & PERFORMANCE:")
    for p in compressor_params:
        if not p['writable']:
            logger.info(f"  {p['id']:>6} | {p['name']:<40} | {p['value']:>8} {p['unit']}")
    logger.info("")

    logger.info("📈 DEGREE MINUTES (System balance indicator):")
    for p in degree_minutes:
        logger.info(f"  {p['id']:>6} | {p['name']:<40} | {p['value']:>8} {p['unit']}")
    logger.info("")

    logger.info("📊 OPERATIONAL STATISTICS:")
    for p in operational_stats:
        logger.info(f"  {p['id']:>6} | {p['name']:<40} | {p['value']:>8} {p['unit']}")
    logger.info("")

    # OPTIMIZATION RECOMMENDATIONS
    logger.info(f"{'='*80}")
    logger.info(f"💡 OPTIMIZATION RECOMMENDATIONS")
    logger.info(f"{'='*80}\n")

    logger.info("1. **PRIMARY OPTIMIZATION PARAMETERS:**")
    logger.info("   - 47007: Heating curve (0-15) - Controls supply temp vs outdoor temp")
    logger.info("   - 47011: Offset (-10 to 10) - Fine-tune heating level")
    logger.info("   - 47206: Start compressor (-1000 to -30 DM) - When to start heating")
    logger.info("   - 48072: Start additional heat (100-2000 DM) - When to use electric backup\n")

    logger.info("2. **HEATING CURVE POINTS (47020-47026):**")
    logger.info("   - Define supply temp at different outdoor temps")
    logger.info("   - Can create custom heating curve for your house\n")

    logger.info("3. **HOT WATER:**")
    logger.info("   - 47041: Hot water demand (Economy/Normal/Lux)")
    logger.info("   - 48132: Hot water boost (temporary increase)\n")

    logger.info("4. **KEY MONITORING FOR OPTIMIZATION:**")
    logger.info("   - 40940/40941: Degree minutes (balance indicator)")
    logger.info("   - 41778: Compressor frequency (20-120 Hz)")
    logger.info("   - 13: Room temperature (comfort)")
    logger.info("   - 43084: Internal additional heat (minimize this!)\n")

    logger.info("5. **OPTIMIZATION STRATEGY:**")
    logger.info("   a. Monitor degree minutes - should hover around -200 DM")
    logger.info("   b. Adjust heating curve to maintain comfort with minimal overshoot")
    logger.info("   c. Tune start compressor threshold to avoid short cycling")
    logger.info("   d. Minimize use of electrical backup heating (expensive!)")
    logger.info("   e. Monitor COP indicators: discharge temp, evaporator temp, compressor freq\n")

    # Save writable parameters to JSON
    output = {
        'writable_parameters': writable,
        'key_monitoring': {
            'temperatures': key_temps,
            'compressor': [p for p in compressor_params if not p['writable']],
            'degree_minutes': degree_minutes,
            'operational_stats': operational_stats
        },
        'optimization_targets': {
            'heating_curve': writable_heating,
            'degree_minutes': writable_dm,
            'hot_water': writable_hw
        }
    }

    with open('data/optimization_parameters.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info(f"{'='*80}")
    logger.info(f"✓ Analysis complete!")
    logger.info(f"✓ Writable parameters saved to: data/optimization_parameters.json")
    logger.info(f"{'='*80}")

if __name__ == '__main__':
    analyze_parameters()
