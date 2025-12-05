# Delta T Calculation Improvement

## Overview

Improved the Delta T (temperature differential) calculation to provide more accurate system performance metrics by filtering for active heating periods and separating hot water production from space heating.

## Changes Made

### 1. Enhanced EfficiencyMetrics Dataclass

Added two new fields to track separate Delta T values:
- `delta_t_active`: Delta T during active space heating only
- `delta_t_hot_water`: Delta T during hot water production

### 2. New Operating Mode Thresholds

```python
COMPRESSOR_ACTIVE_THRESHOLD = 20.0  # Hz - Minimum frequency for active heating
HOT_WATER_TEMP_THRESHOLD = 45.0     # °C - Supply temp above this indicates hot water
```

### 3. New _calculate_active_delta_t() Method

Implements intelligent filtering and matching:
- Uses 5-minute time tolerance to match readings across parameters
- Filters for compressor frequency >20 Hz (active heating)
- Separates readings by supply temperature:
  - **<45°C**: Space heating
  - **>45°C**: Hot water production

### 4. Updated GUI (gui.py)

- Main dashboard now shows active space heating Delta T
- Added dedicated "📊 Delta T Analysis" section with breakdown:
  - All readings (includes standby)
  - Space heating (active only)
  - Hot water production
- Updated recommendations tab to use active Delta T

### 5. Updated Analyzer Output (analyzer.py)

Enhanced console output to show all three Delta T values with proper labeling.

## Results

### Test Data (7-day period):

| Metric | All Readings | Active Space Heating | Hot Water |
|--------|-------------|---------------------|-----------|
| 24h | 5.0°C | 5.4°C ✅ | 6.3°C |
| 72h | 4.5°C | 5.2°C ✅ | 5.7°C |
| 168h | 3.7°C | 4.9°C ✅ | 6.5°C |

### Key Findings:

1. **Accuracy Improvement**: Active space heating Delta T is 1.2°C higher than all-readings average (7-day: 4.9°C vs 3.7°C)

2. **Why the Difference?**
   - "All readings" includes standby periods when supply and return converge
   - This artificially lowers the average
   - Active filtering gives true heating performance

3. **Hot Water Production**
   - Consistently higher Delta T (6.5°C) due to higher temperature operation
   - Now tracked separately for better system understanding

## System Context

**Nibe F730 Mixed Heating System:**
- Ground floor: Underfloor heating (27-30°C via shunt)
- Floors 2-3: Radiators (36-40°C direct)
- Supply: 36-40°C main loop
- Return: Blended from both zones (~33-34°C)

**Target Delta T:**
- Mixed systems: 3-5°C is acceptable ✅
- Pure radiator systems: 5-8°C optimal
- Current active space heating: 4.9°C (perfect!)

## Benefits

1. **More Accurate Performance Tracking**
   - Excludes standby periods
   - Represents actual heating efficiency

2. **Separate Hot Water Monitoring**
   - Understand hot water production patterns
   - Optimize hot water vs space heating balance

3. **Better System Diagnostics**
   - Identify issues with active heating specifically
   - Distinguish between space heating and hot water problems

## Technical Implementation

### Algorithm Flow:

```
For each supply temperature reading:
  ├─ Find closest return reading (within 5 min)
  ├─ Find closest compressor reading (within 5 min)
  └─ If both found and compressor >20 Hz:
      ├─ Calculate Delta T = Supply - Return
      └─ Classify by supply temperature:
          ├─ <45°C → Space heating
          └─ >45°C → Hot water
```

### Time Tolerance:

Used 5-minute (300 second) tolerance window to match readings across parameters, as myUplink API readings may not have identical timestamps.

## Files Modified

- `src/analyzer.py`: Core Delta T calculation logic
- `src/gui.py`: GUI display updates
- `docs/DELTA_T_IMPROVEMENT.md`: This documentation

## Testing

Verified correct operation:
- ✅ Analyzer console output shows all three values
- ✅ GUI loads without errors
- ✅ Time-based matching works across 7-day period
- ✅ Active space heating detected correctly
- ✅ Hot water production separated properly

## Usage

### Command Line:

```bash
python src/analyzer.py
```

Output includes:
```
ΔT (Supply-Return):
  All readings: 5.0°C
  Space heating (active): 5.4°C  ✅
  Hot water production: 6.3°C
```

### GUI:

```bash
streamlit run src/gui.py
```

Shows Delta T breakdown in dedicated section with hover tooltips explaining each metric.

## Conclusion

The improved Delta T calculation provides significantly more accurate system performance metrics by:
1. Filtering for active heating only (compressor >20 Hz)
2. Separating hot water production from space heating
3. Using intelligent time-based matching for parameter alignment

This gives a true representation of heating efficiency during actual operation, rather than including idle periods where temperatures naturally converge.

---

**Date**: 2025-11-25
**System**: Nibe F730 CU 3x400V
**Performance**: Delta T 4.9°C (active space heating) - Optimal for mixed low-temp system ✅
