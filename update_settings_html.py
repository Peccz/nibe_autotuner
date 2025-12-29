with open('settings.html', 'r') as f:
    lines = f.readlines()

# Hitta var vi ska infoga HTML (före sista card eller liknande)
insert_html_pos = -1
for i, line in enumerate(lines):
    if "<!-- Advanced Settings -->" in line: # Try finding advanced settings
        insert_html_pos = i
        break
    if "saveSettings()" in line and "button" in line: # Or before save button div
        # Find start of that card div
        pass

# Fallback: Insert as first card in container
for i, line in enumerate(lines):
    if "<div class=\"container" in line:
        insert_html_pos = i + 2 # After h2 header usually
        break

# Actually, let's just append it before the script tag at the bottom of the content block
for i, line in enumerate(lines):
    if "<script>" in line:
        insert_html_pos = i
        break

if insert_html_pos != -1:
    new_html = """
    <!-- Away Mode -->
    <div class="card bg-dark text-white mb-4 border-info">
        <div class="card-header border-info">
            <i class="bi bi-airplane"></i> Semester / Borta
        </div>
        <div class="card-body">
            <p class="text-muted small">Sänker temperaturen till 16°C och stänger av varmvatten.</p>
            
            <div class="form-check form-switch mb-3">
                <input class="form-check-input" type="checkbox" id="away-enabled">
                <label class="form-check-label" for="away-enabled">Aktivera Borta-läge</label>
            </div>
            
            <div class="mb-3">
                <label for="away-end" class="form-label">Hemkomst</label>
                <input type="datetime-local" class="form-control bg-dark text-white" id="away-end">
            </div>
            
            <button class="btn btn-info w-100" onclick="saveAwayMode()">Spara Semesterläge</button>
        </div>
    </div>
"""
    lines.insert(insert_html_pos, new_html)

# Add JS functions
# We need to add saveAwayMode and update loadSettings/saveSettings
# Easier to just append new functions and call them manually or hook into existing.

js_insert_pos = -1
for i, line in enumerate(lines):
    if "function saveSettings()" in line:
        js_insert_pos = i
        break

if js_insert_pos != -1:
    new_js = """
    async function saveAwayMode() {
        const enabled = document.getElementById('away-enabled').checked;
        const endDate = document.getElementById('away-end').value;
        
        try {
            const response = await fetch('/api/settings/away-mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    enabled: enabled,
                    end_date: endDate ? new Date(endDate).toISOString() : null
                })
            });
            const result = await response.json();
            if (result.success) {
                alert('Semesterläge sparat!');
            } else {
                alert('Fel: ' + result.error);
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Kunde inte spara.');
        }
    }
    
    // Hook into loadSettings to populate fields
    // This requires parsing the original loadSettings function which is hard via script.
    // Instead we overwrite loadSettings if possible or append a separate loader.
"""
    lines.insert(js_insert_pos, new_js)

# Update loadSettings to fetch away mode data
# We look for the line where json is parsed
for i, line in enumerate(lines):
    if "document.getElementById('min-indoor').value = s.min_indoor_temp;" in line:
        lines.insert(i+1, "            if (s.away_mode_enabled !== undefined) document.getElementById('away-enabled').checked = s.away_mode_enabled;\n")
        lines.insert(i+2, "            if (s.away_mode_end_date) document.getElementById('away-end').value = s.away_mode_end_date.slice(0, 16);\n")
        break

with open('settings_updated.html', 'w') as f:
    f.writelines(lines)
