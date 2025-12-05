# Raspberry Pi Setup Guide - Nibe Autotuner

## Översikt

Denna guide hjälper dig att sätta upp Raspberry Pi för att kontinuerligt samla in data från din Nibe F730 värmepump via myUplink API.

## Fördelar med Raspberry Pi

- ✅ Alltid på och ansluten till nätverket
- ✅ Låg strömförbrukning (~3-5W)
- ✅ Automatisk datainsamling var 5:e minut
- ✅ Ingen manuell export av CSV-filer
- ✅ Kan köra GUI och API-server för fjärråtkomst

## Krav

- Raspberry Pi (3B+, 4, eller 5 rekommenderas)
- Raspbian/Raspberry Pi OS installerat
- Nätverksanslutning (WiFi eller Ethernet)
- Minst 8GB SD-kort (16GB+ rekommenderas)

---

## Steg-för-steg Installation

### 1. Förbered Raspberry Pi

Logga in på din Pi (SSH eller direkt):

```bash
# Uppdatera systemet
sudo apt update && sudo apt upgrade -y

# Installera nödvändiga paket
sudo apt install -y python3-pip python3-venv git sqlite3
```

### 2. Överför projektet till Pi

**Alternativ A: Kopiera från din dator (rekommenderat)**

Från din huvuddator:
```bash
# Ersätt 'pi@raspberrypi.local' med din Pi's adress
scp -r /home/peccz/AI/nibe_autotuner pi@raspberrypi.local:~/

# Kopiera .env fil
scp /home/peccz/AI/nibe_autotuner/.env pi@raspberrypi.local:~/nibe_autotuner/
```

**Alternativ B: Klona från Git**

Om du har projektet i ett Git-repo:
```bash
cd ~
git clone <din-repo-url> nibe_autotuner
cd nibe_autotuner
```

### 3. Installera Python-miljön

På Raspberry Pi:

```bash
cd ~/nibe_autotuner

# Skapa virtual environment
python3 -m venv venv

# Aktivera
source venv/bin/activate

# Installera dependencies
pip install -r requirements.txt
```

Detta kan ta 5-10 minuter på en Raspberry Pi.

### 4. Autentisering med myUplink

Du har två alternativ:

**Alternativ A: Autentisera från huvuddatorn, kopiera tokens**

Från din huvuddator (där du redan har autentiserat):
```bash
# Kopiera token-filen
scp ~/.myuplink_tokens.json pi@raspberrypi.local:~/
```

**Alternativ B: Autentisera direkt från Pi**

Om Pi har skärm och webbläsare:
```bash
cd ~/nibe_autotuner
source venv/bin/activate
python src/auth.py
```

Detta öppnar en webbläsare för inloggning på myUplink.

**Alternativ C: SSH X11 forwarding (för headless Pi)**

Från din dator:
```bash
# Anslut med X11 forwarding
ssh -X pi@raspberrypi.local

# Kör autentisering (webbläsaren öppnas på din dator)
cd ~/nibe_autotuner
source venv/bin/activate
python src/auth.py
```

### 5. Testa datainsamling

Innan vi installerar som tjänst, testa att det fungerar:

```bash
cd ~/nibe_autotuner
source venv/bin/activate
python src/data_logger.py --interval 300
```

Du bör se:
```
INFO: Starting data collection (interval: 300 seconds)
INFO: Fetched X parameters from myUplink API
INFO: Saved X new readings to database
```

Tryck `Ctrl+C` för att stoppa efter ett par minuter.

### 6. Installera som systemd-tjänst

Först måste vi uppdatera service-filen för Pi:

```bash
cd ~/nibe_autotuner

# Skapa korrekt service-fil för Pi
cat > nibe-autotuner.service << 'EOF'
[Unit]
Description=Nibe Autotuner Data Logger
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/nibe_autotuner
Environment="PATH=/home/pi/nibe_autotuner/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/pi/nibe_autotuner/venv/bin/python src/data_logger.py --interval 300

# Restart policy
Restart=always
RestartSec=30

# Logging
StandardOutput=append:/home/pi/nibe_autotuner/logs/data_logger.log
StandardError=append:/home/pi/nibe_autotuner/logs/data_logger_error.log

[Install]
WantedBy=multi-user.target
EOF

# Gör install-scriptet körbart
chmod +x install_service.sh

# Kör installationen
./install_service.sh
```

Svara 'y' när den frågar om du vill starta tjänsten.

### 7. Verifiera att det fungerar

```bash
# Kontrollera status
sudo systemctl status nibe-autotuner

# Se live-loggar
journalctl -u nibe-autotuner -f

# Kontrollera databas
sqlite3 data/nibe_autotuner.db "SELECT COUNT(*) FROM parameter_readings;"
```

Du bör se nya avläsningar var 5:e minut.

---

## Fjärråtkomst till Data

### Alternativ 1: Streamlit GUI (Rekommenderat)

Kör GUI:et på Pi och kom åt det från din dator:

```bash
# På Pi
cd ~/nibe_autotuner
source venv/bin/activate
streamlit run src/gui.py --server.port 8501 --server.address 0.0.0.0
```

Öppna sedan i din webbläsare:
```
http://raspberrypi.local:8501
```

**Automatisk start av GUI:**

Skapa en separat service för GUI:et:

```bash
cat > nibe-gui.service << 'EOF'
[Unit]
Description=Nibe Autotuner GUI
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/nibe_autotuner
Environment="PATH=/home/pi/nibe_autotuner/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/pi/nibe_autotuner/venv/bin/streamlit run src/gui.py --server.port 8501 --server.address 0.0.0.0 --server.headless true

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo cp nibe-gui.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nibe-gui
sudo systemctl start nibe-gui
```

### Alternativ 2: REST API Server

Om du vill komma åt data programmatiskt:

```bash
cd ~/nibe_autotuner
source venv/bin/activate
python src/api_server.py
```

API:et blir tillgängligt på:
```
http://raspberrypi.local:8000
```

Se API-dokumentation på:
```
http://raspberrypi.local:8000/docs
```

### Alternativ 3: Synka databas till huvuddator

Använd `rsync` för att regelbundet kopiera databasen:

```bash
# På din huvuddator, kör detta med cron var timme
rsync -avz pi@raspberrypi.local:~/nibe_autotuner/data/nibe_autotuner.db /home/peccz/AI/nibe_autotuner/data/
```

Lägg till i crontab (`crontab -e`):
```
0 * * * * rsync -avz pi@raspberrypi.local:~/nibe_autotuner/data/nibe_autotuner.db /home/peccz/AI/nibe_autotuner/data/
```

---

## Underhåll och Övervakning

### Kontrollera status dagligen

```bash
# Status för tjänsten
sudo systemctl status nibe-autotuner

# Senaste loggarna
journalctl -u nibe-autotuner -n 50

# Databasstatistik
cd ~/nibe_autotuner
source venv/bin/activate
python -c "
import sys
sys.path.insert(0, 'src')
from models import init_db, ParameterReading
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func

engine = init_db('sqlite:///./data/nibe_autotuner.db')
Session = sessionmaker(bind=engine)
session = Session()

count = session.query(func.count(ParameterReading.id)).scalar()
latest = session.query(func.max(ParameterReading.timestamp)).scalar()

print(f'Total readings: {count:,}')
print(f'Latest reading: {latest}')
session.close()
"
```

### Vanliga problem

**Problem: Token expired**

```bash
# Förnya autentiseringen
cd ~/nibe_autotuner
source venv/bin/activate
python src/auth.py

# Starta om tjänsten
sudo systemctl restart nibe-autotuner
```

**Problem: Tjänsten startar inte**

```bash
# Kontrollera loggar
journalctl -u nibe-autotuner -n 100

# Verifiera virtual environment
ls -la /home/pi/nibe_autotuner/venv/bin/python

# Testa manuellt
cd ~/nibe_autotuner
source venv/bin/activate
python src/data_logger.py --interval 300
```

**Problem: Disk fullt**

```bash
# Kontrollera diskutrymme
df -h

# Databasstorlek
du -h ~/nibe_autotuner/data/nibe_autotuner.db

# Loggar kan bli stora
du -h ~/nibe_autotuner/logs/

# Rensa gamla loggar (var försiktig!)
sudo journalctl --vacuum-time=7d
```

### Automatisk backup

Lägg till daglig backup:

```bash
# Skapa backup-script
cat > ~/backup_nibe.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/pi/nibe_backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# Backup databas
cp ~/nibe_autotuner/data/nibe_autotuner.db "$BACKUP_DIR/nibe_autotuner_$DATE.db"

# Behåll bara de senaste 7 backuperna
cd "$BACKUP_DIR"
ls -t nibe_autotuner_*.db | tail -n +8 | xargs -r rm

echo "Backup complete: nibe_autotuner_$DATE.db"
EOF

chmod +x ~/backup_nibe.sh

# Lägg till i crontab (varje dag kl 03:00)
(crontab -l 2>/dev/null; echo "0 3 * * * /home/pi/backup_nibe.sh") | crontab -
```

---

## Prestanda och Resurser

### Typisk resursanvändning på Raspberry Pi 4:

- **CPU**: <5% (mestadels idle)
- **RAM**: ~150MB för data logger, ~300MB för GUI
- **Disk**: ~100MB databas per månad (beroende på antal parametrar)
- **Nätverk**: ~1KB var 5:e minut (minimal)

### Optimering för äldre Pi (3B+ eller äldre):

```bash
# Minska insamlingsfrekvens till 10 minuter
# Redigera service-filen:
sudo nano /etc/systemd/system/nibe-autotuner.service

# Ändra:
ExecStart=/home/pi/nibe_autotuner/venv/bin/python src/data_logger.py --interval 600

# Ladda om
sudo systemctl daemon-reload
sudo systemctl restart nibe-autotuner
```

---

## Säkerhet

### Brandväggsregler (om du exponerar GUI/API)

```bash
# Installera UFW
sudo apt install ufw

# Tillåt SSH
sudo ufw allow ssh

# Tillåt Streamlit GUI (endast från lokalt nätverk)
sudo ufw allow from 192.168.0.0/16 to any port 8501

# Aktivera brandvägg
sudo ufw enable
```

### VPN-åtkomst (för säker fjärråtkomst)

Om du vill komma åt Pi utifrån, använd WireGuard eller Tailscale istället för att exponera portar direkt.

**Tailscale (enklast):**

```bash
# Installera Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Anslut
sudo tailscale up

# Nu kan du komma åt Pi från valfri enhet i ditt Tailscale-nätverk
```

---

## Troubleshooting Checklista

- [ ] Python 3.8+ installerat: `python3 --version`
- [ ] Virtual environment aktiverat: `which python` visar venv-path
- [ ] Dependencies installerade: `pip list | grep myuplink`
- [ ] `.env` fil finns: `cat ~/nibe_autotuner/.env`
- [ ] Tokens finns: `ls -la ~/.myuplink_tokens.json`
- [ ] Nätverksanslutning: `ping api.myuplink.com`
- [ ] Tjänsten körs: `systemctl is-active nibe-autotuner`
- [ ] Inga fel i loggar: `journalctl -u nibe-autotuner -n 50`
- [ ] Databas växer: `watch -n 60 'sqlite3 ~/nibe_autotuner/data/nibe_autotuner.db "SELECT COUNT(*) FROM parameter_readings;"'`

---

## Summering

När allt är uppsatt har du:

✅ **Automatisk datainsamling** var 5:e minut
✅ **Startar vid boot** - ingen manuell intervention
✅ **Automatisk återstart** vid fel
✅ **Loggning** för felsökning
✅ **Fjärråtkomst** via GUI eller API
✅ **Backup** (om konfigurerad)

Din Raspberry Pi samlar nu kontinuerligt in data från värmepumpen och du kan analysera prestanda, optimera inställningar och spåra effektivitet över tid!

---

**Frågor eller problem?**

Kontrollera först loggarna:
```bash
journalctl -u nibe-autotuner -f
```

Kör sedan testet manuellt:
```bash
cd ~/nibe_autotuner
source venv/bin/activate
python src/data_logger.py --interval 300
```
