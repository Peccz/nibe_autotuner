# Database Design - Nibe Autotuner

## Overview

The database stores time-series data from the heat pump for analysis and optimization.

## Schema Design

### Core Tables

#### 1. `systems`
Stores information about heat pump systems.

```sql
CREATE TABLE systems (
    id INTEGER PRIMARY KEY,
    system_id VARCHAR(50) UNIQUE NOT NULL,  -- From myUplink API
    name VARCHAR(100),
    country VARCHAR(50),
    security_level VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 2. `devices`
Stores information about devices (heat pumps, etc.)

```sql
CREATE TABLE devices (
    id INTEGER PRIMARY KEY,
    device_id VARCHAR(100) UNIQUE NOT NULL,  -- From myUplink API
    system_id INTEGER REFERENCES systems(id),
    product_name VARCHAR(100),
    serial_number VARCHAR(50),
    firmware_version VARCHAR(20),
    connection_state VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 3. `parameters`
Catalog of all available parameters (meta-data)

```sql
CREATE TABLE parameters (
    id INTEGER PRIMARY KEY,
    parameter_id VARCHAR(10) UNIQUE NOT NULL,  -- e.g., "40004", "47007"
    parameter_name VARCHAR(200),
    parameter_unit VARCHAR(20),
    category VARCHAR(100),
    writable BOOLEAN DEFAULT FALSE,
    min_value REAL,
    max_value REAL,
    step_value REAL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 4. `parameter_readings` (Time-series data)
**Most important table** - stores all sensor readings over time

```sql
CREATE TABLE parameter_readings (
    id INTEGER PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id),
    parameter_id INTEGER REFERENCES parameters(id),
    timestamp TIMESTAMP NOT NULL,
    value REAL NOT NULL,
    str_value VARCHAR(50),

    -- Indexes for fast time-series queries
    INDEX idx_device_timestamp (device_id, timestamp),
    INDEX idx_param_timestamp (parameter_id, timestamp),
    INDEX idx_device_param_timestamp (device_id, parameter_id, timestamp)
);
```

#### 5. `parameter_changes`
Tracks manual parameter changes made by user

```sql
CREATE TABLE parameter_changes (
    id INTEGER PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id),
    parameter_id INTEGER REFERENCES parameters(id),
    timestamp TIMESTAMP NOT NULL,
    old_value REAL,
    new_value REAL,
    reason TEXT,  -- Why the change was made
    applied_by VARCHAR(50),  -- 'user', 'system', 'recommendation'
    recommendation_id INTEGER,  -- Link to recommendation if applicable
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 6. `recommendations`
AI-generated optimization recommendations

```sql
CREATE TABLE recommendations (
    id INTEGER PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id),
    parameter_id INTEGER REFERENCES parameters(id),
    created_at TIMESTAMP NOT NULL,
    recommended_value REAL,
    current_value REAL,
    expected_impact TEXT,  -- JSON with expected changes
    priority VARCHAR(20),  -- 'high', 'medium', 'low'
    status VARCHAR(20),  -- 'pending', 'applied', 'rejected', 'expired'
    applied_at TIMESTAMP,
    expired_at TIMESTAMP
);
```

#### 7. `recommendation_results`
Track effectiveness of applied recommendations

```sql
CREATE TABLE recommendation_results (
    id INTEGER PRIMARY KEY,
    recommendation_id INTEGER REFERENCES recommendations(id),
    measured_at TIMESTAMP NOT NULL,
    metric_name VARCHAR(50),  -- e.g., 'energy_consumption', 'comfort_level'
    before_value REAL,
    after_value REAL,
    change_percent REAL,
    success BOOLEAN
);
```

## Key Design Decisions

### 1. Time-Series Optimization

- **Partitioning**: Could partition `parameter_readings` by month for large datasets
- **Retention**: Consider archiving old data after 1-2 years
- **Indexes**: Composite indexes on (device, parameter, timestamp) for fast queries

### 2. Data Collection Strategy

- **Frequency**: Every 5-10 minutes initially
- **Selective logging**: May log critical parameters more frequently
- **Delta compression**: Only store changes for slowly changing parameters

### 3. Analysis Queries

Common queries the system will need:

```sql
-- Get temperature trend over last 24 hours
SELECT timestamp, value
FROM parameter_readings pr
JOIN parameters p ON pr.parameter_id = p.id
WHERE p.parameter_id = '40004'  -- Outdoor temp
  AND timestamp > datetime('now', '-24 hours')
ORDER BY timestamp;

-- Calculate average compressor frequency by hour
SELECT
    strftime('%Y-%m-%d %H:00', timestamp) as hour,
    AVG(value) as avg_frequency
FROM parameter_readings pr
JOIN parameters p ON pr.parameter_id = p.id
WHERE p.parameter_id = '41778'  -- Compressor frequency
  AND timestamp > datetime('now', '-7 days')
GROUP BY hour;

-- Find correlation between outdoor temp and energy usage
SELECT
    outdoor.value as outdoor_temp,
    energy.value as energy_usage
FROM parameter_readings outdoor
JOIN parameter_readings energy
    ON outdoor.device_id = energy.device_id
    AND outdoor.timestamp = energy.timestamp
WHERE outdoor.parameter_id = (SELECT id FROM parameters WHERE parameter_id = '40004')
  AND energy.parameter_id = (SELECT id FROM parameters WHERE parameter_id = '43084');
```

## Storage Estimates

### Data Volume Calculations

Assuming:
- 102 parameters per reading
- 1 reading every 5 minutes
- 8 bytes per value + metadata = ~50 bytes per parameter reading

**Daily**: 102 params × 12 readings/hour × 24 hours = 29,376 rows = ~1.5 MB/day
**Monthly**: ~45 MB
**Yearly**: ~540 MB

**Conclusion**: SQLite is perfectly adequate for several years of data.

## Migration Strategy

Using Alembic for schema migrations:

```bash
# Initialize
alembic init alembic

# Create migration
alembic revision --autogenerate -m "Initial schema"

# Apply migration
alembic upgrade head
```

## Future Enhancements

1. **Aggregation tables**: Pre-compute hourly/daily averages
2. **Real-time views**: Materialized views for dashboard
3. **ML features table**: Store computed features for ML models
4. **Weather data integration**: External weather API data
5. **Energy pricing**: Spot price data for cost optimization
