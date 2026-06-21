# LOCAL_CONTROL_RESEARCH.md
# Nibe F730 och Zaptec — lokala styrningsalternativ till molnberoende API:er

*Utredning (ej hårdvaruändring). Syfte: kartlägga realistiska alternativ till myUplink och Zaptec-moln om API:erna är instabila eller otillgängliga.*

---

## 1. Bakgrund och motivation

Under 2026-06-11 fick GM 40940-skrivningar ~10 read-timeouts under några minuter. Systemet klarade det (pump höll sista setpoint), men händelsen motiverar en utredning av lokala alternativ utan moln-round-trip.

---

## 2. Nibe F730 — lokal Modbus-styrning

### 2.1 Nibe MODBUS 40 (tillbehör)

Nibe tillverkar ett officiellt Modbus-tillbehör, **NIBE MODBUS 40** (artikelnummer 067 076), som monteras i pumpen och exponerar ett Modbus RTU-gränssnitt via RS-485. Det ger läs- och skriv-åtkomst till i princip alla pump-parametrar inklusive GM (40940) och framledningskurva (47007/47011), utan internet-beroende.

**Protokoll:** Modbus RTU (RS-485). Standard Modbus-slav på adress 1 (konfigurerbar). Baudrate 9600 eller 19200.

**Viktigaste register (Nibe Modbus 40 dokumentation):**

| Register | Innehåll | Typ |
|----------|----------|-----|
| 40004 | BT1 utomhustemp (×10, °C) | R |
| 40008 | BT2 tilloppstemperatur | R |
| 40033 | BT50 rumstemperatur | R |
| 40940 | Degree Minutes (skriv) | R/W |
| 40941 | Degree Minutes (läs) | R |
| 47007 | Värmekurva | R/W |
| 47011 | Kurva offset | R/W |

**Fördelar:**
- Noll moln-latens; lokalt RS-485-anrop tar < 100 ms.
- Inga timeout-problem orsakade av internet.
- Fungerar vid nätverksstörning.

**Nackdelar:**
- Kräver fysisk installation av MODBUS 40-kortet (kräver Nibe-certifierad installatör om garantin ska bevaras).
- RS-485 till Raspberry Pi kräver USB-to-RS485-adapter (t.ex. ch340-baserad, ~100 kr).
- Modbus RTU är halvduplex; polling ≥ 1 Hz kräver omsorg.
- Ingen officiell integration med myUplink kvar — antingen/eller ur praktisk synvinkel (går att köra parallellt men risk för race condition på 40940).

**Python-bibliotek:** `pymodbus` (stabil, aktivt underhållen). Exempelkod:
```python
from pymodbus.client import ModbusSerialClient
client = ModbusSerialClient(port='/dev/ttyUSB0', baudrate=9600)
result = client.read_holding_registers(40940, count=1, slave=1)
gm = result.registers[0]
```

### 2.2 Modbus TCP via IP-brygga

Alternativt kan RS-485-signalen bryggad via en **Elfin EW11A** eller **Waveshare RS485 TO ETH** (Ethernet-till-RS485-brygga, ~300–500 kr). Modbus-klienten kopplar då TCP till bryggans IP och talar Modbus TCP; inget USB-krävs på RPi:n.

```python
from pymodbus.client import ModbusTcpClient
client = ModbusTcpClient(host='192.168.1.x', port=502)
```

### 2.3 Befintlig community-integration: `nibe-heatpump` (Home Assistant)

Home Assistant-komponenten [`nibe-heatpump`](https://github.com/elupus/hibe_heatpump) av elupus stöder Nibe F-serien via Modbus. Det är vältestat och täcker F730. Kan fungera som referens eller direkt integration om HA redan finns i systemet (HA kör Docker på `127.0.0.1:5580`).

### 2.4 Rekommendation för detta projekt

1. **Kortsiktig fix (redan gjord):** Retry-logik i GM-skrivningar (Task #17 Del A).
2. **Medellång åtgärd:** Köp och installera Nibe MODBUS 40. Kostnaden är ~2 000–3 000 kr inkl. tillbehör. Koppla RS-485 via USB-adapter till RPi. Implementera en Modbus-klient som fallback om myUplink times out tre gånger i rad. GM-skrivning sker då direkt.
3. **Alternativ utan korts-installation:** Utvärdera om HA-komponentens Modbus-integration kan hantera GM-skrivningar parallellt (innebär risk för race conditions på 40940 — kräver explicit locking).

---

## 3. Zaptec — lokala alternativ

### 3.1 Nuläge

Ioniq5-projektet kommunicerar med Zaptec Go via Zaptec Cloud REST API. Pause/Resume och current-limit-kommandon skickas via `https://api.zaptec.com`. Om Zaptec-molnet är nere kan laddstyrningen inte pausa eller justera ström.

### 3.2 Zaptec Service Bus (near-real-time)

Zaptec erbjuder en **Service Bus**-kanal (Azure Service Bus) för partners/integratörer som vill ha near-real-time telemetri utan polling. Ger push-notiser vid laddstatus-ändringar. Kräver partner-avtal med Zaptec. Minskar polling-behovet men är fortfarande moln-beroende.

**Status:** Dokumenterat i Zaptec API-spec. Kräver partnerkonto. Inte tillgängligt i Free tier.

### 3.3 Zaptec Go lokal kommunikation

Zaptec Go kommunicerar med en **lokal LAN-endpoint** (intern REST/OCPP). Officiell dokumentation är begränsad, men community-reverse-engineering (se [hacs-zapcharge](https://github.com/custom-components/HA-zapcharge)) visar att:

- Zaptec Go exponerar ett **lokalt REST-API** på port 80 inom hemnätverket.
- Autentisering sker med samma användarnamn/lösenord som molnet, men token-exchange sker lokalt.
- Stödjer GET-status och Pause/Resume utan moln-round-trip.

**Risk:** Lokala API:et är inte officiellt dokumenterat; kan förändras i firmware-uppdateringar.

**Kända endpoints (community, ej garanterade):**

| Endpoint | Beskrivning |
|----------|-------------|
| `GET /api/sessions/ongoing` | Aktuell laddningssession |
| `POST /api/chargers/{id}/sendCommand/5` | Pause |
| `POST /api/chargers/{id}/sendCommand/6` | Resume |

### 3.4 OCPP-alternativ

Zaptec Go är OCPP 1.6-kompatibel. Teorietiskt kan Zaptec konfigureras att peka mot en lokal OCPP-backend (t.ex. [Steve](https://github.com/steve-community/steve)), men detta kräver firmware-konfiguration som Zaptec normalt inte exponerar för slutkunder.

### 3.5 Rekommendation för detta projekt

1. **Kortsiktig:** Befintlig retry-logik i Zaptec-kommandon (finns redan i `cli/zaptec_command.py`).
2. **Medellång:** Undersök lokal Zaptec-endpoint (icke-destruktiv read-only probe: `GET http://<zaptec-ip>/api/sessions/ongoing`) för att avgöra om lokal kommunikation är möjlig på den installerade firmware-versionen.
3. **Långsiktig:** Om Zaptec Go byter moln-backend eller priset på Zaptec-molnet förändras — utvärdera OCPP-alternativ (kräver router-konfiguration, ingen Zaptec-kodändring).

**Viktigt:** Inga ändringar mot Zaptec-hårdvaran utan peccz-godkännande. Allt ovan är research/rekommendation.

---

## 4. Sammanfattning och prioritetsordning

| Prioritet | Åtgärd | Risk | Kostnad | Moln-oberoende |
|-----------|--------|------|---------|----------------|
| 1 (gjort) | Retry/backoff GM-skrivningar (Task #17 Del A) | Låg | 0 | Nej (myUplink kvar) |
| 2 | Installera Nibe MODBUS 40 + RS-485 | Medel (installation) | ~2–3 000 kr | Ja (Nibe) |
| 3 | Lokal Zaptec-endpoint (read-only probe först) | Låg–Medel | 0 | Delvis |
| 4 | OCPP local backend | Hög (firmware) | Tid | Ja (Zaptec) |

*Inga hårdvaruändringar är utförda. Detta är enbart research och rekommendation för peccz att agera på.*

---

## 5. Källor

- Nibe MODBUS 40 installationshandbok (IHB 1636-3 SE, finns på nibeuplink.com)
- Nibe F730 parameterregister (dokumenteras i DNA.md §6)
- pymodbus dokumentation: https://pymodbus.readthedocs.io/
- elupus/hibe_heatpump (HA community): https://github.com/elupus/hibe_heatpump
- Zaptec API-spec (Swagger): https://api.zaptec.com/api-spec
- community/HA-zapcharge (lokal Zaptec): https://github.com/custom-components/HA-zapcharge
- Zaptec Service Bus dokumentation (partner-portal)

*Utredning genomförd 2026-06-21 av Claude Sonnet 4.6 (Task #17 Del C).*
