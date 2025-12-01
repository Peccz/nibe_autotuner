# Post-Restart Verification Checklist

**Date:** 2025-12-01
**Project:** Nibe Autotuner
**After:** System restart/reboot

## Quick Start

After restarting your computer, follow this checklist to verify everything works:

---

## ✅ Step 1: Check Raspberry Pi Services

### 1a. SSH to Raspberry Pi
```bash
ssh peccz@100.100.118.62
```

### 1b. Check Service Status
```bash
sudo systemctl status nibe-autotuner
sudo systemctl status nibe-mobile
```

**Expected:**
- ✅ Both services show `active (running)` in green
- ✅ No error messages in recent logs

**If NOT running:**
```bash
sudo systemctl start nibe-autotuner
sudo systemctl start nibe-mobile
```

---

## ✅ Step 2: Verify Data Logging

### 2a. Check Database Updates
```bash
sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db "SELECT datetime(MAX(timestamp), 'localtime') as last_reading FROM parameter_readings;"
```

**Expected:**
- ✅ Last reading timestamp is within the last 5-10 minutes

**If NOT recent:**
```bash
sudo journalctl -u nibe-autotuner -n 50
# Look for errors related to token or API
```

### 2b. Count Recent Readings
```bash
sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db "SELECT COUNT(*) FROM parameter_readings WHERE timestamp > datetime('now', '-1 hour');"
```

**Expected:**
- ✅ Should show ~12 readings (one every 5 minutes)

---

## ✅ Step 3: Test PWA Access

### 3a. Open PWA in Browser
```
http://100.100.118.62:8502/
```

**Expected:**
- ✅ Dashboard loads
- ✅ Two cards visible: "Uppvärmning" (Heating) and "Varmvatten" (Hot Water)
- ✅ COP values displayed
- ✅ Timestamps are recent (within last 5 min)

**If blank or error:**
```bash
# On Pi:
sudo systemctl restart nibe-mobile
sudo journalctl -u nibe-mobile -n 50
```

### 3b. Check Metrics Display
Look for:
- ✅ COP värden (not "N/A")
- ✅ Temperature values (outdoor, indoor, supply, return)
- ✅ Tier badges (🏆 ELITE, ⭐ EXCELLENT, ✅ GOOD, etc)
- ✅ Optimization score (0-100)

---

## ✅ Step 4: Test Visualizations

### 4a. Open Visualizations Page
```
http://100.100.118.62:8502/visualizations
```

**Expected:**
- ✅ 5 charts displayed:
  1. Utomhustemperatur (Outdoor temp)
  2. Inomhustemperatur (Indoor temp)
  3. Tilluftstemperatur (Supply temp)
  4. Returtemperatur (Return temp)
  5. Kompressorfrekvens (Compressor freq)
- ✅ All charts show data (colored lines)
- ✅ Time labels on X-axis (HH:MM format)
- ✅ No console errors (press F12 in browser)

**If charts don't load:**
- Check browser console (F12 → Console tab)
- Look for error messages
- Try hard refresh: Ctrl+Shift+R

---

## ✅ Step 5: Verify Changes Page

### 5a. Open Changes Page
```
http://100.100.118.62:8502/changes
```

**Expected:**
- ✅ Form is disabled (greyed out)
- ✅ Blue info box visible with text: "Ändringsloggen är tillfälligt inaktiverad för uppdatering"
- ✅ No red error messages
- ✅ Historik section shows "Inga ändringar loggade än" (if empty)

**What you should NOT see:**
- ❌ Red error: "Parameter not found"
- ❌ Red error: "'parameter_type' is an invalid keyword"
- ❌ Active form that accepts input

---

## ✅ Step 6: Run System Verification Script

### 6a. Run Verification
```bash
cd ~/nibe_autotuner
python3 verify_system.py
```

**Expected Output:**
```
============================================================
NIBE AUTOTUNER - SYSTEM VERIFICATION
============================================================

✓ TOKENS:
  Has refresh_token: True
  Scope: READSYSTEM WRITESYSTEM offline_access
  Expires: 2025-XX-XX XX:XX:XX (should be in future)

✓ DATABASE:
  Total readings: 40,000+ (increasing)
  Latest reading: 2025-12-01 XX:XX:XX (recent)
  Readings last hour: ~12

✓ API:
  Success: True
  Has heating data: True
  Has hot_water data: True
  Optimization score: XX/100 (TIER_NAME)

  HEATING:
    COP: X.XX (TIER)
    Runtime: X.Xh

  HOT WATER:
    COP: X.XX (TIER)
    Runtime: X.Xh

============================================================
✓ VERIFICATION COMPLETE
============================================================
```

---

## ✅ Step 7: Verify Token Auto-Renewal

### 7a. Check Token File
```bash
cat ~/.myuplink_tokens.json | jq
```

**Expected:**
- ✅ Contains `access_token`
- ✅ Contains `refresh_token` (important!)
- ✅ `scope` includes `offline_access`
- ✅ `expires_at` is a Unix timestamp

### 7b. Check Token Expiry
```bash
python3 -c "import json; from datetime import datetime; tokens = json.load(open('/home/peccz/.myuplink_tokens.json')); print(f'Token expires: {datetime.fromtimestamp(tokens[\"expires_at\"]).strftime(\"%Y-%m-%d %H:%M:%S\")}')"
```

**Expected:**
- ✅ Expiry time is in the future (within next 1-2 hours from access_token creation)
- ✅ Token will auto-renew before expiry

---

## 🔧 Troubleshooting

### Problem: No Recent Data
**Symptoms:** Last database reading is old (>10 minutes)

**Fix:**
```bash
sudo systemctl restart nibe-autotuner
sudo journalctl -u nibe-autotuner -f
# Watch logs for 5 minutes, should see API calls
```

### Problem: PWA Shows Blank Cards
**Symptoms:** Dashboard loads but COP values show "N/A"

**Fix:**
```bash
# Check if compressor has been active
sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db "SELECT datetime(timestamp, 'localtime'), value FROM parameter_readings WHERE parameter_id = 43424 AND value >= 20 ORDER BY timestamp DESC LIMIT 10;"

# If no results, heat pump hasn't run recently (normal if warm enough)
```

### Problem: Graphs Don't Load
**Symptoms:** Visualization page shows empty chart boxes

**Fix:**
```bash
# Test API endpoint directly
curl http://localhost:8502/api/chart/outdoor?hours=24

# Should return JSON with success: true and data
# If not, restart mobile service:
sudo systemctl restart nibe-mobile
```

### Problem: Token Errors in Logs
**Symptoms:** journalctl shows "401 Unauthorized" or token errors

**Fix:**
```bash
# Check if token has refresh_token
cat ~/.myuplink_tokens.json | grep refresh_token

# If missing, need to re-authenticate:
cd ~/nibe_autotuner
python3 src/auth.py
# Follow OAuth flow in browser
```

### Problem: Changes Form Still Active
**Symptoms:** Form is not greyed out, can still click submit

**Fix:**
```bash
# Need to update code on Pi
cd ~/nibe_autotuner
git pull origin main
sudo systemctl restart nibe-mobile
```

---

## 📊 Normal Values Reference

### COP Performance Tiers:
- **Heating:**
  - 🏆 ELITE: COP ≥ 4.5
  - ⭐ EXCELLENT: COP ≥ 4.0
  - ✨ VERY GOOD: COP ≥ 3.5
  - ✅ GOOD: COP ≥ 3.0
  - 👍 OK: COP ≥ 2.5
  - ⚠️ POOR: COP < 2.5

- **Hot Water:**
  - 🏆 ELITE: COP ≥ 4.0
  - ⭐ EXCELLENT: COP ≥ 3.5
  - ✨ VERY GOOD: COP ≥ 3.0
  - ✅ GOOD: COP ≥ 2.5
  - 👍 OK: COP ≥ 2.0
  - ⚠️ POOR: COP < 2.0

### Delta T (Temperature Difference):
- ⭐ EXCELLENT: ΔT ≥ 7°C
- ✅ GOOD: ΔT ≥ 5°C
- 👍 OK: ΔT ≥ 3°C
- ⚠️ POOR: ΔT < 3°C

### Compressor:
- Active: frequency ≥ 20 Hz
- Range: 20-80 Hz
- Idle: 0 Hz

---

## ✅ Final Checklist Summary

After completing all steps above, verify:

- [ ] Both systemd services running on Pi
- [ ] Database has readings from last 5 minutes
- [ ] PWA dashboard loads and shows current data
- [ ] Both heating and hot water cards visible
- [ ] All 5 graphs display correctly
- [ ] Changes form is disabled with info message
- [ ] verify_system.py shows all green checks
- [ ] Token has refresh_token and offline_access scope

**If all checked: System is fully operational! ✅**

---

## 📝 Notes

- Data logs every 5 minutes automatically
- Token renews every hour automatically
- Services auto-start on Pi boot
- No manual intervention needed after restart
- Check dashboard occasionally to verify operation

## 🆘 Need Help?

If something doesn't work after following this checklist:

1. Check `RESTART_GUIDE.md` for detailed troubleshooting
2. Check `CHANGELOG_2025-12-01.md` for what was fixed
3. Review systemd logs: `sudo journalctl -u nibe-autotuner -n 100`
4. Review mobile service logs: `sudo journalctl -u nibe-mobile -n 100`
