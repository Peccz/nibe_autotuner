# Nibe F730 Parameter Reference (Premium Manage)

Comprehensive list of all 102 parameters identified on the device.
**Source:** `deep_scan_v3.py` (2025-12-04)

## 🛠️ Writable Parameters (Control)
These parameters can be adjusted by the AI Agent via the myUplink API.

### 🔥 Heating & Climate
| ID | Name | Unit | Current | Range | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **47011** | **Offset** | - | -3.0 | -10..10 | Main heat adjustment (Curve Offset). |
| **47007** | **Heating curve** | - | 7.0 | 1..15 | Slope of the heating curve. |
| **47015** | **Room temp** (Climate System 1) | °C | 20.0 | 5..30 | Target room temp (if sensor active). |
| **47394** | Control room sensor | - | 0 | 0..4 | Factor for room sensor influence. |
| **47375** | Stop heating | °C | 13.0 | 0..30 | Outdoor temp to stop heating entirely. |
| **47020** | Flow line temp @ 30°C | °C | 15.0 | - | Custom curve point. |
| **47021** | Flow line temp @ 20°C | °C | 15.0 | - | Custom curve point. |
| **47022** | Flow line temp @ 10°C | °C | 26.0 | - | Custom curve point. |
| **47023** | Flow line temp @ 0°C | °C | 32.0 | - | Custom curve point. |
| **47024** | Flow line temp @ -10°C | °C | 35.0 | - | Custom curve point. |
| **47025** | Flow line temp @ -20°C | °C | 40.0 | - | Custom curve point. |
| **47026** | Flow line temp @ -30°C | °C | 45.0 | - | Custom curve point. |
| **47028** | Change in curve | °C | 0.0 | - | Curve break point adjustment. |

### 🛁 Hot Water
| ID | Name | Unit | Current | Range | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **47041** | **Hot water demand** | - | 1 | 0..3 | 0=Small, 1=Medium, 2=Large, 3=Smart. |
| **48132** | **Hot water boost** | - | 0 | 0/1 | Activate "Temporary Lux" (One-time). |
| **50004** | Temporary lux | - | 0 | - | Time-based HW boost. |
| **47050** | Periodic increase | - | 1 | 0/1 | Legionella protection cycle. |
| **47051** | Period | days | 14 | - | Days between periodic increases. |

### 💨 Ventilation
| ID | Name | Unit | Current | Range | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **50005** | **Increased ventilation** | - | 0 | 0..4 | Force higher fan speed. |
| **47538** | Start temp. exhaust air | °C | 24.0 | - | Threshold for compressor ramp-up? |
| **47539** | Min diff outdoor-exhaust | °C | 7.0 | - | Efficiency limit. |
| **47537** | Night cooling | - | 0 | 0/1 | Passive cooling at night. |

### ⚙️ Compressor & Operation
| ID | Name | Unit | Current | Range | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **47206** | **Start compressor** | DM | -200 | - | Degree Minutes to start (Neg value). |
| **47137** | Op. mode | - | 0 | 0..2 | 0=Auto, 1=Manual, 2=Add. only. |
| **47212** | Set max electrical add | - | 650 | - | Max power for heater (6.5 kW?). |
| **48072** | Start diff add. heat | DM | 1500 | - | DM threshold for electric heater. |
| **47209** | Diff between add. steps | DM | 100 | - | Step delay for heater. |
| **47376** | Stop additional heat | °C | 1.0 | - | Outdoor temp to block heater. |

### 💰 Smart Price Adaption (Built-in)
*These settings control Nibe's own SPA logic. AI Agent might conflict if these are active.*
| ID | Name | Value | Description |
| :--- | :--- | :--- | :--- |
| 41929 | Mode | 2 | SPA Enabled? |
| 44896 | Heating offset | -4.5 | Current SPA adjustment. |
| 44908 | Status | 30 | Status code. |

---

## 📊 Readable Values (Sensors)
Key metrics for analysis.

| ID | Name | Value | Unit | Description |
| :--- | :--- | :--- | :--- | :--- |
| **40004** | **Outdoor temp** | 4.1 | °C | Main control input. |
| **40033** | **Room temp** | 22.1 | °C | Indoor comfort level. |
| **40940** | **Degree minutes** | -140 | DM | Heating deficit (Main logic). |
| **40013** | **Hot water top** | 52.0 | °C | BT7 Sensor. |
| **40014** | Hot water charging | 47.0 | °C | BT6 Sensor (Compressor stop). |
| **41778** | Compressor freq | 45 | Hz | Current load. |
| **40008** | Supply line | 24.7 | °C | Water to radiators. |
| **40012** | Return line | 24.4 | °C | Water from radiators. |
| **40025** | Exhaust air | 22.3 | °C | Air entering pump. |
| **40026** | Extract air | 20.7 | °C | Air leaving house (waste). |
| **43437** | Pump speed (GP1) | 30 | % | Circulation pump. |
| **50345** | Hot water amount | 24 | min | Estimated equivalent hot water? |

*Note: Values are snapshots from 2025-12-04.*
