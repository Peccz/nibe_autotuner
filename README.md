# Nibe Autotuner

En Android-app som optimerar Nibe värmepumpar genom intelligent analys och automatisk justering av inställningar.

## Projektöversikt

Nibe Autotuner skapar en förståelse för hur ditt värmepumpsystem är uppbyggt genom att användaren beskriver systemet med text och bilder. Appen analyserar sedan data från Nibe/myUplink API eller importerade CSV-filer för att optimera systemets prestanda.

### Funktioner (Planerade)

- 📊 **Datainsamling** från myUplink API eller CSV-import
- 🧠 **Systemförståelse** genom text- och bildbeskrivningar
- 📈 **Intelligent analys** av driftsdata
- ⚙️ **Automatisk optimering** av inställningar
- 📱 **Android-app** med användarvänligt gränssnitt
- 🔄 **Manuellt läge** för system utan API-skrivbehörighet

## Projektstruktur

```
nibe_autotuner/
├── src/                    # Python källkod
│   ├── auth.py            # OAuth2 autentisering
│   ├── api_client.py      # myUplink API-klient
│   └── ...
├── tests/                 # Enhetstester
├── docs/                  # Dokumentation
├── config/                # Konfigurationsfiler
├── data/                  # Databas och CSV-filer
├── requirements.txt       # Python-beroenden
├── .env.example          # Exempel på miljövariabler
└── README.md             # Denna fil
```

## Komma Igång

### Förutsättningar

- Python 3.9 eller senare
- Ett Nibe-konto med tillgång till myUplink
- En Nibe värmepump som är ansluten till myUplink

### Installation

1. **Klona projektet** (eller navigera till projektmappen)
   ```bash
   cd nibe_autotuner
   ```

2. **Skapa virtuell miljö**
   ```bash
   python -m venv venv
   source venv/bin/activate  # På Linux/Mac
   # eller
   venv\Scripts\activate  # På Windows
   ```

3. **Installera beroenden**
   ```bash
   pip install -r requirements.txt
   ```

4. **Skapa .env-fil**
   ```bash
   cp .env.example .env
   ```

### Registrera App på myUplink Developer Portal

För att använda myUplink API måste du registrera en applikation:

1. **Gå till myUplink Developer Portal**
   - Besök: https://dev.myuplink.com/
   - Logga in med ditt Nibe/myUplink-konto

2. **Skapa en ny applikation**
   - Klicka på "Applications" eller "My Apps"
   - Klicka på "Create Application" eller "New Application"

3. **Fyll i applikationsdetaljer**
   - **Name**: `Nibe Autotuner` (eller valfritt namn)
   - **Description**: `Automatic optimization tool for Nibe heat pumps`
   - **Redirect URI**: `http://localhost:8080/oauth/callback`
   - **Scopes**: Välj `READSYSTEM` och `WRITESYSTEM`

4. **Spara och hämta credentials**
   - Efter att du skapat appen, kopiera:
     - **Client ID**
     - **Client Secret**

5. **Uppdatera .env-filen**
   ```bash
   MYUPLINK_CLIENT_ID=din_client_id_här
   MYUPLINK_CLIENT_SECRET=din_client_secret_här
   ```

### Testa API-anslutningen

1. **Autentisera mot myUplink**
   ```bash
   python src/auth.py
   ```

   Detta kommer att:
   - Öppna din webbläsare för inloggning
   - Starta en lokal server för att ta emot OAuth-callback
   - Spara dina tokens i `tokens.json`

2. **Hämta data från dina enheter**
   ```bash
   python src/api_client.py
   ```

   Detta kommer att:
   - Visa alla dina system
   - Lista alla enheter per system
   - Visa exempel på datapunkter (temperaturer, status, etc.)

## API-dokumentation

### Tillgängliga Endpoints

- `GET /v2/systems/me` - Hämta alla system
- `GET /v2/systems/{systemId}` - Systemdetaljer
- `GET /v2/systems/{systemId}/devices` - Lista enheter
- `GET /v2/devices/{deviceId}/points` - Hämta alla datapunkter
- `GET /v2/devices/{deviceId}/points/{pointId}` - Hämta specifik datapunkt
- `PATCH /v2/devices/{deviceId}/points/{pointId}` - Ändra inställning (kräver WRITESYSTEM)

### Vanliga Datapunkter

Exempel på vanliga parameter-ID:n (kan variera mellan modeller):

- `40004`: Utetemperatur (BT1)
- `40079`: Ström (A)
- `41778`: Kompressorfrekvens
- Temperature readings: BT1 (outdoor), supply/return line temps
- System status: Operating mode, compressor frequency
- Energy data: Current draw, power consumption

**Obs**: Parameter-ID:n kan variera mellan olika Nibe-modeller. Använd `api_client.py` för att se vilka som är tillgängliga för din pump.

## Begränsningar och Anteckningar

### API Write Access
- Möjligheten att **skriva** inställningar via API:et är ännu inte helt verifierad
- Kan kräva Premium-prenumeration på myUplink
- Projektet har stöd för **manuell inmatning** som backup
  - Användaren kan ändra inställningar manuellt
  - Rapportera tillbaka ändringarna till appen
  - Appen analyserar effekten av ändringarna

### Rate Limits
- myUplink API har sannolikt rate limits
- För frekvent polling, överväg att cacha data

### Säkerhet
- **Dela ALDRIG** din `.env`-fil eller `tokens.json`
- Dessa innehåller känsliga autentiseringsuppgifter
- Filer är automatiskt exkluderade via `.gitignore`

## Nästa Steg i Utvecklingen

- [ ] Implementera databas för lagring av historisk data
- [ ] Skapa CSV-importfunktionalitet
- [ ] Utveckla analysmotor för optimering
- [ ] Designa systemförståelse-modul (AI/ML)
- [ ] Börja Android-app-utveckling
- [ ] Implementera automatisk inställningsjustering
- [ ] Testa med riktiga Nibe-system

## Bidra

Detta är för närvarande ett privat projekt under utveckling.

## Licens

TBD

## Kontakt

För frågor eller feedback, skapa en issue i projektet.

---

**Status**: 🚧 Under aktiv utveckling

**Senast uppdaterad**: 2025-11-24
