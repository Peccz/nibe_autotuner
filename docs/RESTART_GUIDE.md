# Restart Guide - Nibe Autotuner

## Pre-Restart Status Check

### Current Running Services (2025-12-01)
```bash
# On Raspberry Pi (systemd services):
- nibe-autotuner.service (data logger, 5 min intervals)
- nibe-mobile.service (Flask PWA, port 8502)

# On this laptop (background processes):
- Streamlit GUI (port 8501) - PID 521255
- data_logger.py (300s) - PIDs 601576, 601668
```

### Files Modified in This Session
1. `src/auth.py` - Added offline_access scope
2. `src/analyzer.py` - Fixed compressor threshold (>= 20 Hz)
3. `src/mobile/templates/visualizations.html` - Removed Chart.js time-scale
4. `src/mobile_app.py` - Fixed parameter changes API
5. `src/mobile/templates/changes.html` - Disabled form with info message
6. `CHANGELOG_2025-12-01.md` - Documentation of all fixes
7. `fix_tokens.py` - Token file creator
8. `verify_system.py` - System verification script

### All Changes Committed
```
Latest commits:
- d7e175c: Update changelog with parameter changes API fix
- e8ba14a: Fix parameter changes API to use correct model fields
- 59f5c43: Remove Chart.js time scale dependency
- 0a57943: Add offline_access scope to get refresh token
```

## Pre-Restart Checklist

### 1. Stop Local Processes (this laptop)
```bash
# Kill Streamlit (if running locally)
pkill -f "streamlit run"

# Kill any local data loggers (if running)
pkill -f "data_logger.py"

# Verify all stopped
ps aux | grep -E "(python|streamlit)" | grep nibe
```

### 2. Verify Raspberry Pi Services (will survive reboot)
```bash
# SSH to Pi
ssh peccz@100.100.118.62

# Check service status
sudo systemctl status nibe-autotuner
sudo systemctl status nibe-mobile

# These services are enabled and will auto-start on boot
```

### 3. Verify Database is Intact
```bash
# On Pi or locally
ls -lh ~/nibe_autotuner/data/nibe_autotuner.db
# Should be ~100MB+, last modified recently

# Quick check
sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db "SELECT COUNT(*) FROM parameter_readings;"
```

### 4. Verify Token File
```bash
cat ~/.myuplink_tokens.json
# Should contain:
# - access_token
# - refresh_token (important!)
# - scope: "READSYSTEM WRITESYSTEM offline_access"
# - expires_at (timestamp)
```

## Restart Procedure

### Option A: Just Reboot (Recommended)
```bash
# Save all work, then:
reboot
```

### Option B: Graceful Shutdown
```bash
# Close all applications
# Then shutdown:
shutdown -h now
```

## Post-Restart Verification

### 1. Check Raspberry Pi Services
```bash
ssh peccz@100.100.118.62

# Verify services started
sudo systemctl status nibe-autotuner
sudo systemctl status nibe-mobile

# Check logs for errors
sudo journalctl -u nibe-autotuner -n 50
sudo journalctl -u nibe-mobile -n 50

# Test data logging (should see new readings every 5 min)
sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db "SELECT datetime(MAX(timestamp), 'localtime'), COUNT(*) FROM parameter_readings WHERE timestamp > datetime('now', '-1 hour');"
```

### 2. Test PWA Access
```bash
# From laptop browser:
http://100.100.118.62:8502/

# Should see:
- Dashboard with heating and hot water cards
- All 5 graphs loading
- Recent data (within last 5 minutes)
```

### 3. Run System Verification
```bash
cd ~/nibe_autotuner
python3 verify_system.py

# Expected output:
✓ TOKENS:
  Has refresh_token: True
  Scope: READSYSTEM WRITESYSTEM offline_access

✓ DATABASE:
  Total readings: 40,000+ (increasing)
  Latest reading: within last 5 minutes
  Readings last hour: ~12 (one per 5 min)

✓ API:
  Success: True
  Has heating data: True
  Has hot_water data: True
  Optimization score: XX/100
```

### 4. Test Visualizations Page
```bash
# Browser: http://100.100.118.62:8502/visualizations

# Verify:
- All 5 charts display correctly
- No console errors about date adapter
- Data points visible on graphs
```

### 5. Test Changes Page
```bash
# Browser: http://100.100.118.62:8502/changes

# Verify:
- Form is disabled (grey/faded)
- Info message visible: "Ändringsloggen är tillfälligt inaktiverad"
- No error messages in console
- Historik section shows "Inga ändringar loggade än" (if empty)
```

## Expected Service Behavior

### On Raspberry Pi (auto-start via systemd):
- `nibe-autotuner.service` - Logs data every 5 minutes to database
- `nibe-mobile.service` - Serves PWA on port 8502

### Token Auto-Renewal:
- Tokens valid for 90 days
- Auto-renewed every hour via refresh_token
- Check token expiry: `date -d @$(cat ~/.myuplink_tokens.json | jq .expires_at)`

## Troubleshooting

### If PWA doesn't load after restart:
```bash
ssh peccz@100.100.118.62
sudo systemctl restart nibe-mobile
sudo journalctl -u nibe-mobile -n 50
```

### If data logging stopped:
```bash
sudo systemctl restart nibe-autotuner
sudo journalctl -u nibe-autotuner -n 50

# Check token
python3 -c "import json; print(json.load(open('/home/peccz/.myuplink_tokens.json')))"
```

### If graphs don't load:
```bash
# Check browser console for errors
# Verify API endpoint:
curl http://100.100.118.62:8502/api/chart/outdoor?hours=24

# Should return JSON with success: true
```

## Important Notes

1. **Raspberry Pi services survive reboot** - They are systemd-managed and auto-start
2. **Token file persists** - ~/.myuplink_tokens.json survives reboot
3. **Database persists** - ~/nibe_autotuner/data/nibe_autotuner.db survives reboot
4. **Local laptop processes do NOT survive** - Streamlit, etc must be manually restarted
5. **Latest code is on GitHub** - Pi will have latest code after `git pull`

## If You Need to Update Pi After Restart

```bash
ssh peccz@100.100.118.62
cd ~/nibe_autotuner
git pull origin main
sudo systemctl restart nibe-autotuner
sudo systemctl restart nibe-mobile
```

## Contact Info / Useful Links
- PWA: http://100.100.118.62:8502
- GitHub: https://github.com/Peccz/nibe_autotuner
- MyUplink API: https://dev.myuplink.com
