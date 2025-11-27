# Token-hantering och Automatisk Förnyelse

## Sammanfattning

✅ **Ja, tjänsten kommer fungera långsiktigt!**

Systemet har nu både **reaktiv** och **proaktiv** token-hantering som säkerställer kontinuerlig drift.

## Hur Token-hanteringen Fungerar

### Två Typer av Tokens

1. **Access Token**
   - Kortlivad (ca 1 timme)
   - Används för varje API-anrop
   - Förnyas automatiskt

2. **Refresh Token**
   - Långlivad (30-90 dagar, eller längre om den används regelbundet)
   - Används för att få nya access tokens
   - Behålls mellan förnyelser

### Automatisk Token-förnyelse (Tre Nivåer)

#### Nivå 1: Proaktiv Förnyelse (NY!)

Före varje API-anrop kontrolleras om access token snart löper ut:

```python
# src/auth.py, rad 167-181
if current_time >= (expires_at - 300):  # 5 minuter före utgång
    logger.info("Access token expiring soon, refreshing...")
    self.refresh_access_token()
```

**Fördelar:**
- Tokens förnyas INNAN de löper ut
- Inga avbrott i datainsamling
- Smidigare drift

#### Nivå 2: Reaktiv Förnyelse (Fanns Redan)

Om ett API-anrop misslyckas med 401 Unauthorized:

```python
# src/api_client.py, rad 66-79
if e.response.status_code == 401:
    logger.warning("Access token expired, refreshing...")
    self.auth.refresh_access_token()
    # Retry the request
```

**Fördelar:**
- Backup om proaktiv förnyelse misslyckas
- Hanterar oväntade token-utgångar

#### Nivå 3: Vid Uppstart

När tjänsten startar försöker den först förnya befintliga tokens:

```python
# src/auth.py, rad 172-179
if self.load_tokens():
    logger.info("Found saved tokens. Attempting to refresh...")
    try:
        self.refresh_access_token()
```

**Fördelar:**
- Säkerställer färska tokens vid boot
- Upptäcker utgångna tokens tidigt

## Vad Händer När Refresh Token Löper Ut?

Om refresh token löper ut (mycket ovanligt om systemet används regelbundet):

1. Tjänsten loggar felet:
   ```
   ERROR: Token refresh failed. Please re-authenticate with: python src/auth.py
   ```

2. Du får en **notifiering** i loggarna:
   ```bash
   journalctl -u nibe-autotuner | grep "refresh failed"
   ```

3. Du behöver **manuellt autentisera** igen (ta ca 1 minut):
   ```bash
   ssh pi@raspberrypi.local
   cd ~/nibe_autotuner
   source venv/bin/activate
   python src/auth.py
   sudo systemctl restart nibe-autotuner
   ```

## Hur Undvika Utgångna Refresh Tokens?

### ✅ Använd Regelbundet

Så länge datainsamlingen körs var 5:e minut kommer:
- Access tokens förnyas automatiskt varje timme
- Refresh tokens användas regelbundet
- myUplink API förlänger refresh token-giltighetstiden

### ✅ Övervaka Loggarna

Sätt upp en cron-job som varnar dig om autentiseringsfel:

```bash
# Skapa varningsscript
cat > ~/check_nibe_auth.sh << 'EOF'
#!/bin/bash
if journalctl -u nibe-autotuner --since "1 hour ago" | grep -q "refresh failed"; then
    echo "VARNING: Nibe autentisering misslyckades!" | mail -s "Nibe Auth Error" din@email.com
fi
EOF

chmod +x ~/check_nibe_auth.sh

# Lägg till i crontab (kör varje timme)
(crontab -l 2>/dev/null; echo "0 * * * * ~/check_nibe_auth.sh") | crontab -
```

### ✅ Backup Access

Sätt upp **Tailscale** eller **WireGuard** för säker fjärråtkomst till Pi, så kan du alltid autentisera på nytt även utanför hemmet.

## Förbättringar Gjorda

### Före (Gammal Kod)

```python
def get_access_token(self):
    # TODO: Check token expiration and refresh if needed
    # For now, just return the access token
    return self.tokens.get('access_token')
```

**Problem:**
- Ingen utgångskontroll
- Tokens löpte ut mitt under körning
- Datainsamling stannade

### Efter (Ny Kod)

```python
def get_access_token(self):
    # Check if token is expired or about to expire (within 5 minutes)
    if 'expires_at' in self.tokens:
        expires_at = self.tokens['expires_at']
        current_time = time.time()

        if current_time >= (expires_at - 300):
            logger.info("Access token expiring soon, refreshing...")
            self.refresh_access_token()

    return self.tokens.get('access_token')
```

**Lösning:**
- ✅ Kontrollerar utgång före varje anrop
- ✅ Förnyer proaktivt (5 min buffer)
- ✅ Kontinuerlig drift

### Ytterligare Förbättringar

1. **Expiration Timestamp**
   - Varje token sparas nu med `expires_at` timestamp
   - Möjliggör exakt utgångskontroll

2. **Refresh Token Bevarande**
   - Om API:et inte returnerar ny refresh token, behålls den gamla
   - Förhindrar förlust av refresh token

3. **Konsekvent Filplats**
   - Tokens sparas alltid i `~/.myuplink_tokens.json`
   - Fungerar oavsett var scriptet körs

## Testa Token-hanteringen

### Manuellt Test

```bash
cd ~/nibe_autotuner
source venv/bin/activate

# Kör test-script
python -c "
import sys
sys.path.insert(0, 'src')
from auth import MyUplinkAuth
import time
from datetime import datetime

auth = MyUplinkAuth()
auth.load_tokens()

if auth.tokens and 'expires_at' in auth.tokens:
    expires_at = auth.tokens['expires_at']
    now = time.time()
    time_left = (expires_at - now) / 60

    print(f'Token status:')
    print(f'  Utgår om: {int(time_left)} minuter')
    print(f'  Utgångsdatum: {datetime.fromtimestamp(expires_at)}')
    print(f'  Förnyelse vid: {datetime.fromtimestamp(expires_at - 300)}')
else:
    print('Tokens saknas eller saknar utgångsdatum')
"
```

### Övervaka Automatisk Förnyelse

```bash
# Se live-loggar och filtrera efter förnyelser
journalctl -u nibe-autotuner -f | grep -E "refresh|token"
```

Du bör se:
```
INFO: Access token expiring soon, refreshing...
INFO: Successfully refreshed access token
```

## Förväntad Token-livscykel

```
Dag 0:  Autentisera med auth.py
        └─> Access token: 1h
        └─> Refresh token: 90 dagar

Dag 0-90: Automatisk förnyelse varje timme
        ├─> 00:00 - Access token förnyas
        ├─> 01:00 - Access token förnyas
        ├─> 02:00 - Access token förnyas
        └─> ... fortsätter automatiskt

Dag 90+: Refresh token giltighetstid FÖRLÄNGS automatiskt
        (så länge systemet används regelbundet)
```

## Sammanfattning

| Scenario | Hantering | Användaråtgärd |
|----------|-----------|----------------|
| Access token löper ut | ✅ Automatisk förnyelse | Ingen |
| Access token snart utgången | ✅ Proaktiv förnyelse | Ingen |
| API returnerar 401 | ✅ Automatisk retry | Ingen |
| Tjänsten startar om | ✅ Förnyar vid boot | Ingen |
| Refresh token löper ut | ⚠️ Manuell autentisering | `python src/auth.py` |
| Pi offline >90 dagar | ⚠️ Manuell autentisering | `python src/auth.py` |

## Slutsats

Med de nya förbättringarna kommer din Raspberry Pi att:

✅ **Samla data kontinuerligt** utan avbrott
✅ **Förnya tokens automatiskt** varje timme
✅ **Hantera utgångar proaktivt** innan problem uppstår
✅ **Logga tydligt** om något går fel
✅ **Kräva minimal underhållning** (eventuellt re-autentisering 1-2 gånger/år om alls)

**Förväntad underhållning:** Nästan ingen. Om systemet körs kontinuerligt kommer refresh tokens förnyas av myUplink automatiskt och du behöver aldrig autentisera igen.

**Worst case:** Om Pi är offline i 90+ dagar behöver du autentisera igen (tar 1 minut).

---

**Senast uppdaterad:** 2025-11-25
**Status:** ✅ Produktionsklar med robust token-hantering
