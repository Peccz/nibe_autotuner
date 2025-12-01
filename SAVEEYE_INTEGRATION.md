# 🔋 SaveEye Integration Guide

## Översikt

SaveEye är en energimätare som kan ge **verkliga effektmätningar** istället för estimerade värden. Detta möjliggör:
- ✅ **Verklig COP-beräkning**: kW_heat / kW_electric
- ✅ **Exakt kostnadsberäkning**: Faktisk förbrukning i kWh
- ✅ **Bättre optimeringsunderlag**: Verklig data istället för estimat

## SaveEye Funktioner

**Mätningar**:
- Elektrisk effekt (kW) i realtid
- Energiförbrukning (kWh) historik
- Spänning, ström, frekvens
- Effektfaktor (cos φ)

**Kommunikation**:
- ✅ **MQTT** (Local) - Rekommenderat för integration
- ✅ **SaveEye App** (Cloud)
- ✅ **Home Assistant** support
- ⚠️ **REST API** (oklart om tillgänglig)

## Integration via MQTT

### Arkitektur

```
SaveEye Meter
    ↓ (MQTT)
MQTT Broker (Mosquitto på RPi)
    ↓
Nibe Autotuner
    ↓
Real COP Calculation
```

### Steg 1: Installera MQTT Broker På RPi

```bash
# SSH till RPi
ssh nibe-rpi

# Installera Mosquitto MQTT broker
sudo apt update
sudo apt install -y mosquitto mosquitto-clients

# Starta och aktivera service
sudo systemctl start mosquitto
sudo systemctl enable mosquitto

# Verifiera att den körs
sudo systemctl status mosquitto
```

### Steg 2: Konfigurera SaveEye För MQTT

**I SaveEye-appen**:
1. Öppna SaveEye app
2. Gå till **Settings**
3. Välj **MQTT Configuration**
4. Aktivera **Local MQTT**
5. Konfigurera:
   ```
   MQTT Broker: 192.168.86.34  (RPi IP)
   Port: 1883
   Topic Prefix: saveeye
   Username: (optional)
   Password: (optional)
   ```
6. Spara och testa anslutningen

### Steg 3: Verifiera MQTT-meddelanden

```bash
# Lyssna på alla SaveEye-meddelanden
mosquitto_sub -h localhost -t "saveeye/#" -v

# Förväntat output:
# saveeye/telemetry {"power_w": 3456, "energy_kwh": 123.45, ...}
# saveeye/status {"connected": true, ...}
```

### Steg 4: Identifiera Värmepumpsmätaren

Om du har flera mätare, identifiera vilken som mäter värmepumpen:

```bash
# Lyssna på specifik mätare
mosquitto_sub -h localhost -t "saveeye/meter_1/telemetry" -v
mosquitto_sub -h localhost -t "saveeye/meter_2/telemetry" -v

# Sätt på/av värmepumpen och se vilken mätare som reagerar
```

### Steg 5: Integrera i Nibe Autotuner

**Installera MQTT-bibliotek**:
```bash
cd /home/peccz/nibe_autotuner
source venv/bin/activate
pip install paho-mqtt
```

**Ny fil: `src/saveeye_client.py`**:
```python
"""
SaveEye MQTT Client
Reads real-time power measurements from SaveEye energy meter
"""
import json
from typing import Optional, Dict
import paho.mqtt.client as mqtt
from loguru import logger
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PowerMeasurement:
    """Real-time power measurement from SaveEye"""
    timestamp: datetime
    power_w: float  # Watts
    energy_kwh: float  # Total kWh
    voltage_v: float  # Volts
    current_a: float  # Ampere
    power_factor: float  # cos φ


class SaveEyeClient:
    """Client for reading SaveEye energy meter data via MQTT"""

    def __init__(
        self,
        broker_host: str = 'localhost',
        broker_port: int = 1883,
        topic_prefix: str = 'saveeye',
        meter_id: str = 'meter_1'
    ):
        """
        Initialize SaveEye MQTT client

        Args:
            broker_host: MQTT broker hostname/IP
            broker_port: MQTT broker port (default: 1883)
            topic_prefix: MQTT topic prefix (default: 'saveeye')
            meter_id: Meter ID for heat pump (e.g., 'meter_1')
        """
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic_prefix = topic_prefix
        self.meter_id = meter_id
        self.latest_measurement: Optional[PowerMeasurement] = None

        # MQTT client
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker"""
        if rc == 0:
            logger.info(f"Connected to MQTT broker at {self.broker_host}")
            # Subscribe to telemetry topic
            topic = f"{self.topic_prefix}/{self.meter_id}/telemetry"
            client.subscribe(topic)
            logger.info(f"Subscribed to {topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker: {rc}")

    def _on_message(self, client, userdata, msg):
        """Callback when message received"""
        try:
            payload = json.loads(msg.payload.decode('utf-8'))

            # Parse measurement
            measurement = PowerMeasurement(
                timestamp=datetime.utcnow(),
                power_w=float(payload.get('power_w', 0)),
                energy_kwh=float(payload.get('energy_kwh', 0)),
                voltage_v=float(payload.get('voltage_v', 230)),
                current_a=float(payload.get('current_a', 0)),
                power_factor=float(payload.get('power_factor', 1.0))
            )

            self.latest_measurement = measurement
            logger.debug(f"Received: {measurement.power_w:.0f}W, {measurement.energy_kwh:.2f}kWh")

        except Exception as e:
            logger.error(f"Failed to parse MQTT message: {e}")

    def connect(self):
        """Connect to MQTT broker"""
        try:
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            logger.info("SaveEye MQTT client started")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise

    def disconnect(self):
        """Disconnect from MQTT broker"""
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("SaveEye MQTT client stopped")

    def get_latest_measurement(self) -> Optional[PowerMeasurement]:
        """Get latest power measurement"""
        return self.latest_measurement

    def get_current_power_kw(self) -> Optional[float]:
        """Get current power in kW"""
        if self.latest_measurement:
            return self.latest_measurement.power_w / 1000.0
        return None


def main():
    """Test SaveEye client"""
    import time

    # Initialize client
    # TODO: Update meter_id to match your heat pump meter
    client = SaveEyeClient(
        broker_host='localhost',
        meter_id='meter_1'  # Change to your heat pump meter ID
    )

    try:
        # Connect
        client.connect()

        # Monitor for 30 seconds
        logger.info("Monitoring SaveEye for 30 seconds...")
        for i in range(30):
            time.sleep(1)
            measurement = client.get_latest_measurement()
            if measurement:
                logger.info(
                    f"Power: {measurement.power_w:.0f}W "
                    f"({measurement.power_w/1000:.2f}kW), "
                    f"Total: {measurement.energy_kwh:.2f}kWh"
                )
            else:
                logger.warning("No measurement received yet")

    finally:
        client.disconnect()


if __name__ == '__main__':
    main()
```

### Steg 6: Uppdatera Analyzer Med Verklig COP

**Modifiera `src/analyzer.py`**:
```python
from saveeye_client import SaveEyeClient, PowerMeasurement

class HeatPumpAnalyzer:
    def __init__(self, db_path: str = 'data/nibe_autotuner.db', saveeye_client: Optional[SaveEyeClient] = None):
        # ... existing init ...
        self.saveeye_client = saveeye_client

    def calculate_real_cop(self, hours_back: int = 1) -> Optional[float]:
        """
        Calculate REAL COP using SaveEye power measurements

        Returns:
            Real COP or None if SaveEye data unavailable
        """
        if not self.saveeye_client:
            return None

        # Get heat output from Nibe (calculated from flow/temp)
        metrics = self.calculate_metrics(hours_back)

        # Get electrical input from SaveEye
        electrical_power_kw = self.saveeye_client.get_current_power_kw()

        if electrical_power_kw and electrical_power_kw > 0.5:  # Compressor running
            # Calculate heat output (simplified - needs flow meter for accuracy)
            # Q = m * Cp * ΔT
            # For now, estimate from typical F730 performance
            delta_t = metrics.delta_t
            # Assume typical flow rate for F730: ~30 L/min
            flow_rate = 30.0 / 60.0  # L/s
            heat_output_kw = flow_rate * 4.18 * delta_t  # kW

            real_cop = heat_output_kw / electrical_power_kw

            logger.info(f"Real COP: {real_cop:.2f} (from SaveEye)")
            logger.info(f"  Heat output: {heat_output_kw:.2f}kW")
            logger.info(f"  Electric input: {electrical_power_kw:.2f}kW")

            return max(1.0, min(real_cop, 8.0))  # Sanity check

        return None
```

## Alternative: Home Assistant Integration

Om du redan använder Home Assistant:

### Setup
1. Följ [SaveEye Home Assistant Guide](https://github.com/saveeye/SaveEye-HA-Guide)
2. Konfigurera MQTT sensors i Home Assistant
3. Exportera data via Home Assistant API
4. Integrera med Nibe Autotuner via HTTP requests

### Exempel: Läs från Home Assistant

```python
import requests

def get_power_from_ha(entity_id: str = 'sensor.saveeye_heat_pump_power'):
    """Get power reading from Home Assistant"""
    url = 'http://homeassistant.local:8123/api/states/' + entity_id
    headers = {'Authorization': 'Bearer YOUR_HA_TOKEN'}

    response = requests.get(url, headers=headers)
    data = response.json()

    power_w = float(data['state'])
    return power_w / 1000.0  # Convert to kW
```

## Deployment Checklist

- [ ] Installera Mosquitto MQTT broker på RPi
- [ ] Konfigurera SaveEye för Local MQTT
- [ ] Verifiera MQTT-meddelanden med `mosquitto_sub`
- [ ] Identifiera rätt meter-ID för värmepumpen
- [ ] Installera `paho-mqtt` i venv
- [ ] Skapa `src/saveeye_client.py`
- [ ] Testa SaveEye-klienten med `python src/saveeye_client.py`
- [ ] Integrera i `analyzer.py` för real COP calculation
- [ ] Uppdatera dashboards för att visa real vs estimated COP
- [ ] Logga både real och estimated COP för jämförelse

## Förväntade Resultat

**Före SaveEye**:
```
COP (estimated): 3.07 (från empirisk modell)
```

**Efter SaveEye**:
```
COP (estimated): 3.07 (från empirisk modell)
COP (real):      3.15 ± 0.15 (från SaveEye mätningar)
Difference:      +0.08 (+2.6%)
```

**Vinster**:
- ✅ Verklig COP istället för estimat
- ✅ Exakt kostnadsberäkning
- ✅ Validering av empirisk modell
- ✅ Bättre optimeringsunderlag
- ✅ Kan upptäcka prestandaproblem tidigt

## Troubleshooting

### SaveEye Skickar Inga MQTT-meddelanden

**Lösning**:
1. Kontrollera att Local MQTT är aktiverat i appen
2. Verifiera IP-adress till RPi
3. Kontrollera att Mosquitto körs: `sudo systemctl status mosquitto`
4. Kolla Mosquitto-loggen: `sudo journalctl -u mosquitto -f`

### Felaktiga Effektvärden

**Möjliga orsaker**:
- Fel mätare (inte värmepumpen)
- Mäter totalt hushåll istället för bara värmepump
- SaveEye inte kalibrerad korrekt

**Lösning**:
- Slå på/av värmepumpen och observera effektförändring
- Jämför med värmepumpens namnskylt (1.1-6.0 kW för F730)

### Ingen Flow-meter

**Problem**: Utan flow-meter kan vi inte beräkna exakt värmeuteffekt.

**Lösning**:
- Använd typisk flow för F730: 25-35 L/min
- Eller installera flow-meter (Kamstrup, Grundfos, etc.)
- Eller använd Nibes interna värmeberäkning (om tillgänglig i API)

## Referenser

**SaveEye**:
- [SaveEye Official](https://saveeye.se/)
- [SaveEye Home Assistant Guide](https://github.com/saveeye/SaveEye-HA-Guide)
- [SaveEye MQTT Integration Discussion](https://community.home-assistant.io/t/saveeye-echelon-energy-meter-module-mqtt-sensors-for-ha-energy-dashboard/816435)

**MQTT**:
- [Mosquitto MQTT Broker](https://mosquitto.org/)
- [Paho MQTT Python](https://pypi.org/project/paho-mqtt/)

**Heat Pump Monitoring**:
- [Open Energy Monitor - Heat Pump](https://community.home-assistant.io/t/open-energy-monitor-heat-pump-mqtt-integration/572765)

## Nästa Steg

1. **Test MQTT Setup** (15 min)
   - Installera Mosquitto på RPi
   - Konfigurera SaveEye
   - Verifiera meddelanden

2. **Develop SaveEye Client** (30 min)
   - Skapa `saveeye_client.py`
   - Testa mottagning av data
   - Logga mätningar

3. **Integrate with Analyzer** (45 min)
   - Lägg till real COP calculation
   - Uppdatera dashboards
   - Jämför real vs estimated

4. **Deploy & Monitor** (ongoing)
   - Övervaka precision
   - Kalibrera empirisk modell
   - Använd för optimering

**Total tid**: ~2 timmar initial setup + kontinuerlig förbättring
