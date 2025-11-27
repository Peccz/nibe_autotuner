# Nibe Autotuner - Usage Guide

## Getting Started

### 1. Data Collection

The data logger continuously collects data from your heat pump and stores it in the database.

#### Single Reading (Test)
```bash
source venv/bin/activate
python src/data_logger.py --once
```

#### Continuous Logging (Every 5 minutes)
```bash
python src/data_logger.py --interval 300
```

#### Continuous Logging (Every 1 minute - for testing)
```bash
python src/data_logger.py --interval 60
```

#### Run in Background (Linux/Mac)
```bash
nohup python src/data_logger.py --interval 300 > logs/data_logger.log 2>&1 &
```

#### Stop Background Process
```bash
# Find process ID
ps aux | grep data_logger

# Kill process
kill <PID>
```

### 2. Database Management

#### Check Database Stats
```python
from src.data_logger import DataLogger

logger = DataLogger()
stats = logger.get_stats()
print(stats)
```

#### Query Recent Data
```python
from src.models import get_session, init_db, ParameterReading, Parameter
from datetime import datetime, timedelta

engine = init_db()
session = get_session(engine)

# Get outdoor temperature for last 24 hours
outdoor_temp_param = session.query(Parameter).filter_by(
    parameter_id='40004'
).first()

recent_readings = session.query(ParameterReading).filter(
    ParameterReading.parameter_id == outdoor_temp_param.id,
    ParameterReading.timestamp > datetime.now() - timedelta(hours=24)
).order_by(ParameterReading.timestamp).all()

for reading in recent_readings:
    print(f"{reading.timestamp}: {reading.value}°C")
```

## Data Analysis Examples

### Temperature Trends

```python
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine('sqlite:///./data/nibe_autotuner.db')

# Load data
query = """
SELECT
    pr.timestamp,
    p.parameter_name,
    pr.value,
    p.parameter_unit
FROM parameter_readings pr
JOIN parameters p ON pr.parameter_id = p.id
WHERE p.parameter_id IN ('40004', '40008', '40012', '40033')
  AND pr.timestamp > datetime('now', '-24 hours')
ORDER BY pr.timestamp
"""

df = pd.read_sql_query(query, engine)

# Pivot for easier plotting
df_pivot = df.pivot(
    index='timestamp',
    columns='parameter_name',
    values='value'
)

# Plot
import matplotlib.pyplot as plt
df_pivot.plot(figsize=(12, 6))
plt.title('Temperature Trends - Last 24 Hours')
plt.ylabel('Temperature (°C)')
plt.legend(loc='best')
plt.grid(True)
plt.savefig('temp_trends.png')
```

### Energy Consumption Analysis

```python
# Calculate daily energy patterns
query = """
SELECT
    strftime('%H', pr.timestamp) as hour,
    AVG(pr.value) as avg_compressor_freq,
    AVG(CASE WHEN p2.parameter_id = '43084' THEN pr2.value END) as avg_add_heat
FROM parameter_readings pr
JOIN parameters p ON pr.parameter_id = p.id
LEFT JOIN parameter_readings pr2 ON pr2.device_id = pr.device_id AND pr2.timestamp = pr.timestamp
LEFT JOIN parameters p2 ON pr2.parameter_id = p2.id
WHERE p.parameter_id = '41778'  -- Compressor frequency
  AND pr.timestamp > datetime('now', '-7 days')
GROUP BY hour
ORDER BY hour
"""

df_energy = pd.read_sql_query(query, engine)
print(df_energy)
```

## Maintenance

### Backup Database

```bash
# Backup
cp data/nibe_autotuner.db data/backups/nibe_autotuner_$(date +%Y%m%d).db

# Restore
cp data/backups/nibe_autotuner_20251124.db data/nibe_autotuner.db
```

### Database Size Management

```python
# Check database size
import os
db_size = os.path.getsize('data/nibe_autotuner.db')
print(f"Database size: {db_size / 1024 / 1024:.2f} MB")

# Archive old data (keep last 6 months)
from datetime import datetime, timedelta

cutoff_date = datetime.now() - timedelta(days=180)

session.query(ParameterReading).filter(
    ParameterReading.timestamp < cutoff_date
).delete()

session.commit()

# Vacuum to reclaim space
session.execute("VACUUM")
```

## Next Steps

1. **Data Visualization Dashboard** - Create web dashboard to view trends
2. **Analysis Engine** - Implement optimization algorithms
3. **Recommendation System** - Generate parameter tuning suggestions
4. **Android App** - Build mobile interface

## Troubleshooting

### Token Expired
If you get authentication errors:
```bash
python src/auth.py  # Re-authenticate
```

### Database Locked
If multiple processes access the database:
- Use only one data logger instance
- Consider PostgreSQL for concurrent access

### Memory Usage
For long-running processes, monitor memory:
```bash
ps aux | grep data_logger
```

If memory grows:
- Reduce collection frequency
- Archive old data more frequently
- Restart logger periodically
