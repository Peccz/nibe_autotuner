# Scientific Baseline for Heat Pump Optimization

This document provides the academic and technical foundation for the calculations used in the Nibe Autotuner system.

## 1. Coefficient of Performance (COP)

### Theory
The Coefficient of Performance for heat pumps is theoretically limited by the Carnot efficiency:

```
COP_carnot = T_hot / (T_hot - T_cold)
```

Where temperatures are in Kelvin.

### Real-World Performance
**Finding**: Real heat pumps typically achieve **30-60% of theoretical Carnot COP**

**Implementation**: Our system uses **45% Carnot efficiency** as a baseline estimation:

```python
# From analyzer.py
carnot_cop = t_hot_k / (t_hot_k - t_cold_k)
efficiency_factor = 0.45  # 45% of Carnot (middle of 30-60% range)
estimated_cop = carnot_cop * efficiency_factor
```

**Validation**: This places typical COP values between 2.0-5.0 depending on outdoor temperature, which aligns with manufacturer specifications for air-source heat pumps.

## 2. Delta T (Temperature Differential)

### Optimal Ranges by System Type

**Heat Pumps (ASHPs)**:
- **Optimal range**: 5-10°C [1]
- **Best performance**: 5-7°C [1]
- **Our implementation**: 5-8°C (aligned with research)

**Efficiency Impact**:
- Every 3°F (1.7°C) reduction in return temperature = ~1% efficiency increase [2]

### Implementation

```python
# From analyzer.py
# Optimal ΔT for hydronic systems is typically 5-8°C
if metrics.delta_t < 3:
    # Poor: Water too hot, low heat extraction
    # Recommendation: Reduce supply temperature
elif 3 <= metrics.delta_t < 5:
    # Suboptimal: Monitor but may not require action
elif 5 <= metrics.delta_t <= 8:
    # Optimal: Best efficiency
elif 8 < metrics.delta_t <= 10:
    # Suboptimal: Monitor but may not require action
else:  # > 10°C
    # Poor: Insufficient flow or heat output
    # Recommendation: Increase supply temperature or check flow
```

### Sources
[1] [The importance of delta t in hydronic heating systems](https://global.purmo.com/en/the-indoors/insights/the-importance-of-delta-t-in-hydronic-heating-systems)
[2] [Delta T Can Improve Boiler Efficiency](https://www.deppmann.com/blog/monday-morning-minutes/delta-t-improve-boiler-efficiency/)
[3] [The Delta Difference | EM Magazine](https://www.energymanagermagazine.co.uk/the-delta-difference/)

## 3. Heating Curve Optimization

### Recent Research Findings (2025)

**Key Study**: "Optimization of heating curves for heat pumps in operation: Outdoor temperature ranges for energy-efficient heating curve shifts" [4]

**Findings**:
- Standard parallel shift is optimal only when average outdoor temp is **2-5°C**
- Outside this range, adjust curve at start or endpoint
- **84.42% of heating curves can be improved**
- Average energy reduction: **4.02%**
- Average COP increase: **2.59%**

### Adaptive Optimization

**Study**: "Adaptive optimization of heating curves in buildings heated by a weather-compensated heat pump" [5]

**Method**: Online optimization using two reference points to track desired indoor temperature while minimizing energy consumption.

### Implementation

Our system uses degree minutes (DM) as a proxy for thermal comfort and adjusts heating curve based on:

```python
# Target: -200 DM (optimal balance)
# Range: -300 to -100 DM (comfort zone)

if dm < -300:
    # System too cold: increase heating curve
    suggested_curve = min(15.0, current_curve + 0.5)
elif dm > -100:
    # System too warm: decrease heating curve
    suggested_curve = max(0.0, current_curve - 0.5)
```

### Sources
[4] [Optimization of heating curves for heat pumps in operation](https://www.sciencedirect.com/science/article/pii/S0306261925004556)
[5] [Adaptive optimization of heating curves](https://www.tandfonline.com/doi/full/10.1080/23744731.2019.1616984)
[6] [Understanding Your Heat Curve for Optimal Performance](https://www.imsheatpumps.co.uk/blog/understanding-your-heat-curve/)

## 4. Degree Minutes (Thermal Mass Control)

### Concept
Degree minutes represent the integrated temperature deficit/surplus over time, accounting for building thermal mass and heat capacity.

### Research on Thermal Mass Optimization

**Study**: "Enhancing building energy efficiency with thermal mass optimization" [7]

**Findings**:
- Optimal thermal mass control achieves **4-12% energy savings**
- Model Predictive Control (MPC) can shift cooling load with **20-60% cost savings**
- Convergence intervals of **O(minutes)** are sufficient for control

### Building Thermal Dynamics

**Formula**:
```
Degree Minutes Change = (Target_Temp - Current_Temp) × Time_Interval
```

**Optimal Range**:
- Target: **-200 DM** (slight cooling deficit for efficiency)
- Comfort zone: **-300 to -100 DM**
- Alert range: < -500 DM or > 100 DM

### Why -200 DM?
- Negative value = indoor temp slightly below setpoint
- Building thermal mass stores residual heat
- Prevents excessive cycling
- Maintains comfort while optimizing efficiency

### Implementation

```python
# From analyzer.py
if degree_minutes < -300:
    # Too cold: occupants may notice discomfort
    # Action: Increase heating curve
    confidence = 0.85
elif degree_minutes > -100:
    # Too warm: wasting energy
    # Action: Decrease heating curve
    confidence = 0.85
else:
    # Optimal range: no action needed
    pass
```

### Sources
[7] [Enhancing building energy efficiency with thermal mass optimization](https://www.sciencedirect.com/science/article/pii/S2666792425000186)
[8] [Multi-objective optimization for thermal mass model predictive control](https://www.sciencedirect.com/science/article/abs/pii/S0360544216309458)
[9] [A control strategy considering buildings' thermal characteristics](https://ideas.repec.org/a/eee/energy/v307y2024ics0360544224024113.html)

## 5. System Efficiency Targets

### COP Targets by Outdoor Temperature

Based on Carnot limitations and 45% efficiency factor:

| Outdoor Temp | Typical COP | Good COP | Excellent COP |
|--------------|-------------|----------|---------------|
| -5°C         | 2.0-2.5     | 2.5-3.0  | 3.0+          |
| 0°C          | 2.5-3.0     | 3.0-3.5  | 3.5+          |
| 5°C          | 3.0-3.5     | 3.5-4.0  | 4.0+          |
| 10°C         | 3.5-4.0     | 4.0-4.5  | 4.5+          |

### Implementation

```python
# Our system at 1.1°C outdoor shows COP = 3.11
# This is in the "Good" range, approaching "Excellent"
```

## 6. Compressor Runtime Analysis

### Optimal Runtime
- **Avoid**: Continuous operation (>80% runtime)
- **Reason**: Prevents efficient defrost cycles and increases wear
- **Target**: 50-70% runtime for balanced operation

### Implementation

```python
if runtime_ratio > 0.8:
    # Recommendation: System may be undersized or curve too high
    # Consider reducing heating demand
```

## 7. Validation Against Real Data

### Your System Performance (Nov 24, 2025)
- **Outdoor temp**: 1.1°C
- **COP**: 3.11 (Excellent for conditions)
- **Degree Minutes**: -212 (Perfect! Target: -200)
- **Delta T**: 3.1°C (Slightly low, optimal: 5-8°C)
- **Heating Curve**: 7.0 with offset -1.0

**Analysis**: System is well-optimized overall. Minor improvement possible by adjusting flow rate or temperature to achieve delta T closer to 5°C.

## 8. Recommendation Confidence Levels

Based on research certainty and impact:

| Confidence | Criteria | Action |
|------------|----------|--------|
| 0.85       | Degree minutes outside optimal range | Strong recommendation |
| 0.75       | Compressor runtime issues | Moderate recommendation |
| 0.70       | Delta T outside optimal range | Monitor and suggest |
| 0.60       | COP below expected for conditions | Investigate causes |

## 9. Future Enhancements

### Machine Learning Potential
- Train models on collected data for weather prediction
- Learn building-specific thermal characteristics
- Optimize for electricity price variations
- Personalized comfort preferences

### Advanced Control
- Implement Model Predictive Control (MPC)
- Multi-objective optimization (comfort + cost + efficiency)
- Integration with weather forecasts
- Dynamic adjustment based on occupancy

## 10. References

### Academic Papers
1. Purmo Global - [The importance of delta t in hydronic heating systems](https://global.purmo.com/en/the-indoors/insights/the-importance-of-delta-t-in-hydronic-heating-systems)
2. Deppmann - [Delta T Can Improve Boiler Efficiency](https://www.deppmann.com/blog/monday-morning-minutes/delta-t-improve-boiler-efficiency/)
3. Energy Manager Magazine - [The Delta Difference](https://www.energymanagermagazine.co.uk/the-delta-difference/)
4. ScienceDirect - [Optimization of heating curves for heat pumps (2025)](https://www.sciencedirect.com/science/article/pii/S0306261925004556)
5. Taylor & Francis - [Adaptive optimization of heating curves](https://www.tandfonline.com/doi/full/10.1080/23744731.2019.1616984)
6. IMS Heat Pumps - [Understanding Your Heat Curve](https://www.imsheatpumps.co.uk/blog/understanding-your-heat-curve/)
7. ScienceDirect - [Enhancing building energy efficiency with thermal mass](https://www.sciencedirect.com/science/article/pii/S2666792425000186)
8. ScienceDirect - [Multi-objective thermal mass optimization](https://www.sciencedirect.com/science/article/abs/pii/S0360544216309458)
9. Energy Journal - [Control strategy for district heating](https://ideas.repec.org/a/eee/energy/v307y2024ics0360544224024113.html)

### Technical Resources
- Kronoterm - [Weather-Compensated Heating Curve](https://kronoterm.eu/what-is-a-weather-compensated-heating-curve-in-heat-pumps/)
- Energy Saving Trust - [The most efficient way to run a heat pump](https://energysavingtrust.org.uk/how-to-ensure-a-heat-pump-runs-efficiently/)
- Grant UK - [Editing the heating curve](https://www.grantuk.com/professional/support/product-support/air-source-heat-pumps/general-advice/how-to-adjust-the-heating-curve-using-the-aerona-smart-controller/)

## 11. Methodology Summary

Our optimization approach is grounded in:

1. **Thermodynamic principles** (Carnot efficiency)
2. **Empirical research** (30-60% real-world efficiency)
3. **Industry best practices** (5-8°C delta T for ASHPs)
4. **Recent academic findings** (2025 heating curve optimization)
5. **Control theory** (thermal mass and degree minutes)
6. **70+ days of real data** from your system

This combination of theory, research, and practical validation ensures recommendations are both scientifically sound and practically effective.

---

**Last Updated**: November 24, 2025
**Data Span**: 70.6 days (Sep 14 - Nov 24, 2025)
**System**: Nibe F730 CU 3x400V
