import re
import os

file_path = 'src/integrations/autonomous_ai_agent_v2.py'

# Den nya listan för December 2025 (Högst intelligens först)
new_config = """    # Priority: Next-Gen Reasoning -> Stable Pro -> Balanced -> Infinite Lite
    FALLBACK_MODELS = [
        {
            'provider': 'gemini',
            'model': 'gemini-3.0-pro-preview',
            'name': 'Gemini 3.0 Pro (Next-Gen Reasoning)',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-2.5-pro',
            'name': 'Gemini 2.5 Pro (Senior Consultant)',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-2.5-flash',
            'name': 'Gemini 2.5 Flash (Balanced)',
            'requires_api_key': 'GOOGLE_API_KEY',
        },
        {
            'provider': 'gemini',
            'model': 'gemini-2.5-flash-lite',
            'name': 'Gemini 2.5 Flash-Lite (High Availability)',
            'requires_api_key': 'GOOGLE_API_KEY',
        }
    ]"""

try:
    with open(file_path, 'r') as f:
        content = f.read()

    # Regex för att hitta den gamla listan (hanterar radbrytningar korrekt)
    # Letar efter "FALLBACK_MODELS = [" följt av innehåll och slutligen "]"
    pattern = re.compile(r'    FALLBACK_MODELS = \[.*?\]', re.DOTALL)
    
    if pattern.search(content):
        new_content = pattern.sub(new_config, content)
        with open(file_path, 'w') as f:
            f.write(new_content)
        print("✅ SUCCESS: Modellistan uppdaterad till 2025-standard!")
    else:
        print("❌ ERROR: Kunde inte hitta 'FALLBACK_MODELS' listan. Kontrollera indenteringen.")

except Exception as e:
    print(f"❌ CRITICAL ERROR: {e}")
