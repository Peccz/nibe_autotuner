# Uppdatera Raspberry Pi med nya grafer

## Snabbkommando (SSH från din dator)
```bash
ssh pi@<din-rpi-ip> 'cd /home/pi/nibe_autotuner && git pull && sudo systemctl restart nibe-mobile.service && sudo systemctl status nibe-mobile.service --no-pager'
```

## Eller manuellt steg-för-steg:

### 1. SSH till Raspberry Pi
```bash
ssh pi@<din-rpi-ip>
```

### 2. Gå till projektkatalogen
```bash
cd /home/pi/nibe_autotuner
```

### 3. Hämta nya ändringar från GitHub
```bash
git pull origin main
```

### 4. Starta om mobile app-tjänsten
```bash
sudo systemctl restart nibe-mobile.service
```

### 5. Kontrollera att tjänsten körs
```bash
sudo systemctl status nibe-mobile.service
```

### 6. Öppna webbläsaren
Gå till: `http://<din-rpi-ip>:8502/visualizations`

## Vad är nytt?

### Nya grafer i Visualizations:
1. **🔄 Pump, Delta T & COP** - Visar cirkulationspump, temperaturskillnad och COP samtidigt
2. **🌡️ Inne- & Utetemperatur** - Jämför inomhus och utomhustemperatur
3. **⚡ COP & Utetemperatur** - Se sambandet mellan utetemperatur och värmepumpens prestanda

### Förbättringar:
- ✅ COP-begränsningen på 5.0 är borttagen
- ✅ Konsekventa skalor på alla Y-axlar
- ✅ Tydliga etiketter på varje axel
- ✅ COP beräknas nu i 15-minuters intervall

## Felsökning

Om mobile app inte startar:
```bash
# Kontrollera loggar
sudo journalctl -u nibe-mobile.service -n 50

# Testa starta manuellt
cd /home/pi/nibe_autotuner
./venv/bin/python src/mobile_app.py
```

Om det saknas Python-beroenden:
```bash
source venv/bin/activate
pip install -r requirements.txt
```
