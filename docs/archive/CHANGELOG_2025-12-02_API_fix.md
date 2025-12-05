# Changelog 2025-12-02: MyUplink API Kompatibilitetsfix

## Problem som upptäcktes

Under testning upptäcktes att **MyUplink API v2 för Nibe F730** har betydligt mer begränsade skrivmöjligheter än förväntat:

1. **404-fel vid läsning/skrivning av individuella parametrar**
   - Endpointen `/v2/devices/{device_id}/points/{parameter_id}` returnerar 404
   - Detta gäller både GET och PATCH/POST/PUT requests
   - Trots att parametrarna visas som "writable" i device points-listan

2. **Endast 2 parametrar har Smart Home Categories**
   - 48132: Hot water boost (sh-hwBoost)
   - 50005: Increased ventilation (sh-ventBoost)
   - Inga värmerelaterade parametrar (47007, 47011, etc.) har smart home categories

3. **Parametrar som INTE kan skrivas via API**
   - 47007: Heating curve (Värmekurva)
   - 47011: Offset (Kurvjustering)
   - 43437: Pump speed (Pumphastighet) - även read-only
   - 47019: Max supply temp - existerar inte ens

## Lösning implementerad

### 1. Fixad `get_point_data()` metod
**Fil:** `src/api_client.py`

Istället för att försöka läsa individuell parameter via 404-endpointen, hämtar metoden nu alla device points och filtrerar:

```python
def get_point_data(self, device_id: str, point_id: str) -> Dict:
    # MyUplink API v2 doesn't support individual point GET, so fetch all and filter
    all_points = self.get_device_points(device_id)
    matching_points = [p for p in all_points if str(p.get('parameterId')) == str(point_id)]

    if not matching_points:
        raise ValueError(f"Point {point_id} not found")

    return matching_points[0]
```

**Resultat:** Läsning av parametrar fungerar nu felfritt ✅

### 2. Konverterat Quick Actions till rekommendationssystem
**Fil:** `src/mobile_app.py`

Alla quick action endpoints har uppdaterats för att returnera **rekommendationer** istället för att försöka ändra parametrar:

#### `/api/quick-action/adjust-offset`
- **Innan:** Försökte sätta parameter 47011 via API → 404-fel
- **Nu:** Returnerar rekommendation med manuella justeringsinstruktioner

```json
{
  "success": true,
  "message": "Rekommendation: Ändra offset från -2 till -1",
  "recommendation": {
    "parameter": "Offset (47011)",
    "current_value": -2,
    "recommended_value": -1,
    "reason": "Höj offset (+1)",
    "manual_adjustment": "Justera manuellt i värmepumpen: Meny 4.1.1"
  },
  "note": "MyUplink API stödjer inte automatisk justering..."
}
```

#### `/api/quick-action/optimize-efficiency`
- **Innan:** Försökte sänka room temp setpoint för bättre COP → 404-fel
- **Nu:** Analyserar system och returnerar COP-optimeringsrekommendationer

#### `/api/quick-action/optimize-comfort`
- **Innan:** Försökte justera offset för 21°C måltemperatur → 404-fel
- **Nu:** Beräknar optimal offset-justering och returnerar rekommendation

### 3. Uppdaterad systemdokumentation
**Fil:** `src/mobile/templates/ai_agent.html`

System prompt har uppdaterats med korrekt information om:
- Vilka parametrar som faktiskt är tillgängliga
- Att vissa parametrar (47007, 43437) kan vara read-only eller ej tillgängliga via API
- Instruktioner att endast rekommendera verifierade parametrar

## Systemets nya arbetssätt

### ✅ Vad som fungerar
1. **AI-analys och rekommendationer** - Gemini AI analyserar data och ger intelligenta råd
2. **Gemini Chat** - Interaktiv chat med AI-assistent
3. **Läsning av alla parametrar** - Fungerar felfritt via get_device_points()
4. **Quick Actions** - Returnerar nu smarta rekommendationer
5. **Dashboard och grafer** - All visualisering fungerar som tidigare
6. **Data logging** - Fortsätter samla in data var 5:e minut

### 🔄 Vad som ändrats
- **Systemet är nu rent rådgivande** - Inga automatiska parameterjusteringar
- **Användaren måste manuellt justera** - Antingen i värmepumpen eller via MyUplink-appen
- **Rekommendationer inkluderar instruktioner** - "Meny 4.1.1" för manuell justering

### ❌ Vad som inte fungerar (API-begränsningar)
- Automatisk justering av värmekurva (47007)
- Automatisk justering av offset (47011)
- Skrivning av pumphastighet (43437) - även read-only
- Individuell parameter-läsning via `/points/{id}` endpoint

## Tekniska detaljer

### MyUplink API v2 Begränsningar för F730
Efter grundlig testning kan vi konstatera:

1. **Device Points List** (GET `/v2/devices/{id}/points`)
   - ✅ Fungerar perfekt
   - Returnerar alla 102 parametrar
   - 42 markerade som "writable"

2. **Individual Point Access** (GET/PATCH `/v2/devices/{id}/points/{param_id}`)
   - ❌ Returnerar alltid 404
   - Gäller alla parametrar inkl. "writable" ones
   - Fungerar inte med PATCH, POST eller PUT

3. **Smart Home Categories**
   - Endast 2/42 "writable" parametrar har smart home categories
   - Värmerelaterade parametrar saknar dessa kategorier
   - Kan vara nyckeln till vilka parametrar som faktiskt kan skrivas

### Testade alternativ
- ✅ Fetch all points and filter (FUNKAR - implementerat)
- ❌ GET `/v2/devices/{id}/points/{param_id}` (404)
- ❌ PATCH `/v2/devices/{id}/points/{param_id}` (404)
- ❌ POST `/v2/devices/{id}/points/{param_id}` (404)
- ❌ PUT `/v2/devices/{id}/points/{param_id}` (404)
- ❌ GET `/v3/devices/{id}/points/{param_id}` (404)
- ❌ GET `/v2/parameters/{id}/{param_id}` (404)

## Deployment

### Commit
```
8c1a93f - Fix MyUplink API compatibility and make recommendations advisory
```

### Deployed till Raspberry Pi
```bash
ssh nibe-rpi 'cd /home/peccz/nibe_autotuner && git pull'
sudo systemctl restart nibe-autotuner
sudo systemctl restart nibe-mobile
```

### Services status
- ✅ nibe-autotuner.service - Active (running)
- ✅ nibe-mobile.service - Active (running)
- ✅ nibe-gui.service - Active (running)

## Användarupplevelse

### Innan
1. Användaren klickar "Höj temp" → **404-fel**
2. AI ger rekommendation med Apply/Dismiss → **404-fel vid Apply**
3. Quick actions misslyckas → **Frustration**

### Efter
1. Användaren klickar "Höj temp" → **Rekommendation med manual instruktion**
2. AI ger rekommendation → **"Justera manuellt i Meny 4.1.1"**
3. Quick actions returnerar smarta råd → **Tydlig vägledning**

## Framtida möjligheter

### Potentiella lösningar att utforska
1. **Smart Home Category endpoint** - Kanske finns ett separat endpoint för parametrar med smart home categories
2. **Bulk update endpoint** - Möjligen finns batch-uppdatering
3. **WebSocket/MQTT** - Alternativ kommunikationsmetod
4. **Premium API tier** - Kanske krävs betald subscription för full write access

### För närvarande
Systemet fungerar utmärkt som ett **intelligent rådgivningssystem**:
- AI analyserar prestanda
- Gemini ger smarta rekommendationer
- Användaren fattar beslut och justerar manuellt
- Systemet loggar resultat och lär sig

Detta är faktiskt en **säkrare approach** - användaren har full kontroll och systemet kan inte göra oavsiktliga ändringar.

## Sammanfattning

✅ **Problem löst** - Inga fler 404-fel
✅ **System fungerar** - AI-analys och rekommendationer körr smidigt
✅ **Deployed till RPi** - Alla services aktiva
✅ **Användarupplevelse** - Tydliga rekommendationer med manuella instruktioner

🔄 **Ny approach** - Rent rådgivande system istället för automatiska justeringar
📚 **Lärdomar** - MyUplink API v2 har betydligt mer begränsad write access än dokumenterat

---

**Status:** Systemet rullar stabilt på Raspberry Pi med de nya API-kompatibla lösningarna. ✨
