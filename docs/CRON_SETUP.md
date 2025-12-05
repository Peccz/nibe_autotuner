# ⏰ Cron Job Setup Guide

## Översikt

Automatisk schemaläggning av optimering och övervakning via cron-jobb på Raspberry Pi.

## Tillgängliga Scripts

### 1. Auto-Optimizer (scripts/run_auto_optimizer.sh)
**Funktion**: Optimerar värmeinställningar baserat på senaste 72h data
**Frekvens**: Dagligen kl 03:00
**Vad den gör**:
- Analyserar COP, Delta T, innetemperatur, cykler
- Föreslår max 1 ändring per körning
- Applicerar endast ändringar med >70% confidence
- Respekterar 48h väntetid mellan ändringar

### 2. Ventilation Optimizer (scripts/run_ventilation_optimizer.sh)
**Funktion**: Justerar ventilation baserat på utomhustemperatur
**Frekvens**: Dagligen kl 06:00
**Vad den gör**:
- Väljer strategi (WARM/MILD/COLD/EXTREME)
- Justerar frånluftstemperatur och differens
- Bevarar fuktighet vid kyla
- Säkerställer luftkvalitet för 5 personer

### 3. Data Logger (data_logger.py)
**Status**: Redan igång via systemd service
**Frekvens**: Var 5:e minut
**Service**: `nibe-autotuner.service`

## Installation

### Steg 1: Kopiera Scripts Till RPi

```bash
# Från din lokala maskin
scp scripts/*.sh nibe-rpi:/home/peccz/nibe_autotuner/scripts/
```

### Steg 2: Gör Scripts Körbara

```bash
# SSH till RPi
ssh nibe-rpi

# Gör executable
chmod +x /home/peccz/nibe_autotuner/scripts/run_auto_optimizer.sh
chmod +x /home/peccz/nibe_autotuner/scripts/run_ventilation_optimizer.sh
```

### Steg 3: Konfigurera Crontab

```bash
# Öppna crontab editor
crontab -e
```

**Lägg till följande rader**:

```cron
# Nibe Autotuner - Auto Optimizer
# Kör dagligen kl 03:00 (optimalt: när elpriserna är lägst)
0 3 * * * /home/peccz/nibe_autotuner/scripts/run_auto_optimizer.sh >> /var/log/nibe-auto-optimizer.log 2>&1

# Nibe Autotuner - Ventilation Optimizer
# Kör dagligen kl 06:00 (inför morgonens aktivitet)
0 6 * * * /home/peccz/nibe_autotuner/scripts/run_ventilation_optimizer.sh >> /var/log/nibe-ventilation-optimizer.log 2>&1

# Veckovis sammanfattning (valfritt)
# Skicka email med veckostatistik varje söndag kl 20:00
#0 20 * * 0 /home/peccz/nibe_autotuner/scripts/weekly_report.sh
```

**Spara och stäng** (Ctrl+X, Y, Enter i nano)

### Steg 4: Verifiera Crontab

```bash
# Lista alla cron-jobb
crontab -l
```

**Förväntat output**:
```
0 3 * * * /home/peccz/nibe_autotuner/scripts/run_auto_optimizer.sh >> /var/log/nibe-auto-optimizer.log 2>&1
0 6 * * * /home/peccz/nibe_autotuner/scripts/run_ventilation_optimizer.sh >> /var/log/nibe-ventilation-optimizer.log 2>&1
```

### Steg 5: Skapa Loggfiler

```bash
# Skapa loggfiler med rätt permissions
sudo touch /var/log/nibe-auto-optimizer.log
sudo touch /var/log/nibe-ventilation-optimizer.log
sudo chown peccz:peccz /var/log/nibe-auto-optimizer.log
sudo chown peccz:peccz /var/log/nibe-ventilation-optimizer.log
```

## Testa Scripts Manuellt

### Test 1: Auto-Optimizer (Dry-Run)

```bash
cd /home/peccz/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python src/auto_optimizer.py --dry-run --hours 72
```

**Förväntat**:
- Analyserar senaste 72h
- Visar förslag utan att applicera
- Listar confidence och expected savings

### Test 2: Auto-Optimizer (Live)

```bash
# OBS: Detta gör faktiska ändringar!
./scripts/run_auto_optimizer.sh
```

**Kontrollera output**:
```bash
tail -f /var/log/nibe-auto-optimizer.log
```

### Test 3: Ventilation Optimizer

```bash
./scripts/run_ventilation_optimizer.sh
```

**Kontrollera output**:
```bash
tail -f /var/log/nibe-ventilation-optimizer.log
```

## Övervaka Cron-Jobb

### Realtidsövervakning

```bash
# Följ Auto-Optimizer loggen
tail -f /var/log/nibe-auto-optimizer.log

# Följ Ventilation-Optimizer loggen
tail -f /var/log/nibe-ventilation-optimizer.log

# Följ systemets cron-logg
sudo journalctl -u cron -f
```

### Historik

```bash
# Senaste 50 raderna från Auto-Optimizer
tail -50 /var/log/nibe-auto-optimizer.log

# Sök efter ändringar
grep "applied" /var/log/nibe-auto-optimizer.log

# Sök efter fel
grep -i "error\|failed" /var/log/nibe-*.log
```

### Statistik

```bash
# Hur många gånger har Auto-Optimizer gjort ändringar?
grep -c "Change applied" /var/log/nibe-auto-optimizer.log

# Senaste ändringen
grep "Change applied" /var/log/nibe-auto-optimizer.log | tail -1
```

## Schemaförklaring

### Auto-Optimizer kl 03:00
**Varför**:
- Låga elpriser (typiskt 02:00-04:00)
- Låg aktivitet i huset (alla sover)
- Tillräckligt data från föregående dag
- Ändringar hinner stabilisera sig innan morgon

**Frekvens**: Dagligen (men max 1 ändring per 48h pga säkerhetsregler)

### Ventilation kl 06:00
**Varför**:
- Inför morgonens aktivitet
- Justerar inför dagens väder
- Tid att stabilisera innan folk vaknar (07:00-08:00)

**Frekvens**: Dagligen (ändras när väder kräver)

## Avancerad Konfiguration

### Olika Frekvenser

**Auto-Optimizer varannan dag**:
```cron
# Kör bara på ojämna dagar
0 3 1-31/2 * * /home/peccz/nibe_autotuner/scripts/run_auto_optimizer.sh >> /var/log/nibe-auto-optimizer.log 2>&1
```

**Ventilation endast vardagar**:
```cron
# Mån-Fre
0 6 * * 1-5 /home/peccz/nibe_autotuner/scripts/run_ventilation_optimizer.sh >> /var/log/nibe-ventilation-optimizer.log 2>&1
```

**Extra aggressiv optimering helger**:
```cron
# Lördag & Söndag: Tillåt 2 ändringar istället för 1
0 3 * * 6,0 cd /home/peccz/nibe_autotuner && PYTHONPATH=./src ./venv/bin/python src/auto_optimizer.py --auto-apply --max-actions 2 >> /var/log/nibe-auto-optimizer.log 2>&1
```

### Logg-rotation

Förhindra att loggfiler blir för stora:

```bash
# Skapa logrotate config
sudo nano /etc/logrotate.d/nibe-autotuner
```

**Innehåll**:
```
/var/log/nibe-*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 peccz peccz
}
```

## Notifikationer (Valfritt)

### Email Vid Ändringar

```bash
# Installera mailutils
sudo apt install mailutils

# Modifiera script för att skicka email
nano scripts/run_auto_optimizer.sh
```

**Lägg till i slutet**:
```bash
# Skicka email om ändringar gjordes
if grep -q "Change applied" /tmp/auto_optimizer_last_run.log; then
    cat /tmp/auto_optimizer_last_run.log | mail -s "Nibe Auto-Optimizer: Ändring gjord" din-email@example.com
fi
```

### Pushbullet/Pushover Notifications

```python
# I auto_optimizer.py, lägg till efter ändring:
import requests

def send_notification(title, message):
    # Pushbullet
    requests.post('https://api.pushbullet.com/v2/pushes',
        headers={'Access-Token': 'YOUR_TOKEN'},
        json={'type': 'note', 'title': title, 'body': message})
```

## Felsökning

### Cron-jobbet körs inte

**Problem**: Inget händer vid schemalagd tid

**Lösningar**:
```bash
# 1. Kontrollera att cron service körs
sudo systemctl status cron

# 2. Starta om cron
sudo systemctl restart cron

# 3. Kontrollera crontab syntax
crontab -l

# 4. Kolla system-loggen
sudo journalctl -u cron -n 50

# 5. Verifiera script-sökvägar är absoluta
which python  # Använd aldrig relativa sökvägar i cron!
```

### Script körs men gör inget

**Problem**: Loggen visar att script kör men inga ändringar

**Lösningar**:
```bash
# 1. Kör manuellt och se fel
cd /home/peccz/nibe_autotuner
./scripts/run_auto_optimizer.sh

# 2. Kontrollera att venv är korrekt
./venv/bin/python --version

# 3. Kontrollera databas-permissions
ls -l data/nibe_autotuner.db

# 4. Kontrollera API-tokens
cat ~/.myuplink_tokens.json
```

### Fel i Python-koden

**Problem**: Script kraschar med Python-fel

**Lösningar**:
```bash
# 1. Läs fullständig stacktrace
cat /var/log/nibe-auto-optimizer.log

# 2. Testa imports manuellt
cd /home/peccz/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python -c "from auto_optimizer import AutoOptimizer; print('OK')"

# 3. Kontrollera beroenden
./venv/bin/pip list
```

## Avstängning

### Tillfälligt (behåll konfiguration)

```bash
# Kommentera ut i crontab
crontab -e

# Lägg till # framför raderna:
# #0 3 * * * /home/peccz/nibe_autotuner/scripts/run_auto_optimizer.sh >> /var/log/nibe-auto-optimizer.log 2>&1
```

### Permanent (ta bort helt)

```bash
# Ta bort från crontab
crontab -e

# Radera raderna helt
```

## Sammanfattning

**Setup**:
1. ✅ Kopiera scripts till RPi
2. ✅ Gör executable (`chmod +x`)
3. ✅ Konfigurera crontab
4. ✅ Skapa loggfiler
5. ✅ Testa manuellt

**Övervaka**:
```bash
# Realtid
tail -f /var/log/nibe-*.log

# Historik
grep "applied\|changed" /var/log/nibe-*.log
```

**Resultat**:
- Auto-Optimizer kör dagligen kl 03:00
- Ventilation kör dagligen kl 06:00
- Maximalt 1 heating-ändring per 48h
- Ventilation justeras vid väderförändringar
- Allt loggas för transparency

**Estimerad besparing**:
- Auto-Optimizer: 200-600 kr/år (beroende på optimeringsmöjligheter)
- Ventilation: 200-400 kr/år (vid kyla)
- **Total**: 400-1000 kr/år + ökad komfort
