# 🚀 Deploy Instructions - Nya Optimeringsverktyg

## ✅ Vad har implementerats

### 1. **Separata Metriker för Uppvärmning vs Varmvatten**
- Individuella COP-värden för varje läge
- Separata Delta T-analyser
- Runtime och cykelräkning per läge
- Varmvattentemperatur (BT7) spårad

### 2. **Performance Tier-System**
🏆 **ELITE** - Absolut bästa (COP ≥4.5 uppvärmning, ≥4.0 varmvatten)
⭐ **EXCELLENT** - Utmärkt (COP ≥4.0 uppvärmning, ≥3.5 varmvatten)
✨ **VERY GOOD** - Mycket bra
✅ **GOOD** - Bra
👍 **OK** - Godkänt
⚠️ **POOR** - Under godkänt

### 3. **Optimeringspoäng 0-100**
Kombinerar:
- Heating COP (30 pts)
- Hot Water COP (20 pts)
- Delta T optimization (25 pts)
- Degree Minutes (15 pts)
- Runtime Efficiency (10 pts)

### 4. **Kostnadsanalys i SEK**
- Faktisk elkostnad per läge
- Energy consumption (kWh)
- Heat output (kWh)
- Procentuell fördelning

### 5. **COP vs Utomhustemp Analys**
- Scatter plot för att identifiera underprestation
- Jämför mot teoretisk Carnot-kurva
- Separata färger för uppvärmning/varmvatten

---

## 📋 Deployment till Raspberry Pi

### Steg 1: Push till GitHub (KLART ✅)
```bash
git push origin main
```

### Steg 2: SSH till Raspberry Pi
```bash
# Via Tailscale
ssh peccz@100.100.118.62

# ELLER via lokal nätverks
ssh peccz@raspberrypi.local
# ELLER
ssh peccz@192.168.86.34
```

### Steg 3: Uppdatera kod på Pi
```bash
cd ~/nibe_autotuner
git pull origin main
```

### Steg 4: Starta om Mobile PWA-tjänsten
```bash
sudo systemctl restart nibe-mobile
```

### Steg 5: Verifiera att tjänsten kör
```bash
sudo systemctl status nibe-mobile
```

Du ska se **active (running)** ✅

### Steg 6: Testa från din telefon
Öppna: `http://100.100.118.62:8502` (Tailscale)
ELLER: `http://192.168.86.34:8502` (Lokal WiFi)

---

## 🎯 Vad ska du se?

### Dashboard:
1. **Optimeringspoäng-banner** överst med stor cirkel och tier-badge
2. **Kostnadsanalys-sektion** med 3 kort (Uppvärmning, Varmvatten, Total)
3. **Uppvärmning vs Varmvatten jämförelse** med:
   - COP-värden med färgglada badges (🏆⭐✨✅)
   - Delta T-värden med badges
   - Runtime och cykler

### Exempel från testdata (2025-11-28):
```
Uppvärmning:
- COP: 5.00 🏆 ELITE (guld)
- Delta T: 9.5°C ⭐ EXCELLENT (cyan)
- Runtime: 0.3h
- Cykler: 2

Varmvatten:
- COP: 3.96 ⭐ EXCELLENT (cyan)
- Delta T: 9.5°C ⭐ EXCELLENT (cyan)
- VV Temp: 50.4°C
- Runtime: 1.7h
- Cykler: 1

Optimeringspoäng: ~85-90 ⭐ EXCELLENT
```

---

## 🐛 Felsökning

### Tjänsten startar inte
```bash
# Kolla loggar
sudo journalctl -u nibe-mobile -n 50

# Testa manuellt
cd ~/nibe_autotuner
source venv/bin/activate
PYTHONPATH=./src python src/mobile_app.py
```

### Ser inga nya badges
1. Kontrollera att du har data från senaste tiden
2. Verifiera att dataloggern kör: `sudo systemctl status nibe-autotuner`
3. Kolla databasen:
   ```bash
   sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db "SELECT COUNT(*), MAX(timestamp) FROM parameter_readings"
   ```

### Kan inte nå från telefon
1. Kontrollera att Pi:n är online: `ping 100.100.118.62`
2. Kontrollera tjänstestatus: `sudo systemctl status nibe-mobile`
3. Testa från Pi själv: `curl http://localhost:8502/api/metrics`

---

## 📊 Nya API Endpoints

### `/api/metrics`
Nu inkluderar:
- `heating`: Separata metrics för uppvärmning
- `hot_water`: Separata metrics för varmvatten
- `cost_analysis`: Kostnadsuppdelning i SEK
- `optimization_score`: Övergripande poäng 0-100

### `/api/cop_analysis` (NYL!)
Returnerar COP vs outdoor temp scatter plot data:
- `heating`: Array av (temp, cop) punkter
- `hot_water`: Array av (temp, cop) punkter
- `carnot_curve`: Teoretisk prestanda

---

## 🎮 Gamification: Sträva mot 100 poäng!

För att nå **🏆 ELITE (90+)**:
1. COP Uppvärmning ≥ 4.5
2. COP Varmvatten ≥ 4.0
3. Delta T mellan 5-7°C (💎 PERFECT)
4. Degree Minutes mellan -300 och -100
5. Långa cykler (≥60 min/cykel)

**Tips:**
- Optimera värmekurvan för lägre framledningstemperatur
- Minska varmvattentemperatur till 45-50°C
- Undvik korta cykler

---

## 📈 Nästa Steg (Framtida förbättringar)

1. **COP vs Temp Graf** - Scatter plot i Mobile PWA
2. **Timeline med ändringsmarkeringar** - Se effekt av justeringar
3. **7-dagars rullande genomsnitt** - Identifiera trender
4. **Före/Efter-jämförelse** - När du ändrar inställningar
5. **Export till CSV** - För egen analys

---

**Klart!** 🎉

Du har nu ett kraftfullt optimeringsverktyg som hjälper dig följa och förbättra din värmepumps prestanda över tid!
