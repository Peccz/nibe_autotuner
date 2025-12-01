# 🚀 Uppdatera Raspberry Pi - Nya Grafer!

## ⚡ Snabbkommando
```bash
ssh pi@<din-rpi-ip> 'cd /home/pi/nibe_autotuner && git pull && sudo systemctl restart nibe-mobile.service'
```

---

## 📋 Steg-för-steg (om du vill göra manuellt)

### 1️⃣ Logga in på din RPi
```bash
ssh pi@<din-rpi-ip>
```

### 2️⃣ Gå till projektet
```bash
cd /home/pi/nibe_autotuner
```

### 3️⃣ Hämta uppdateringen
```bash
git pull origin main
```

### 4️⃣ Starta om tjänsten
```bash
sudo systemctl restart nibe-mobile.service
sudo systemctl status nibe-mobile.service  # Kontrollera att den körs
```

### 5️⃣ Öppna i webbläsaren
```
http://<din-rpi-ip>:8502/visualizations
```

---

## ✨ Vad är nytt?

### 🎨 Helt omgjord layout!
Graferna är nu organiserade i **3 tydliga sektioner**:

#### ⚡ **Prestandaanalys** (längst upp)
De viktigaste graferna för att se hur effektivt systemet arbetar:
- **🔄 Pump, Delta T & COP** - Se alla tre tillsammans! Optimal drift = låg pump + högt Delta T + högt COP
- **⚡ COP & Utetemperatur** - Se hur COP påverkas av utetemperaturen

#### 🌡️ **Temperaturövervakning**
Allt om temperaturer:
- **🌡️ Inne- & Utetemperatur** - Jämför direkt!
- **🔥 Fram & Returtemperatur** - Se Delta T
- **💧 Varmvatten** - Håll koll på legionella-säkerhet

#### ⚙️ **Systemstatus**
Tekniska mätvärden:
- **⚙️ Kompressor** - Ska köra jämnt och mjukt
- **🌡️ Ute** - Referenstemperatur
- **🏠 Inne** - Komforttemperatur

### 💡 Pedagogiska tips!
Varje graf har nu en **liten förklaring** som hjälper dig förstå:
- Vad du ska titta efter
- Vad som är optimala värden
- Hur olika värden hänger ihop

### 🎯 Nya features:
- ✅ **COP-gräns borttagen** - Visar nu verklig prestanda (inte max 5.0)
- ✅ **"NYHET" badges** - Ser direkt vilka grafer som är nya
- ✅ **Större featured charts** - De viktiga graferna är större (300px)
- ✅ **Snyggare rubriker** - Med gradienter och ikoner
- ✅ **Bättre färgsättning** - Featured charts har blå ram

---

## 🔍 Tips för användning

### Vad ska jag titta på först?
Börja alltid med **Prestandaanalys**-sektionen:
1. Kolla **COP & Utetemperatur** - Är COP bra för nuvarande utetemperatur?
2. Studera **Pump, Delta T & COP** - Jobbar systemet optimalt?

### Vad är bra värden?
- **COP**: > 3.0 är bra, > 4.0 är utmärkt
- **Delta T**: 5-7°C är optimalt
- **Pump**: Låg hastighet (20-40%) är bra
- **Kompressor**: Jämn drift utan mycket på/av

---

## 🆘 Felsökning

### Problem: Tjänsten startar inte
```bash
# Kolla loggen
sudo journalctl -u nibe-mobile.service -n 50 --no-pager

# Testa starta manuellt
cd /home/pi/nibe_autotuner
./venv/bin/python src/mobile_app.py
```

### Problem: Grafer visas inte
1. Öppna webbläsarens console (F12)
2. Ladda om sidan (Ctrl+R)
3. Kolla efter JavaScript-fel

### Problem: Fel i Python
```bash
# Kanske behöver uppdatera beroenden?
cd /home/pi/nibe_autotuner
source venv/bin/activate
pip install -r requirements.txt
```

---

## 📊 Före/Efter

### Före:
- ❌ Alla grafer i en lång lista
- ❌ Ingen hjälp om vad man ska titta på
- ❌ Svårt att hitta viktiga grafer
- ❌ COP begränsad till max 5.0

### Efter:
- ✅ Tydliga sektioner
- ✅ Förklaringar under varje graf
- ✅ De viktigaste graferna först och större
- ✅ Verklig COP-prestanda visas

---

## 🎉 Grattis!
Din Nibe Autotuner har nu en professionell och lättanvänd dashboard!

Njut av dina nya insikter! 🔥📊⚡
