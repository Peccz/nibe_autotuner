# Deploy-checklista — Audit Fixes (Fas 1–4)

**Datum:** 2026-03-24
**Commits:** `d7f85bb` → `53a5b9b` (5 commits)
**Mål:** Raspberry Pi (`100.100.118.62`)

---

## ⚠️ Kritisk notering INNAN deploy

> **Sökväg-diskrepans:** `deploy_v4.sh` synkar till `/home/peccz/nibe_autotuner`
> men service-filerna i repot pekar på `/home/peccz/AI/nibe_autotuner`.
> Verifiera att `REMOTE_DIR` i `deploy_v4.sh` matchar den faktiska sökvägen på RPi:n.

```bash
# Kör detta på RPi innan deploy för att bekräfta rätt sökväg
ssh peccz@100.100.118.62 "ls ~/nibe_autotuner ~/AI/nibe_autotuner 2>&1"
```

---

## Steg 1 — Förberedelse (lokalt, innan deploy)

### 1.1 Verifiera att allt är pushat
```bash
git status          # Inga ostadgade ändringar
git log --oneline -5  # 53a5b9b ska vara senaste
```

### 1.2 Bekräfta vad som ändrats
| Fil | Ändring | Risk |
|-----|---------|------|
| `src/services/gm_controller.py` | desc-import, SafetyGuard, session refresh, exception handlers | Medel |
| `src/services/smart_planner.py` | BEGIN EXCLUSIVE transaction | Låg |
| `src/data/data_logger.py` | Session refresh, specifika exception handlers | Låg |
| `src/services/safety_guard.py` | GM-parameter (40940) stöd | Låg |
| `nibe-mobile.service` | Lagt till PYTHONPATH | Låg |
| `.env.example` | Komplett variabellista | Ingen |

---

## Steg 2 — Backup på RPi (SSH)

```bash
ssh peccz@100.100.118.62

# 2.1 Backup av databas
cp ~/nibe_autotuner/data/nibe_autotuner.db \
   ~/nibe_autotuner/data/nibe_autotuner.db.backup-$(date +%Y%m%d-%H%M)
echo "✓ Backup skapad"

# 2.2 Kontrollera att backup lyckades
ls -lh ~/nibe_autotuner/data/*.backup-*

# 2.3 Notera aktuell GM-balans och service-status
sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db \
  "SELECT balance, mode, last_updated FROM gm_account;"

sudo systemctl status nibe-autotuner nibe-gm-controller nibe-mobile --no-pager

exit
```

---

## Steg 3 — Deploy (lokalt)

### 3.1 Kör deploy-skriptet
```bash
# OBS: deploy_v4.sh inkluderar git add . — se till att inget oönskat stagas
git status   # Kontrollera en sista gång

./deploy_v4.sh
```

### 3.2 Om deploy-skriptet misslyckas — manuell sync
```bash
# Synka filer manuellt (ersätt sökvägen om RPi använder ~/nibe_autotuner)
rsync -avz \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude 'data/*.db' \
  --exclude '.git' \
  ./ peccz@100.100.118.62:~/nibe_autotuner/
```

---

## Steg 4 — Service-fil för nibe-mobile (SSH på RPi)

> **OBS:** `deploy_v4.sh` kopierar INTE service-filer och startar inte om `nibe-mobile`.
> Detta steg måste köras manuellt.

```bash
ssh peccz@100.100.118.62

# 4.1 Kopiera den uppdaterade service-filen
sudo cp ~/nibe_autotuner/nibe-mobile.service /etc/systemd/system/nibe-mobile.service

# 4.2 Bekräfta att PYTHONPATH finns med
grep PYTHONPATH /etc/systemd/system/nibe-mobile.service
# Förväntat output:
# Environment="PYTHONPATH=/home/peccz/AI/nibe_autotuner/src"

# 4.3 Ladda om systemd
sudo systemctl daemon-reload
echo "✓ systemd reloaded"

exit
```

---

## Steg 5 — Starta om tjänster (SSH på RPi)

```bash
ssh peccz@100.100.118.62

# 5.1 Starta om alla tre tjänster
sudo systemctl restart nibe-autotuner nibe-gm-controller nibe-mobile

# 5.2 Vänta 10 sekunder och kontrollera status
sleep 10
sudo systemctl status nibe-autotuner nibe-gm-controller nibe-mobile --no-pager

# Alla ska visa: Active: active (running)
```

---

## Steg 6 — Verifiering (SSH på RPi)

### 6.1 Kontrollera att GM-controllern startar rätt
```bash
# Ska INTE visa "NameError: name 'desc' is not defined"
journalctl -u nibe-gm-controller -n 30 --no-pager
```

**Förväntat i loggarna:**
```
GM Controller V10.1 (HW Awareness) started.
✓ GM Write Verified: -210 (Reason: ...)
```

**Röda flaggor (rulla tillbaka om dessa syns):**
```
NameError / ImportError / ModuleNotFoundError
SafetyGuard rejected with no safe alternative
```

### 6.2 Kontrollera att mobile-appen startar
```bash
journalctl -u nibe-mobile -n 20 --no-pager
# Ska INTE visa ImportError

# Testa att dashboarden svarar
curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/
# Förväntat: 200
```

### 6.3 Kontrollera att data-loggern kör
```bash
journalctl -u nibe-autotuner -n 20 --no-pager
# Ska visa "✓ Logged X new readings from MyUplink"
```

### 6.4 Verifiera GM-balansen i databasen
```bash
sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db \
  "SELECT balance, mode, last_updated FROM gm_account;"
# Balansen ska vara rimlig (-2000 till 200)
# last_updated ska vara inom senaste 2 minuterna
```

### 6.5 Verifiera att planering fungerar
```bash
sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db \
  "SELECT timestamp, planned_action, planned_offset, electricity_price
   FROM planned_heating_schedule
   WHERE timestamp > datetime('now')
   ORDER BY timestamp LIMIT 6;"
# Ska visa framtida rader, inte vara tom
```

---

## Steg 7 — Övervaka (30–60 min efter deploy)

```bash
# Kör i separate terminaler

# Terminal 1: GM Controller (viktigast)
journalctl -u nibe-gm-controller -f

# Terminal 2: Data Logger
journalctl -u nibe-autotuner -f

# Vad man letar efter i GM-loggarna:
# ✓ GM Write Verified: XXX       → skrivning fungerar
# ⏸️ Bank Paused: Hot Water       → normal paus
# ⚠️ GM Write returned empty     → API-svarade men tomt (ovanligt)
# ✗ GM Write failed              → API-fel (återförsök sker automatiskt)
# SafetyGuard BLOCKED            → skyddsmekanism aktiverad
```

---

## Rollback — Om något går fel

```bash
ssh peccz@100.100.118.62

# Alternativ A: Återgå till föregående git-version
cd ~/nibe_autotuner
git log --oneline -6   # Hitta commit innan audit-fixes (68ad579)
git checkout 68ad579 -- src/services/gm_controller.py
git checkout 68ad579 -- src/data/data_logger.py
git checkout 68ad579 -- src/services/smart_planner.py
sudo systemctl restart nibe-gm-controller nibe-autotuner

# Alternativ B: Återställ databasen (om DB-relaterat problem)
cp ~/nibe_autotuner/data/nibe_autotuner.db.backup-YYYYMMDD-HHMM \
   ~/nibe_autotuner/data/nibe_autotuner.db
sudo systemctl restart nibe-gm-controller nibe-autotuner

# Alternativ C: Återställ service-filen (om mobile-appen kraschar)
sudo cp ~/nibe_autotuner/nibe-mobile.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart nibe-mobile
```

---

## Snabb referens — Vanliga kommandon på RPi

```bash
# Visa status för alla tjänster
sudo systemctl status nibe-autotuner nibe-gm-controller nibe-mobile

# Visa logg i realtid
journalctl -u nibe-gm-controller -f
journalctl -u nibe-autotuner -f
journalctl -u nibe-mobile -f

# Starta om en tjänst
sudo systemctl restart nibe-gm-controller

# Kolla GM-balansen
sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db "SELECT * FROM gm_account;"

# Kolla senaste parametervärden
sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db \
  "SELECT p.parameter_id, r.value, r.timestamp
   FROM parameter_readings r JOIN parameters p ON r.parameter_id = p.id
   WHERE p.parameter_id IN ('40008','40033','40941','HA_TEMP_DOWNSTAIRS')
   AND r.timestamp > datetime('now','-10 minutes')
   ORDER BY r.timestamp DESC LIMIT 10;"
```
