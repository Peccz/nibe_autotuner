# Till: Autonomous AI Agent (Claude/Gemini Hybrid)
# Från: System Engineer (Gemini)
# Datum: 2025-12-04
# Ämne: FAS 2 - Elprisstyrning & Gemini-motor

Vi har nu ett system som överträffar Nibe SPA genom att kombinera elprisdata med komfortregler.

## Arkitekturuppdatering

*   **Driftmotor:** `src/autonomous_ai_agent_v2.py` drivs nu av **Google Gemini 2.0 Flash**.
    *   *Varför?* Du har redan en Google-nyckel, och det är extremt snabbt.
    *   *Krav:* `GOOGLE_API_KEY` i `.env` (Redan klart).
*   **Prisdata:** `src/price_service.py` hämtar 15-minuters spotpriser.
    *   *Källa:* Tibber API (Primär) > Elprisetjustnu.se (Backup/Timmar).
    *   *Krav:* `TIBBER_API_TOKEN` i `.env` (Redan klart).

## Nya Parametrar (102 st identifierade)

Vi har verifierat 102 parametrar via Deep Scan. Här är de viktigaste för din nya logik:

| ID | Namn | Syfte | Strategi |
|:---|:---|:---|:---|
| **47011** | Offset | Värmejustering | Sänk (-1) vid "Expensive". |
| **47041** | Hot water demand | Varmvattenkomfort | Sätt till 0 (Small) vid extrempriser/natt. |
| **50005** | Increased vent. | Ventilation | Håll lågt (0) för att spara värme, öka vid behov. |
| **47206** | Start compressor | Startgräns (DM) | -200 DM är bra. Ändra ej utan analys. |

## Uppdrag till Claude Code (Developer Agent)

Din uppgift är att underhålla detta system. Koden är redan skriven av Gemini, men du ansvarar för vidareutveckling.

1.  **Verifiera Drift:** Kör `python src/autonomous_ai_agent_v2.py` (Dry Run) och se att den hittar priser och gör vettiga val.
2.  **Säkerhet:** Kör alltid `./venv/bin/pytest tests/test_safety_guardrails_v2.py` efter ändringar.
3.  **Cron:** Se till att `scripts/run_ai_agent.sh` pekar på `autonomous_ai_agent_v2.py` och körs varje timme (`0 * * * *`).

## Framtidssäkring: 15-minuters Optimering

*   **Status:** Vi har datan (Tibber) och motorn (Gemini).
*   **Nästa steg:** När du vill öka precisionen, ändra cron-jobbet till `*/15 * * * *`.

Systemet är redo.
/Gemini