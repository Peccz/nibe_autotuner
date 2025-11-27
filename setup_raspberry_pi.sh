#!/bin/bash
# Raspberry Pi Setup Script för Nibe Autotuner
# Kör detta script på din Raspberry Pi

set -e

echo "════════════════════════════════════════════════════════════════"
echo "  Nibe Autotuner - Raspberry Pi Installation"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Färgkoder för output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funktioner
print_step() {
    echo -e "${GREEN}▶${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Kontrollera att vi är på Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo && ! grep -q "BCM" /proc/cpuinfo; then
    print_warning "Detta verkar inte vara en Raspberry Pi"
    read -p "Vill du fortsätta ändå? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Kontrollera att vi INTE kör som root
if [ "$EUID" -eq 0 ]; then
    print_error "Kör INTE detta script som root (med sudo)"
    print_warning "Scriptet kommer fråga efter sudo-lösenord när det behövs."
    exit 1
fi

# Hämta nuvarande användarnamn och hem-katalog
CURRENT_USER=$(whoami)
HOME_DIR=$HOME
INSTALL_DIR="$HOME_DIR/nibe_autotuner"

echo "Installation kommer använda:"
echo "  Användare: $CURRENT_USER"
echo "  Hem-katalog: $HOME_DIR"
echo "  Installation: $INSTALL_DIR"
echo ""
read -p "Fortsätt? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Steg 1: Uppdatera system
print_step "Steg 1: Uppdaterar systemet..."
sudo apt update
sudo apt upgrade -y
print_success "System uppdaterat"

# Steg 2: Installera dependencies
print_step "Steg 2: Installerar nödvändiga paket..."
sudo apt install -y python3-pip python3-venv sqlite3 git curl
print_success "Paket installerade"

# Steg 3: Kontrollera om projektet redan finns
if [ -d "$INSTALL_DIR" ]; then
    print_warning "Katalogen $INSTALL_DIR finns redan"
    read -p "Vill du använda befintliga filer? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_error "Avbryter installation"
        exit 1
    fi
else
    print_error "Projektet finns inte i $INSTALL_DIR"
    echo ""
    echo "Överför projektet från din dator med:"
    echo "  scp -r /path/to/nibe_autotuner $CURRENT_USER@$(hostname):~/"
    echo ""
    echo "Eller klona från Git:"
    echo "  cd ~ && git clone <repo-url> nibe_autotuner"
    exit 1
fi

cd "$INSTALL_DIR"

# Steg 4: Skapa Python virtual environment
print_step "Steg 4: Skapar Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_success "Virtual environment skapat"
else
    print_warning "Virtual environment finns redan"
fi

# Steg 5: Installera Python dependencies
print_step "Steg 5: Installerar Python-paket (detta kan ta några minuter)..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
print_success "Python-paket installerade"

# Steg 6: Kontrollera .env fil
print_step "Steg 6: Kontrollerar konfiguration..."
if [ ! -f ".env" ]; then
    print_warning ".env fil saknas!"
    echo ""
    echo "Överför .env från din dator:"
    echo "  scp /path/to/.env $CURRENT_USER@$(hostname):~/nibe_autotuner/"
    echo ""
    read -p "Tryck Enter när .env är på plats..."
fi

if [ -f ".env" ]; then
    print_success ".env fil hittad"
else
    print_error ".env fil saknas fortfarande"
    exit 1
fi

# Steg 7: Kontrollera myUplink tokens
print_step "Steg 7: Kontrollerar myUplink autentisering..."
if [ ! -f "$HOME_DIR/.myuplink_tokens.json" ]; then
    print_warning "myUplink tokens saknas!"
    echo ""
    echo "Du har två alternativ:"
    echo "  1. Kopiera från din dator:"
    echo "     scp ~/.myuplink_tokens.json $CURRENT_USER@$(hostname):~/"
    echo ""
    echo "  2. Autentisera här (kräver webbläsare):"
    echo "     python src/auth.py"
    echo ""
    read -p "Vill du autentisera nu? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python src/auth.py
    else
        print_warning "Kom ihåg att autentisera innan du startar tjänsten!"
    fi
fi

if [ -f "$HOME_DIR/.myuplink_tokens.json" ]; then
    print_success "Autentisering konfigurerad"
fi

# Steg 8: Skapa loggar-katalog
print_step "Steg 8: Skapar loggar-katalog..."
mkdir -p logs
print_success "Loggar-katalog skapad"

# Steg 9: Skapa korrekt systemd service-fil
print_step "Steg 9: Skapar systemd service-fil..."
cat > nibe-autotuner.service << EOF
[Unit]
Description=Nibe Autotuner Data Logger
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$INSTALL_DIR/venv/bin/python src/data_logger.py --interval 300

# Restart policy
Restart=always
RestartSec=30

# Logging
StandardOutput=append:$INSTALL_DIR/logs/data_logger.log
StandardError=append:$INSTALL_DIR/logs/data_logger_error.log

[Install]
WantedBy=multi-user.target
EOF
print_success "Service-fil skapad"

# Steg 10: Testa datainsamling
print_step "Steg 10: Testar datainsamling..."
echo ""
echo "Startar data logger i testläge (10 sekunder)..."
timeout 10 python src/data_logger.py --interval 300 || true
echo ""
print_success "Test slutfört"

# Steg 11: Installera systemd service
print_step "Steg 11: Installerar systemd-tjänst..."
sudo cp nibe-autotuner.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nibe-autotuner.service
print_success "Tjänst installerad och aktiverad för autostart"

# Steg 12: Fråga om start
echo ""
echo "════════════════════════════════════════════════════════════════"
print_success "Installation klar!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Tjänsten är installerad och kommer starta automatiskt vid boot."
echo ""
read -p "Vill du starta datainsamlingen nu? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl start nibe-autotuner
    sleep 3
    echo ""
    print_step "Status:"
    sudo systemctl status nibe-autotuner --no-pager
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Användbara kommandon"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Hantera tjänsten:"
echo "  sudo systemctl start nibe-autotuner    # Starta"
echo "  sudo systemctl stop nibe-autotuner     # Stoppa"
echo "  sudo systemctl restart nibe-autotuner  # Starta om"
echo "  sudo systemctl status nibe-autotuner   # Status"
echo ""
echo "Loggar:"
echo "  journalctl -u nibe-autotuner -f        # Live-loggar"
echo "  tail -f logs/data_logger.log           # Fil-loggar"
echo ""
echo "Databas:"
echo "  sqlite3 data/nibe_autotuner.db"
echo ""
echo "GUI (från din dator):"
echo "  http://$(hostname).local:8501"
echo "  (kräver: streamlit run src/gui.py --server.address 0.0.0.0)"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""
print_success "Allt klart! Din Raspberry Pi samlar nu data från värmepumpen."
echo ""
