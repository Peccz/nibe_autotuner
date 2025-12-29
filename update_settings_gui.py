with open('settings_to_update.html', 'r') as f:
    lines = f.readlines()

# Hitta "Minsta innetemperatur" blocket och ersätt med utökad version
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if "label for=\"min-indoor\"" in line:
        start_idx = i - 1 # Div wrapper
        # Find end of this div
        for j in range(i, len(lines)):
            if "</div>" in lines[j] and "mb-3" in lines[start_idx]: # Simple heuristic
                end_idx = j + 1
                break
        break

if start_idx != -1:
    new_html = """                    <div class="mb-3">
                        <label for="min-indoor" class="form-label text-danger"><i class="bi bi-shield-lock"></i> Absolut Lägsta (Säkerhet)</label>
                        <div class="input-group">
                            <input type="number" class="form-control bg-dark text-white border-secondary" id="min-indoor" step="0.5" min="15" max="25">
                            <span class="input-group-text bg-secondary text-white border-secondary">°C</span>
                        </div>
                        <div class="form-text text-muted">Systemet tillåts ALDRIG gå under denna temperatur.</div>
                    </div>

                    <div class="mb-3">
                        <label class="form-label text-success"><i class="bi bi-thermometer-sun"></i> Komfortintervall (Mål)</label>
                        <div class="input-group">
                            <span class="input-group-text bg-dark text-muted border-secondary">Min</span>
                            <input type="number" class="form-control bg-dark text-white border-secondary" id="target-min" step="0.5" min="18" max="25">
                            <span class="input-group-text bg-dark text-muted border-secondary">Max</span>
                            <input type="number" class="form-control bg-dark text-white border-secondary" id="target-max" step="0.5" min="18" max="25">
                            <span class="input-group-text bg-secondary text-white border-secondary">°C</span>
                        </div>
                        <div class="form-text text-muted">AI:n optimerar för att ligga här. Höj Min för att tvinga buffring.</div>
                    </div>
"""
    # Vi ersätter inte, vi infogar efter min-indoor div om vi inte kan ersätta säkert.
    # Men vi vill ersätta det gamla fältet för det var bara min-indoor.
    # Låt oss anta att vi ersätter det.
    del lines[start_idx:end_idx]
    lines.insert(start_idx, new_html)

# Uppdatera JS
# loadSettings
for i, line in enumerate(lines):
    if "document.getElementById('min-indoor').value = s.min_indoor_temp;" in line:
        lines.insert(i+1, "            document.getElementById('target-min').value = s.target_indoor_temp_min;\n")
        lines.insert(i+2, "            document.getElementById('target-max').value = s.target_indoor_temp_max;\n")
        break

# saveSettings
for i, line in enumerate(lines):
    if "const minIndoor = document.getElementById('min-indoor').value;" in line:
        lines.insert(i+1, "        const targetMin = document.getElementById('target-min').value;\n")
        lines.insert(i+2, "        const targetMax = document.getElementById('target-max').value;\n")
        break

for i, line in enumerate(lines):
    if "min_indoor_temp: minIndoor," in line:
        lines.insert(i+1, "                target_indoor_temp_min: targetMin,\n")
        lines.insert(i+2, "                target_indoor_temp_max: targetMax,\n")
        break

with open('settings_gui_v2.html', 'w') as f:
    f.writelines(lines)
