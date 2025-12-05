# Nibe Autotuner - Mobile PWA

Progressive Web App för mobil åtkomst till din Nibe värmepump.

## Funktioner

✅ **Dashboard** - Realtidsdata och nyckeltal
✅ **Visualiseringar** - Interaktiva grafer för temperaturer och effektivitet
✅ **Ändringslogg** - Logga manuella justeringar
✅ **Baseline-dokumentation** - Optimeringstips och teknisk information
✅ **PWA** - Installeras som app på Android/iOS
✅ **Offline-stöd** - Fungerar utan internetanslutning (begränsat)
✅ **Auto-refresh** - Uppdaterar data varje 5 minuter

## Installation

### På Raspberry Pi

1. **Uppdatera koden:**
   ```bash
   cd ~/nibe_autotuner
   git pull origin main
   ```

2. **Installera Flask:**
   ```bash
   source venv/bin/activate
   pip install flask
   ```

3. **Installera systemd-tjänst:**
   ```bash
   sudo cp nibe-mobile.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable nibe-mobile
   sudo systemctl start nibe-mobile
   ```

4. **Kontrollera status:**
   ```bash
   sudo systemctl status nibe-mobile
   ```

### På Din Huvuddator

Samma steg som ovan, men kör från `/home/peccz/AI/nibe_autotuner`.

## Åtkomst

När tjänsten körs:

- **Lokal dator:** http://localhost:8502
- **Från telefon (samma nätverk):** http://raspberrypi.local:8502
- **Från telefon (Tailscale):** http://100.100.118.62:8502

## Installera som App på Telefonen

1. Öppna webbadressen i din mobila webbläsare (Chrome/Safari)
2. Tryck på meny-ikonen (⋮ på Android, □↑ på iOS)
3. Välj "Lägg till på hemskärmen" eller "Add to Home Screen"
4. Ge appen ett namn (t.ex. "Nibe")
5. Appen läggs nu till som en ikon på hemskärmen

### Android

![Install on Android](https://i.imgur.com/7QzPZ9w.png)

1. Chrome menu → "Lägg till på startskärmen"
2. Appen installeras och kan öppnas som en vanlig app

### iOS (iPhone/iPad)

![Install on iOS](https://i.imgur.com/9bXvQ2t.png)

1. Safari → Del-knappen (□↑)
2. "Lägg till på hemskärmen"
3. Appen installeras

## Funktioner

### Dashboard
- COP (Värmefaktor)
- Gradminuter
- Delta T (Aktiv uppvärmning)
- Kompressorfrekvens
- Temperaturer (ute, inne, fram, retur)
- Systeminställningar

### Visualiseringar
- Utomhustemperatur
- Inomhustemperatur
- Fram & returtemperatur
- Kompressorfrekvens
- Varmvattentemperatur

Alla grafer är interaktiva och kan visas för 1 timme upp till 1 vecka tillbaka.

### Ändringslogg
Logga manuella justeringar du gör:
- Typ av ändring (värmekurva, varmvatten, etc.)
- Gamla och nya värden
- Anledning till ändring
- Anteckningar

Se historik över alla ändringar med tidsstämplar.

### Baseline-dokumentation
Offline-tillgänglig dokumentation:
- **Nibe F730** - Optimala värden, viktiga inställningar, underhåll
- **Delta T** - Vad det är, optimala värden, hur man justerar
- **COP** - Värmefaktor, typiska värden, hur man förbättrar
- **Optimeringstips** - Säsongsspecifika tips, varningssignaler

## Portar

- **8501:** Streamlit GUI (desktop)
- **8502:** Mobile PWA (mobil)
- **8503:** API Server (framtida)

## Felsökning

### Tjänsten startar inte

```bash
sudo journalctl -u nibe-mobile -n 50
```

### Kan inte nå från telefonen

Kontrollera att:
1. Telefon och server är på samma nätverk
2. Firewall tillåter port 8502
3. Tjänsten körs: `sudo systemctl status nibe-mobile`

### PWA-installation fungerar inte

- **Chrome/Android:** Kräver HTTPS eller localhost
- **Safari/iOS:** Fungerar även med HTTP på lokalt nätverk
- Prova att öppna http://192.168.x.x:8502 istället för raspberrypi.local

### Data uppdateras inte

- Kontrollera att `nibe-autotuner` tjänsten körs (datainsamling)
- Se loggar: `journalctl -u nibe-autotuner -f`

## Utveckling

Starta manuellt för development:

```bash
cd ~/nibe_autotuner
source venv/bin/activate
PYTHONPATH=./src python src/mobile_app.py
```

Appen startar på http://0.0.0.0:8502

## Teknisk Stack

- **Backend:** Flask 3.1+
- **Frontend:** Vanilla JavaScript + CSS
- **Grafer:** Chart.js 4.4
- **Database:** SQLite (samma som huvudsystemet)
- **PWA:** Service Worker + Web Manifest

## Jämförelse: PWA vs Streamlit

| Funktion | Mobile PWA | Streamlit GUI |
|----------|-----------|---------------|
| Optimerad för | Mobil | Desktop |
| Installeras som app | ✅ Ja | ❌ Nej |
| Offline-stöd | ✅ Delvis | ❌ Nej |
| Laddningstid | ⚡ Snabb | 🐌 Långsam |
| Datautbyte | Minimal | Hög |
| Visualiseringar | Interaktiva | Statiska PNG |
| Rekommendationer | ❌ Nej | ✅ Ja |
| Detaljerad analys | ❌ Nej | ✅ Ja |

**Rekommendation:** Använd PWA för daglig övervakning på telefonen, Streamlit för djupanalys på datorn.

## Framtida Förbättringar

- [ ] Push-notifikationer vid avvikelser
- [ ] Dark mode
- [ ] Snabbåtgärder ("Quick actions") från app-ikonen
- [ ] Historik-export (CSV/PDF)
- [ ] Jämför periods (före/efter ändringar)

## Support

- GitHub: https://github.com/Peccz/nibe_autotuner
- Issues: https://github.com/Peccz/nibe_autotuner/issues

---

**Senast uppdaterad:** 2025-11-29
