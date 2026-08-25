# 💧 LeakX — Smart Water Infrastructure Monitoring

LeakX is a multi-zone smart water infrastructure monitoring system designed to detect abnormal pipeline conditions, identify the affected zone, estimate water loss, alert maintenance teams, and support rapid valve isolation.

## 🚨 Problem

Water pipeline leaks can remain unnoticed until a significant amount of water has already been wasted or infrastructure has been damaged. In a multi-zone water network, manually checking every section is slow and difficult.

LeakX addresses this by continuously monitoring flow and pressure values for multiple zones and detecting abnormal conditions automatically.

## 💡 Origin Story

The idea for LeakX came from thinking about real-world water problems, including how floods and infrastructure damage can disrupt access to water and place additional pressure on already vulnerable water systems.

This led to a simple question:

> **What if we could continuously monitor water infrastructure and detect a problem before it becomes a bigger loss?**

That idea became LeakX.

## 🎯 Solution

LeakX monitors three zones:

- **Zone A — Main Line**
- **Zone B — North District**
- **Zone C — South District**

Each zone can have flow and pressure readings. The system stores the readings and determines the current status of each zone.

When abnormal readings indicate a leak, LeakX detects the condition, identifies the affected zone, estimates water loss, displays an alert, and allows the affected valve to be closed remotely.

## ⚙️ How It Works

```text
Flow Sensor ───────┐
                   ├──> ESP32 / IoT Layer ──> LeakX Backend
Pressure Sensor ───┘                              │
                                                 ▼
                                         Detection Engine
                                                 │
                              ┌──────────────────┴─────────────────┐
                              ▼                                    ▼
                         Normal State                         Leak Detected
                                                                   │
                                                                   ▼
                                                            Alert Dashboard
                                                                   │
                                                                   ▼
                                                            Valve Isolation
```

The current version uses simulated sensor data. The architecture is designed to move toward ESP32-based physical sensors.

## 🧠 Current Detection Logic

- Expected flow: **7.0 L/min**
- Normal flow: approximately **6.5–8.5 L/min**
- Simulated leak flow: approximately **12.5–14.5 L/min**
- Leak pressure: approximately **26–29 PSI**
- Normal pressure: approximately **38–42 PSI**
- Dashboard leak threshold: **12 L/min**

Current classification:

- **LEAK → CRITICAL / HIGH**
- Flow above expected level without leak status → **WARNING / MEDIUM**
- Normal readings → **NORMAL / LOW**

These are prototype thresholds and should be calibrated with real hardware before deployment.

## 📊 Dashboard Features

- Live flow rate
- Pipeline pressure
- Pipeline status
- Estimated water loss
- Total alerts
- Live flow telemetry chart
- Flow gauge
- Multi-zone health view
- Alert history
- Zone selection
- Remote valve open/close control
- Siren alert
- Downloadable CSV reports

## 🗄️ Database

LeakX uses **SQLite** to store sensor readings for the three zones.

Stored information includes:

- Timestamp
- Flow
- Pressure
- Status

The current schema uses separate flow, pressure and status columns for each zone.

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Main application |
| FastAPI | REST API/backend |
| Uvicorn | Application server |
| SQLite | Sensor data storage |
| HTML/CSS | Dashboard |
| JavaScript | Live dashboard updates |
| ESP32 | Planned IoT controller |
| Flow sensors | Planned flow measurement |
| Pressure sensors | Planned pressure measurement |
| Solenoid valves | Planned zone isolation |

## 📁 Project Structure

```text
LeakX/
├── main.py
├── database.py
├── check_db.py
├── requirements.txt
├── README.md
├── README_RUN.txt
├── .gitignore
└── leakx.db              # local database; do not commit
```

## ▶️ Run Locally

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/LeakX-Smart-Water-Monitoring.git
cd LeakX-Smart-Water-Monitoring
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start LeakX

```bash
python -m uvicorn main:app --reload
```

### 4. Open the dashboard

```text
http://127.0.0.1:8000
```

### 5. Check the database

```bash
python check_db.py
```

## 🔌 Hardware Roadmap

Recommended physical prototype:

```text
Water Tank
    ↓
12V Pump
    ↓
Flow Sensor
    ↓
Pressure Sensor
    ↓
Solenoid Valve
    ↓
Pipeline
    ↓
Water Tank
```

The ESP32 reads the sensors and sends the readings to the LeakX backend.

Recommended components:

- ESP32 DevKit V1
- YF-S201 or suitable water flow sensors
- 0–1.2 MPa pressure sensors
- 12V solenoid valves
- Relay modules
- 12V power supply
- 5V buck converter
- Mini water pump
- PVC pipes and connectors
- Breadboard/prototype PCB
- Jumper wires
- Buzzer/siren
- LEDs and resistors
- Waterproof enclosure

## 🚀 Future Scope

- Replace simulated readings with real ESP32 sensor data.
- Calibrate thresholds using real pipeline measurements.
- Add advanced anomaly detection or machine learning.
- Add SMS/email/mobile notifications.
- Add map-based leak localization.
- Add configurable automatic valve isolation.
- Track historical water loss and recurring failures.

## 🏆 Hackathon Value

LeakX combines:

**Detection + Localization + Estimation + Alert + Response**

Instead of only reporting that a leak exists, the system aims to answer:

- **Where is the problem?**
- **How serious is it?**
- **How much water may be getting lost?**
- **What action can be taken immediately?**

## ⚠️ Prototype Disclaimer

LeakX is a prototype. Sensor thresholds, water-loss calculations, electrical design, valve selection and communication architecture should be validated and safety-tested before real municipal or industrial deployment.

## 👥 Project

**Project:** LeakX  
**Category:** Smart Water Infrastructure / IoT  
**Backend:** FastAPI + Python  
**Database:** SQLite  
**Current Mode:** Sensor Simulation  
**Planned Hardware:** ESP32 + Flow/Pressure Sensors + Solenoid Valves

---

### Made for smarter water infrastructure 💧
