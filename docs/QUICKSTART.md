# Snabbstart - Nibe Autotuner

Följ dessa steg för att komma igång snabbt:

## Steg 1: Installera Python-beroenden

```bash
# Skapa virtuell miljö
python -m venv venv

# Aktivera virtuell miljö
source venv/bin/activate  # Linux/Mac
# eller
venv\Scripts\activate     # Windows

# Installera beroenden
pip install -r requirements.txt
```

## Steg 2: Registrera på myUplink Developer Portal

1. Gå till: https://dev.myuplink.com/
2. Logga in med ditt Nibe/myUplink-konto
3. Skapa en ny applikation:
   - **Name**: Nibe Autotuner
   - **Redirect URI**: `http://localhost:8080/oauth/callback`
   - **Scopes**: `READSYSTEM` och `WRITESYSTEM`
4. Kopiera **Client ID** och **Client Secret**

## Steg 3: Konfigurera miljövariabler

```bash
# Kopiera exempel-filen
cp .env.example .env

# Redigera .env och lägg till dina credentials:
# MYUPLINK_CLIENT_ID=din_client_id_här
# MYUPLINK_CLIENT_SECRET=din_client_secret_här
```

## Steg 4: Testa autentisering

```bash
python src/auth.py
```

Detta kommer att:
- Öppna din webbläsare
- Be dig logga in på myUplink
- Spara dina tokens lokalt

## Steg 5: Hämta data från din värmepump

```bash
python src/api_client.py
```

Detta visar:
- Alla dina system
- Enheter per system
- Tillgängliga datapunkter
- Exempel på aktuella värden

## Vad händer nu?

Om allt fungerar ser du:
- ✅ Din systemID
- ✅ Dina enheter (värmepump, varmvattenberedare, etc.)
- ✅ Datapunkter med aktuella värden (temperaturer, status, etc.)

## Felsökning

### Problem: "Missing CLIENT_ID or CLIENT_SECRET"
- Kontrollera att `.env`-filen finns
- Kontrollera att värden är korrekt ifyllda (utan citattecken)

### Problem: "Failed to receive authorization code"
- Kontrollera att Redirect URI är exakt: `http://localhost:8080/oauth/callback`
- Kontrollera att port 8080 inte används av annat program

### Problem: "401 Unauthorized"
- Tokens kan ha gått ut
- Kör `python src/auth.py` igen för att autentisera på nytt

### Problem: "No systems found"
- Kontrollera att din värmepump är ansluten till myUplink
- Logga in på https://myuplink.com för att verifiera

## Nästa Steg

När du har verifierat att API-anslutningen fungerar:

1. **Utforska dina datapunkter** - Se vilka parametrar din värmepump exponerar
2. **Testa skrivåtkomst** - Kontrollera om du kan ändra inställningar via API:et
3. **Planera databasstruktur** - Hur ska vi lagra historisk data?
4. **Designa optimeringsalgoritmer** - Hur ska systemet analysera data?

## Hjälp

För mer information, se [README.md](README.md) eller skapa en issue i projektet.
