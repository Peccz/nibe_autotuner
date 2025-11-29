# Installation på Raspberry Pi - Snabbguide

## Steg 1: Uppdatera kod på Pi

Från din huvuddator, SSH:a in på Pi:

```bash
ssh peccz@raspberrypi
```

Eller om Tailscale:
```bash
ssh peccz@100.100.118.62
```

## Steg 2: Uppdatera repository

```bash
cd ~/nibe_autotuner
git pull origin main
```

## Steg 3: Installera Flask för Mobile PWA

```bash
source venv/bin/activate
pip install flask
```

## Steg 4: Kopiera tokens från huvuddatorn

**På din huvuddator**, kör:

```bash
scp ~/.myuplink_tokens.json peccz@raspberrypi.local:~/
```

Eller med Tailscale:
```bash
scp ~/.myuplink_tokens.json peccz@100.100.118.62:~/
```

## Steg 5: Installera Mobile PWA systemd-tjänst

**På Raspberry Pi:**

```bash
cd ~/nibe_autotuner
sudo cp nibe-mobile.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nibe-mobile
sudo systemctl start nibe-mobile
```

## Steg 6: Kontrollera att allt fungerar

```bash
# Kontrollera datainsamling (redan installerad)
sudo systemctl status nibe-autotuner

# Kontrollera Streamlit GUI (redan installerad)
sudo systemctl status nibe-gui

# Kontrollera nya Mobile PWA
sudo systemctl status nibe-mobile
```

Alla tre tjänster ska visa **active (running)** ✅

## Steg 7: Testa från telefonen

1. Anslut telefonen till samma WiFi som Pi:n
2. Öppna i mobil webbläsare:
   - `http://raspberrypi.local:8502`
   - Eller: `http://192.168.86.34:8502` (Pi:ns lokala IP)
   - Eller Tailscale: `http://100.100.118.62:8502`

3. Installera som app:
   - **Android:** Chrome menu → "Lägg till på startskärmen"
   - **iPhone:** Safari → Del-knapp → "Lägg till på hemskärmen"

## Tjänster på Raspberry Pi

Efter installation kör Pi:n tre tjänster:

| Tjänst | Port | Beskrivning |
|--------|------|-------------|
| `nibe-autotuner` | - | Datainsamling var 5:e minut |
| `nibe-gui` | 8501 | Streamlit (desktop) |
| `nibe-mobile` | 8502 | Mobile PWA |

## Loggar

```bash
# Datainsamling
journalctl -u nibe-autotuner -f

# Streamlit GUI
journalctl -u nibe-gui -f

# Mobile PWA
journalctl -u nibe-mobile -f
```

## Starta om tjänster

```bash
# Om något krånglar
sudo systemctl restart nibe-autotuner
sudo systemctl restart nibe-gui
sudo systemctl restart nibe-mobile
```

## Verifiera data

```bash
# Senaste readings
sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db \
  "SELECT datetime(timestamp, 'localtime'), parameter_id, value
   FROM parameter_readings
   ORDER BY timestamp DESC
   LIMIT 10"
```

## Felsökning

### Mobile PWA startar inte

```bash
# Kontrollera loggar
journalctl -u nibe-mobile -n 50

# Testa manuellt
cd ~/nibe_autotuner
source venv/bin/activate
PYTHONPATH=./src python src/mobile_app.py
```

### Kan inte nå från telefonen

1. Kontrollera att Pi:n är tillgänglig:
   ```bash
   # Från din dator
   ping raspberrypi.local
   ```

2. Kontrollera Pi:ns IP:
   ```bash
   # På Pi:n
   hostname -I
   ```

3. Testa direkt med IP istället för hostname

### Token-problem

Om du ser "No refresh token available":

```bash
cd ~/nibe_autotuner
source venv/bin/activate
python src/auth.py
# Följ instruktionerna
sudo systemctl restart nibe-autotuner
```

---

**Klart!** Nu kör allt på Raspberry Pi 24/7! 🎉
