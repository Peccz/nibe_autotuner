# Raspberry Pi Installation - Ett-kommando

## Snabbinstallation (Rekommenderat)

Kör detta kommando på din Raspberry Pi för att installera allt automatiskt:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Peccz/nibe_autotuner/main/setup_raspberry_pi.sh)
```

**VÄNTA!** Innan du kör kommandot ovan, läs nedanför för komplett installation.

---

## Komplett Installation (Steg-för-steg)

### Steg 1: Klona Repository

```bash
cd ~
git clone https://github.com/Peccz/nibe_autotuner.git
cd nibe_autotuner
```

### Steg 2: Kopiera Konfiguration från Din Dator

**Från din huvuddator**, kör:

```bash
# Ersätt 'pi@raspberrypi.local' med din Pi's adress
scp /home/peccz/AI/nibe_autotuner/.env pi@raspberrypi.local:~/nibe_autotuner/
scp ~/.myuplink_tokens.json pi@raspberrypi.local:~/
```

### Steg 3: Kör Setup-script

**På Raspberry Pi**, kör:

```bash
cd ~/nibe_autotuner
./setup_raspberry_pi.sh
```

Scriptet kommer automatiskt:
- ✅ Installera alla dependencies
- ✅ Skapa Python virtual environment
- ✅ Verifiera konfiguration
- ✅ Testa datainsamling
- ✅ Installera systemd-tjänst
- ✅ Aktivera autostart vid boot

---

## Alternativ: Manuell Installation

Om du föredrar att installera manuellt:

```bash
# 1. Klona repo
cd ~
git clone https://github.com/Peccz/nibe_autotuner.git
cd nibe_autotuner

# 2. Installera system-dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv sqlite3 git curl

# 3. Skapa Python virtual environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Kopiera .env från din dator (kör från din dator)
# scp /home/peccz/AI/nibe_autotuner/.env pi@raspberrypi.local:~/nibe_autotuner/

# 5. Kopiera tokens från din dator (kör från din dator)
# scp ~/.myuplink_tokens.json pi@raspberrypi.local:~/

# 6. Testa datainsamling
python src/data_logger.py --interval 300
# Tryck Ctrl+C efter ett par minuter

# 7. Installera systemd-tjänst
./install_service.sh

# 8. Starta tjänsten
sudo systemctl start nibe-autotuner
sudo systemctl status nibe-autotuner
```

---

## Efter Installation

### Verifiera att det Fungerar

```bash
# Kontrollera status
sudo systemctl status nibe-autotuner

# Se live-loggar
journalctl -u nibe-autotuner -f

# Kontrollera databas
sqlite3 data/nibe_autotuner.db "SELECT COUNT(*) FROM parameter_readings;"
```

### Åtkomst till GUI från Din Dator

**På Raspberry Pi**, kör:

```bash
cd ~/nibe_autotuner
source venv/bin/activate
streamlit run src/gui.py --server.address 0.0.0.0
```

**På din dator**, öppna:
```
http://raspberrypi.local:8501
```

### Automatisk GUI-start (Valfritt)

För att köra GUI:t automatiskt:

```bash
cat > ~/nibe_autotuner/nibe-gui.service << 'EOF'
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

sudo cp ~/nibe_autotuner/nibe-gui.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nibe-gui
sudo systemctl start nibe-gui
```

Nu är GUI:t tillgängligt på: `http://raspberrypi.local:8501`

---

## Felsökning

### Tjänsten startar inte

```bash
# Kontrollera loggar
journalctl -u nibe-autotuner -n 50

# Testa manuellt
cd ~/nibe_autotuner
source venv/bin/activate
python src/data_logger.py --interval 300
```

### Tokens saknas

```bash
# Om du inte kopierade tokens, autentisera på Pi:
cd ~/nibe_autotuner
source venv/bin/activate
python src/auth.py
```

### .env fil saknas

Kopiera från din dator:
```bash
scp /home/peccz/AI/nibe_autotuner/.env pi@raspberrypi.local:~/nibe_autotuner/
```

---

## Underhåll

### Uppdatera till Senaste Version

```bash
cd ~/nibe_autotuner
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart nibe-autotuner
```

### Backup Databas

```bash
# Manuell backup
cp ~/nibe_autotuner/data/nibe_autotuner.db ~/nibe_autotuner_backup_$(date +%Y%m%d).db

# Automatisk backup (daglig)
cat > ~/backup_nibe.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/pi/nibe_backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
cp ~/nibe_autotuner/data/nibe_autotuner.db "$BACKUP_DIR/nibe_$DATE.db"
# Behåll endast 7 senaste
cd "$BACKUP_DIR" && ls -t nibe_*.db | tail -n +8 | xargs -r rm
EOF

chmod +x ~/backup_nibe.sh
(crontab -l 2>/dev/null; echo "0 3 * * * /home/pi/backup_nibe.sh") | crontab -
```

---

## Avinstallera

Om du vill ta bort systemet:

```bash
cd ~/nibe_autotuner
sudo systemctl stop nibe-autotuner
sudo systemctl disable nibe-autotuner
sudo rm /etc/systemd/system/nibe-autotuner.service
sudo systemctl daemon-reload
rm -rf ~/nibe_autotuner
```

---

## Support

- **GitHub**: https://github.com/Peccz/nibe_autotuner
- **Dokumentation**: Se README.md och docs/
- **Loggar**: `journalctl -u nibe-autotuner -f`

