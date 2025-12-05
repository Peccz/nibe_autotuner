# Changelog 2025-12-01

## Token Authentication Fix

### Problem
- MyUplink API tokens expirerade efter 1 timme
- Ingen `refresh_token` returnerades i OAuth response
- Dataloggern slutade fungera när token gick ut

### Lösning
- Lade till `offline_access` scope i OAuth flow (auth.py:92)
- Re-autentiserade och fick giltig `refresh_token`
- Token förnyas nu automatiskt var timme

### Resultat
- ✅ Tokens giltiga i 90 dagar
- ✅ Automatisk förnyelse fungerar
- ✅ Dataloggning kontinuerlig var 5:e minut

## Kompressor Threshold Fix

### Problem
- Kompressor vid exakt 20 Hz exkluderades från analys
- Användes `> 20` istället för `>= 20`

### Lösning
- Ändrade threshold till `>= 20 Hz` på 3 platser (analyzer.py:392, 495, 746)

### Resultat
- ✅ All kompressoraktivitet inkluderas nu

## Chart.js Visualization Fix

### Problem
- Grafer laddade inte pga saknad date adapter
- Fel: "date adapter not implemented"

### Lösning
- Tog bort `type: 'time'` från x-axis config
- Använder category scale med custom formatter istället

### Resultat
- ✅ Alla 5 grafer fungerar utan external dependencies
- ✅ Data decimeras till max 200 punkter för prestanda

## Nya Funktioner

### Separata Metriker
- Individuella COP-värden för uppvärmning vs varmvatten
- Baserat på supply temp threshold (45°C)
- Runtime och cykelräkning per läge

### Performance Tiers
- 🏆 ELITE (COP ≥4.5 heating, ≥4.0 hot water)
- ⭐ EXCELLENT (COP ≥4.0 heating, ≥3.5 hot water)
- ✨ VERY GOOD
- ✅ GOOD
- 👍 OK
- ⚠️ POOR

### Optimeringspoäng
- 0-100 poäng baserat på:
  - Heating COP (30 pts)
  - Hot Water COP (20 pts)
  - Delta T (25 pts)
  - Degree Minutes (15 pts)
  - Runtime Efficiency (10 pts)

## Testresultat 2025-12-01

### Senaste veckan (168h)
- Heating COP: 4.28 ⭐ EXCELLENT
- Hot Water COP: 3.05 ✅ GOOD
- Total readings: 41,742
- Kompressor aktiv senast: 2025-11-30 19:40

### System Status
- Dataloggning: ✅ Aktiv (var 5:e minut)
- Mobile PWA: ✅ Körs på port 8502
- Token: ✅ Giltig med auto-renewal
- Grafer: ✅ Alla 5 fungerar

## Parameter Changes API Fix

### Problem
- Changes form kunde inte spara ändringar
- Fel: "'parameter_type' is an invalid keyword argument for ParameterChange"
- API använde fel modellschema

### Lösning
- Uppdaterade mobile_app.py att använda korrekt schema (device_id, parameter_id FKs)
- Inaktiverade formulär med info-meddelande
- Historik-visning fungerar fortfarande

### Resultat
- ✅ Backend API använder korrekt ParameterChange-modell
- ℹ️ Formulär tillfälligt inaktiverat för uppdatering

## Commits
- e8ba14a: Fix parameter changes API to use correct model fields
- 59f5c43: Remove Chart.js time scale dependency
- 0a57943: Add offline_access scope to get refresh token
- 9b3c294: Add token fix script
- 912c16f: Add system verification script
- 8237a79: Fix compressor threshold - include readings at exactly 20 Hz
