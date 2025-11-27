# Fix Authentication Issue

## Problem
Data logger cannot authenticate with myUplink API:
```
ERROR: No refresh token available
```

## Solution

### Step 1: Kill the current data logger process

```bash
# Find the process
ps aux | grep data_logger

# Kill it (replace PID with actual number from output)
kill 57052
```

Or simply:
```bash
pkill -f data_logger
```

### Step 2: Run authentication

```bash
cd /home/peccz/AI/nibe_autotuner
source venv/bin/activate
python src/auth.py
```

This will:
1. Open your browser
2. Ask you to login to myUplink
3. Redirect back and save new tokens
4. Tokens saved to: `~/.myuplink_tokens.json`

### Step 3: Verify authentication worked

```bash
ls -la ~/.myuplink_tokens.json
```

You should see the file with recent timestamp.

### Step 4: Start data logger again

**Option A: Run manually (for testing)**
```bash
python src/data_logger.py --interval 300
```

**Option B: Install as systemd service (recommended)**
```bash
./install_service.sh
```

Then check status:
```bash
sudo systemctl status nibe-autotuner
sudo journalctl -u nibe-autotuner -f
```

### Step 5: Verify data is being collected

Wait 5-10 minutes, then check:
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from models import init_db, ParameterReading
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func
from datetime import datetime

engine = init_db('sqlite:///./data/nibe_autotuner.db')
SessionMaker = sessionmaker(bind=engine)
session = SessionMaker()

latest = session.query(func.max(ParameterReading.timestamp)).scalar()
now = datetime.utcnow()
age = now - latest

print(f'Latest reading: {latest}')
print(f'Current time:   {now}')
print(f'Data age:       {age}')

if age.total_seconds() < 600:
    print('✅ Data is FRESH - collection working!')
else:
    print('⚠️  Data is OLD - check logs')

session.close()
"
```

## Quick Fix (All-in-one)

```bash
cd /home/peccz/AI/nibe_autotuner
pkill -f data_logger
source venv/bin/activate
python src/auth.py
# Follow browser prompts, then:
./install_service.sh
```

## Troubleshooting

### If authentication fails:
1. Check your .env file has correct credentials
2. Verify myUplink application is still active at dev.myuplink.com
3. Check internet connection

### If data still not updating:
```bash
# Check service status
sudo systemctl status nibe-autotuner

# View live logs
sudo journalctl -u nibe-autotuner -f

# Restart service
sudo systemctl restart nibe-autotuner
```

## Common Issues

### "No module named 'myuplink'"
```bash
pip install -r requirements.txt
```

### "Permission denied" on install_service.sh
```bash
chmod +x install_service.sh
```

### Service won't start
Check logs:
```bash
sudo journalctl -u nibe-autotuner -n 50
```
