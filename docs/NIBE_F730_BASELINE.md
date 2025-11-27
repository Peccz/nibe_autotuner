# Nibe F730 Technical Baseline

**Model:** Nibe F730 CU 3x400V (Control Unit)
**Type:** Exhaust Air Heat Pump with Integrated Water Heater
**Serial:** 06615522045017

This document provides manufacturer specifications, optimal settings, and technical parameters for the Nibe F730 heat pump system used in the Nibe Autotuner project.

---

## 1. Technical Specifications

### Compressor
- **Type:** Inverter controlled variable speed compressor
- **Power Output Range:** 1.1 - 6.0 kW
- **Control:** Frequency modulated for optimal efficiency
- **Operating Range:** Variable frequency control for load matching

### Exhaust Air System
- **Extract Air Temperature Range:** Down to -15°C
- **Critical Temperature Threshold:** 6°C (compressor blocked below this, electric backup engages)
- **Exhaust Air Flow Rates:**
  - Minimum: 90 m³/h (25 l/s) at minimum compressor frequency
  - Standard: 180 m³/h
  - Maximum: 252 m³/h (70 l/s) at minimum compressor frequency

### Performance Standards
- **Testing Standard:** EN 14511
- **Rating Condition:** A20(12)W35 at 252 m³/h at minimum compressor speed
- **Seasonal Performance:** SCOP rated according to EN 14825 for cold climate at 35°C

**Sources:**
- [NIBE F730 Technical Specifications](https://www.archiexpo.com/prod/nibe-energy-systems/product-73261-1752902.html)
- [NIBE Exhaust Air Heat Pumps](https://www.nibe.eu/en-eu/products/heat-pumps/exhaust-air-heat-pumps)

---

## 2. Heating Curve Settings

### Basic Principles
The heating curve determines supply temperature based on outdoor temperature for energy-efficient operation. The control computer calculates the required supply temperature to maintain indoor comfort.

### Curve Characteristics
- **Curve Range:** 0-10 (or higher depending on system)
- **Slope Definition:** Degrees supply temperature increases/decreases per degree outdoor temperature change
- **Temperature Control Range:** 0-80°C flow line temperature
- **Adjustment Interval:** Wait 24 hours between changes for room temperature stabilization

### Temperature Ranges by Heating System

**Underfloor Heating:**
- Max flow temperature: 35-45°C
- Lower curve settings recommended (typically 3-6)

**Low Temperature Radiators:**
- Supply temperature: 35-40°C (mild weather) to 45-50°C (coldest day)
- Medium curve settings (typically 5-8)

### Curve Offset
- **Function:** Shifts entire curve up/down by same amount at all outdoor temperatures
- **Typical Adjustment:** ±2 steps = ±5°C supply temperature
- **Use Case:** Fine-tuning after establishing base curve

### Optimal Settings Example (from field data)
Based on real-world optimization of Nibe F1145 (similar system):
- **Conservative:** Curve 9 with -3 offset (higher temperatures)
- **Optimized:** Curve 5 with 0 offset (lower temperatures, better efficiency)
  - At +10°C outdoor: 27°C target flow
  - At 0°C outdoor: 32°C target flow
  - At -10°C outdoor: 36°C target flow

**Sources:**
- [Basic Values for Curve Settings - Nibe F730 Manual](https://www.manualslib.com/manual/1252238/Nibe-F730.html?page=31)
- [NIBE Heat Pump Curve Configuration](https://www.marshflattsfarm.org.uk/wordpress/?page_id=4933)
- [Exhaust Air Heat Pump F730 User Manual](https://manualzz.com/doc/28241796/nibe-f730-exhaust-air-heat-pump-user-manual)

---

## 3. Degree Minutes (DM) Control

### Factory Settings
- **Default Value:** -60 DM
- **Meaning:** Compressor starts/stops based on accumulated temperature deficit
- **Calculation:** Each minute, system calculates (actual flow temp - setpoint temp), accumulates values

### How It Works
1. Every minute: `DM_accumulator += (T_actual - T_setpoint)` (when negative)
2. When `DM_accumulator <= DM_threshold`, action triggers
3. Example with -60 DM setting:
   - 2°C below setpoint in minute 1: stores -2
   - 3°C below setpoint in minute 2: accumulates to -5
   - Continues until reaching -60, then compressor shuts down

### Optimal Settings
- **Factory Default:** -60 DM (more frequent cycling)
- **Optimized for Efficiency:** -200 DM (longer run times, fewer starts)
- **Autotuner Target:** -200 DM for optimal balance
- **Comfort Zone:** -300 to -100 DM

### Benefits of Lower DM Values (e.g., -200)
- Keeps compressor running longer
- Prevents premature shutdown when hot water demand satisfied
- Reduces start/stop cycling (extends compressor life)
- Better efficiency through sustained operation

**Sources:**
- [Degree Minutes Explanation - DIYnot Forums](https://www.diynot.com/diy/threads/degree-minutes.243571/)
- [Nibe Exhaust Air Heat Pump Help](https://forums.moneysavingexpert.com/discussion/6153717/nibe-exhaust-air-heat-pump-help)

---

## 4. Temperature Differential (Delta T)

### Optimal Ranges
Based on general heat pump research (see SCIENTIFIC_BASELINE.md):
- **Optimal:** 5-8°C for air source and exhaust air heat pumps
- **Acceptable:** 3-5°C (suboptimal but functional)
- **Poor:** <3°C (insufficient heat extraction) or >10°C (low flow rate)

### Impact on Efficiency
- Every 1.7°C reduction in return temperature = 1% efficiency gain
- Lower delta T indicates insufficient heat extraction from heating system
- Higher delta T indicates low flow rate or undersized heat distribution

### System-Specific Considerations
For exhaust air heat pumps like F730:
- Supply temperature typically 35-45°C (depending on heating system)
- Return temperature should be 5-8°C cooler
- Monitor during various outdoor conditions for consistency

**Sources:**
- [Scientific Baseline Document](./SCIENTIFIC_BASELINE.md)
- Deppmann Associates research cited in Scientific Baseline

---

## 5. Hot Water Settings

### Temperature Recommendations
- **Optimal:** 45°C (most efficient)
- **Standard:** 50°C (common default)
- **Maximum:** 55°C (beyond this, electric backup typically required)
- **Not Recommended:** 60°C (requires significant electric boost, reduces COP)

### Efficiency Principle
Heat pumps operate more efficiently at lower output temperatures:
- Less power consumption for longer operation
- Higher COP at lower temperature differentials
- Reduced reliance on electric backup heating

**Source:**
- [NIBE Ground Source Heat Pump Settings](https://www.avforums.com/threads/nibe-ground-source-heat-pump-correct-settings.2078187/)

---

## 6. Performance Validation

### Expected COP (Coefficient of Performance)

Based on system data (70.6 days):
- **Measured COP:** 3.11 at 1.1°C outdoor temperature
- **Assessment:** Excellent performance ✅
- **Validation:** Confirms 45% Carnot efficiency factor used in calculations

### Degree Minutes Validation
- **Measured:** -212 DM
- **Target:** -200 DM
- **Assessment:** Perfect ✅
- **Status:** Operating in optimal comfort/efficiency zone

### Delta T Assessment
- **Measured:** 3.1°C
- **Target:** 5-8°C
- **Assessment:** Suboptimal ⚠️
- **Recommendation:** Investigate flow rate or heat distribution system sizing

---

## 7. Advanced Settings (Installer Menu)

### Menu Structure
Advanced settings accessible through installer menu (typically menu 2.9 or 5.x):

**Key Parameters:**
- Heating curve slope
- Heating curve offset
- Minimum supply temperature
- Maximum supply temperature
- Degree minutes threshold
- Room sensor configuration
- Hot water temperature setpoint
- Periodic increase settings
- External contact adjustments
- Night cooling configuration

### Safety Considerations
- Always wait 24-48 hours between adjustments
- Monitor system performance after changes
- Document original settings before modifications
- Understand parameter interactions (curve + offset)

**Sources:**
- [NIBE F730 Installer Manual](https://www.manualslib.com/manual/1619931/Nibe-F730.html)
- [Installer Manual NIBE F730](https://www.nibe.eu/assets/documents/18806/M12000-1.pdf)

---

## 8. Operational Constraints

### Temperature Limitations
- **Exhaust Air Block:** Compressor blocked if exhaust air <6°C
- **Electric Backup Activation:** Engages when heat pump cannot meet demand
- **Extract Air Minimum:** Can operate down to -15°C extract air temperature
- **Flow Temperature Range:** 20-80°C (configurable min/max)

### Ventilation Control
- **Min. Diff. Indoor-Outdoor Temp:** Controls ventilation speed
- **Speed 4 Activation:** When temp difference exceeds setpoint AND exhaust air temp > "Start temp exhaust air"
- **Purpose:** Optimize ventilation based on thermal conditions

**Sources:**
- [NIBE F730 Technical Specifications](https://www.archiexpo.com/prod/nibe-energy-systems/product-73261-1752902.html)

---

## 9. Integration with Nibe Autotuner

### Parameter Monitoring
The Nibe Autotuner monitors these critical parameters from your F730:

**Core Metrics:**
- `40004` - Outdoor Temperature (BT1)
- `40033` - Supply Temperature (BT2)
- `40012` - Return Temperature (BT3)
- `40008` - Heat Fluid In (BT10)
- `40007` - Heat Fluid Out (BT11)
- `40067` - Average Indoor Temperature (BT50)
- `43009` - Calculated Supply Temperature
- `43005` - Degree Minutes
- `43136` - Compressor Frequency
- `47011` - Heating Curve (P1.2.1)
- `48132` - Heating Offset (P1.2.2)

### Validation Rules
Based on manufacturer specifications, the Autotuner validates:

1. **COP Estimation:** Using 45% Carnot efficiency factor
2. **Degree Minutes Target:** -200 DM (range: -300 to -100)
3. **Delta T Target:** 5-8°C (warning: 3-5°C or 8-10°C, alert: <3°C or >10°C)
4. **Heating Curve Range:** Typically 3-9 for residential systems
5. **Supply Temperature:** Within configured min/max (check compressor isn't blocked)

### Recommendation Logic
The system generates recommendations when:
- Delta T <5°C → Check flow rate, consider heating curve adjustment
- Degree Minutes <-300 or >-100 → Adjust DM threshold
- Supply temp frequently at max → Increase heating curve slope
- COP <2.5 consistently → Review system configuration, check for issues

---

## 10. References and Documentation

### Official NIBE Documentation
- [Installer Manual NIBE F730 (PDF)](https://www.nibe.eu/assets/documents/24233/431700-1.pdf)
- [User Manual NIBE F730 (PDF)](https://www.nibe.eu/assets/documents/19520/M12090-1.pdf)
- [F730 Product Brochure (PDF)](https://www.nibe.eu/assets/documents/31344/531379-2.pdf)

### ManualsLib Resources
- [NIBE F730 Installer Manual](https://www.manualslib.com/manual/1619931/Nibe-F730.html)
- [NIBE F730 User Manual](https://www.manualslib.com/manual/1617983/Nibe-F730.html)
- [NIBE F730 Installation Guide](https://www.manualslib.com/manual/3489978/Nibe-F730.html)

### Community Resources
- [NIBE Heat Pump Curve Configuration - Marsh Flatts Farm](https://www.marshflattsfarm.org.uk/wordpress/?page_id=4933)
- [Degree Minutes Discussion - DIYnot Forums](https://www.diynot.com/diy/threads/degree-minutes.243571/)
- [Nibe Settings Optimization - AVForums](https://www.avforums.com/threads/nibe-ground-source-heat-pump-correct-settings.2078187/)

### Scientific Research
See [SCIENTIFIC_BASELINE.md](./SCIENTIFIC_BASELINE.md) for academic research citations on:
- COP calculations and Carnot efficiency
- Delta T optimization studies
- Heating curve optimization research (2024-2025)
- Thermal mass control and degree minutes

---

## 11. System Health Indicators

### Green Status ✅ (Optimal)
- COP ≥ 3.0
- Degree Minutes: -300 to -100 DM
- Delta T: 5-8°C
- Supply temp within configured range
- Compressor frequency varying appropriately
- No frequent electric backup activation

### Yellow Status ⚠️ (Monitor)
- COP: 2.5-3.0
- Degree Minutes: -400 to -300 or -100 to 0
- Delta T: 3-5°C or 8-10°C
- Occasional electric backup usage
- Slight deviations from target parameters

### Red Status ❌ (Action Required)
- COP <2.5 (when outdoor temp >-5°C)
- Degree Minutes: <-400 or >0
- Delta T: <3°C or >10°C
- Frequent electric backup activation
- Compressor frequently at minimum or maximum frequency
- Exhaust air temperature frequently <6°C

---

## Validation Against Real Data

Using 70.6 days of operational data (September-November 2025):

| Metric | Measured Value | Target/Optimal | Status |
|--------|----------------|----------------|--------|
| COP | 3.11 | ≥3.0 | ✅ Excellent |
| Degree Minutes | -212 DM | -200 DM | ✅ Perfect |
| Delta T | 3.1°C | 5-8°C | ⚠️ Suboptimal |
| Heating Curve | 7.0 | 5-9 | ✅ Good |
| Curve Offset | -1.0 | -3 to +3 | ✅ Good |
| Avg Compressor Freq | Varying | Variable | ✅ Good |

**Overall Assessment:** System operating efficiently with room for minor optimization in heat distribution (Delta T improvement).

---

**Document Version:** 1.0
**Last Updated:** 2025-11-24
**Data Source:** 70.6 days real operational data + manufacturer specifications
**Model:** Nibe F730 CU 3x400V (Serial: 06615522045017)
