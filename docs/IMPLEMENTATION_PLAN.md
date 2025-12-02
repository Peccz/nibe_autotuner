# GUI Optimization - Implementation Plan

**Datum:** 2025-12-02
**Baserad på:** GUI_AUDIT.md

---

## Phase 1: Dashboard Cleanup (HIGH PRIORITY)

### Mål
Förbättra läsbarheten och minska redundans på huvuddashboarden. Gör det möjligt att förstå systemets status på < 5 sekunder.

### Ändringar

#### 1.1 Ta bort redundant Delta T Analys sektion
**Fil:** `src/mobile/templates/dashboard.html`
**Rader:** 236-250

**Action:**
```html
<!-- TA BORT HELT -->
<section class="section">
    <h2 class="section-title">📊 Delta T Analys</h2>
    ...
</section>
```

**Motivering:** Information visas redan i huvudmetriker och i system-jämförelsen.

---

#### 1.2 Integrera temperatursektion med ventilation
**Fil:** `src/mobile/templates/dashboard.html`
**Rader:** 121-142 (temperaturer) + 144-176 (ventilation)

**Action:** Slå samman till en "Klimat & Ventilation" sektion

**Nuvarande:**
```html
<!-- Temperaturer -->
<section class="section">
    <h2 class="section-title">🌡️ Temperaturer</h2>
    ...
</section>

<!-- Ventilation Status -->
<section class="section" id="ventilationSection">
    ...
</section>
```

**Nytt:**
```html
<section class="section">
    <h2 class="section-title">🌡️ Klimat & Ventilation</h2>

    <!-- Temperature overview -->
    <div class="climate-overview">
        <div class="climate-main">
            <div class="climate-item highlight">
                <span class="climate-icon">🏠</span>
                <div class="climate-data">
                    <span class="climate-value" id="indoorTemp">-</span>
                    <span class="climate-label">Inomhus</span>
                </div>
            </div>
            <div class="climate-item">
                <span class="climate-icon">🌤️</span>
                <div class="climate-data">
                    <span class="climate-value" id="outdoorTemp">-</span>
                    <span class="climate-label">Utomhus</span>
                </div>
            </div>
        </div>
    </div>

    <!-- Ventilation strategy -->
    <div class="ventilation-card">
        <div class="vent-header">
            <div class="strategy-badge" id="ventStrategyBadge">-</div>
            <span class="ventilation-status" id="ventStatus"></span>
        </div>
        <div class="vent-metrics-compact">
            <span>💨 <span id="fanSpeed">-</span></span>
            <span>🌡️ <span id="exhaustTemp">-</span></span>
            <span>💧 <span id="rhDrop">-</span> RH-drop</span>
        </div>
        <div class="ventilation-reasoning-compact" id="ventReasoning">
            <!-- Kortare reasoning -->
        </div>
    </div>

    <!-- System temps (collapsible details) -->
    <details class="temp-details">
        <summary>Systemtemperaturer</summary>
        <div class="temp-grid">
            <div class="temp-item">
                <span class="temp-label">Fram</span>
                <span class="temp-value" id="supplyTemp">-</span>
            </div>
            <div class="temp-item">
                <span class="temp-label">Retur</span>
                <span class="temp-value" id="returnTemp">-</span>
            </div>
        </div>
    </details>
</section>
```

**CSS additions:**
```css
.climate-overview {
    margin-bottom: 1rem;
}

.climate-main {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
}

.climate-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem;
    background: white;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.climate-item.highlight {
    border: 2px solid var(--primary-color);
}

.climate-icon {
    font-size: 2rem;
}

.climate-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--primary-color);
}

.climate-label {
    font-size: 0.75rem;
    color: var(--text-secondary);
}

.ventilation-card {
    background: white;
    padding: 1rem;
    border-radius: 8px;
    margin-top: 1rem;
}

.vent-metrics-compact {
    display: flex;
    justify-content: space-around;
    margin: 0.75rem 0;
    font-size: 0.9rem;
    color: var(--text-secondary);
}

.ventilation-reasoning-compact {
    font-size: 0.85rem;
    color: var(--text-secondary);
    padding: 0.75rem;
    background: #f8f9fa;
    border-radius: 4px;
}

.temp-details {
    margin-top: 1rem;
    padding: 0.5rem;
    background: #f8f9fa;
    border-radius: 8px;
    cursor: pointer;
}

.temp-details summary {
    font-size: 0.9rem;
    color: var(--text-secondary);
    user-select: none;
}

.temp-details[open] summary {
    margin-bottom: 0.75rem;
}
```

---

#### 1.3 Flytta "Uppvärmning vs Varmvatten" till ny Analysis sida
**Fil:** `src/mobile/templates/dashboard.html`
**Rader:** 252-319

**Action:**
1. Ta bort från dashboard.html
2. Skapa ny fil: `src/mobile/templates/analysis.html`
3. Lägg till länk från dashboard: "Se detaljerad analys →"

**Dashboard summary (ersätter current section):**
```html
<section class="section">
    <h2 class="section-title">📊 Systemöversikt</h2>
    <div class="system-summary">
        <div class="system-card heating">
            <div class="system-header">
                <span class="system-icon">🔥</span>
                <span class="system-title">Uppvärmning</span>
            </div>
            <div class="system-metrics">
                <div class="metric-primary">
                    COP: <strong id="heatingCOPSummary">-</strong>
                    <span class="metric-badge" id="heatingCOPBadgeSummary"></span>
                </div>
                <div class="metric-secondary">
                    <span id="heatingRuntimeSummary">-</span> · <span id="heatingCyclesSummary">-</span> cykler
                </div>
            </div>
        </div>

        <div class="system-card hotwater">
            <div class="system-header">
                <span class="system-icon">💧</span>
                <span class="system-title">Varmvatten</span>
            </div>
            <div class="system-metrics">
                <div class="metric-primary">
                    COP: <strong id="hotWaterCOPSummary">-</strong>
                    <span class="metric-badge" id="hotWaterCOPBadgeSummary"></span>
                </div>
                <div class="metric-secondary">
                    <span id="hotWaterRuntimeSummary">-</span> · <span id="hotWaterCyclesSummary">-</span> cykler
                </div>
            </div>
        </div>
    </div>
    <a href="/analysis" class="link-more">Se detaljerad analys →</a>
</section>
```

**CSS:**
```css
.system-summary {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
}

.system-card {
    background: white;
    padding: 1rem;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.system-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
}

.system-icon {
    font-size: 1.5rem;
}

.system-title {
    font-weight: 600;
    color: var(--text-primary);
}

.system-metrics {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.metric-primary {
    font-size: 1.1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.metric-primary strong {
    color: var(--primary-color);
    font-size: 1.3rem;
}

.metric-badge {
    padding: 0.15rem 0.4rem;
    border-radius: 4px;
    font-size: 0.7rem;
    color: white;
    font-weight: 600;
}

.metric-secondary {
    font-size: 0.85rem;
    color: var(--text-secondary);
}

.link-more {
    display: inline-block;
    margin-top: 0.75rem;
    color: var(--primary-color);
    text-decoration: none;
    font-size: 0.9rem;
}

.link-more:hover {
    text-decoration: underline;
}
```

---

#### 1.4 Förbättra huvudmetriker med trender
**Fil:** `src/mobile/templates/dashboard.html`
**Rader:** 92-119

**Action:** Lägg till trendpilar och jämförelser

**Nuvarande:**
```html
<div class="metric-card highlight">
    <div class="metric-icon">⚡</div>
    <div class="metric-value" id="cop">-</div>
    <div class="metric-label">COP</div>
    <div class="metric-status" id="copStatus"></div>
</div>
```

**Nytt:**
```html
<div class="metric-card highlight">
    <div class="metric-header">
        <span class="metric-icon">⚡</span>
        <span class="metric-trend" id="copTrend"></span>
    </div>
    <div class="metric-value" id="cop">-</div>
    <div class="metric-label">COP</div>
    <div class="metric-comparison" id="copComparison">-</div>
    <div class="metric-status" id="copStatus"></div>
</div>
```

**JavaScript additions:**
```javascript
// In loadDashboard():
// After setting COP value, add trend and comparison
if (data.cop && data.cop_yesterday) {
    const copChange = data.cop - data.cop_yesterday;
    const trendIcon = copChange >= 0 ? '↗' : '↘';
    const trendColor = copChange >= 0 ? 'var(--success-color)' : 'var(--error-color)';

    document.getElementById('copTrend').innerHTML = `<span style="color: ${trendColor}">${trendIcon}</span>`;
    document.getElementById('copComparison').textContent = `${copChange >= 0 ? '+' : ''}${copChange.toFixed(2)} vs igår`;
}
```

**API Changes Needed:**
- Modify `/api/metrics` to include yesterday's values for comparison
- Add fields: `cop_yesterday`, `degree_minutes_yesterday`, etc.

**CSS:**
```css
.metric-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.5rem;
}

.metric-trend {
    font-size: 1.5rem;
    line-height: 1;
}

.metric-comparison {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-top: 0.25rem;
}
```

---

#### 1.5 Förbättra Optimization Score visuellt
**Fil:** `src/mobile/templates/dashboard.html`
**Rader:** 20-32

**Action:** Gör större och mer prominent

**Nuvarande:**
```html
<section class="optimization-banner" id="optimizationBanner">
    <div class="opt-score-container">
        <div class="opt-score-circle" id="optScoreCircle">
            <div class="opt-score-value" id="optScoreValue">-</div>
            <div class="opt-score-label">Poäng</div>
        </div>
        <div class="opt-score-details">
            <div class="opt-score-badge" id="optScoreBadge">-</div>
            <div class="opt-score-subtitle">Systemets övergripande prestanda</div>
        </div>
    </div>
</section>
```

**Nytt:**
```html
<section class="hero-banner" id="optimizationBanner">
    <div class="hero-content">
        <div class="hero-score">
            <div class="score-circle-large" id="optScoreCircle">
                <div class="score-value-large" id="optScoreValue">-</div>
            </div>
        </div>
        <div class="hero-details">
            <div class="hero-grade" id="optScoreBadge">-</div>
            <div class="hero-subtitle">Systemets övergripande prestanda</div>
            <div class="hero-explanation" id="scoreExplanation">-</div>
        </div>
    </div>
</section>
```

**CSS updates:**
```css
.hero-banner {
    background: linear-gradient(135deg, var(--primary-color) 0%, #1e4a6f 100%);
    color: white;
    padding: 2rem 1rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.hero-content {
    display: flex;
    align-items: center;
    gap: 1.5rem;
}

.score-circle-large {
    width: 100px;
    height: 100px;
    border-radius: 50%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: white;
    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
}

.score-value-large {
    font-size: 2.5rem;
    font-weight: 700;
    color: var(--primary-color);
    line-height: 1;
}

.hero-details {
    flex: 1;
}

.hero-grade {
    font-size: 2rem;
    font-weight: 700;
    margin-bottom: 0.25rem;
}

.hero-subtitle {
    font-size: 0.9rem;
    opacity: 0.9;
    margin-bottom: 0.5rem;
}

.hero-explanation {
    font-size: 0.85rem;
    opacity: 0.85;
    font-style: italic;
}
```

**JavaScript additions:**
```javascript
// In updatePerformanceScore():
const explanations = {
    'A+': 'Exceptionell prestanda! Systemet arbetar optimalt.',
    'A': 'Utmärkt prestanda. Fortsätt så här.',
    'B': 'Bra prestanda med potential för förbättringar.',
    'C': 'Acceptabel prestanda men bör optimeras.',
    'D': 'Prestandan bör förbättras. Se AI-rekommendationer.',
    'F': 'Systemet behöver uppmärksamhet. Kontrollera inställningar.'
};

document.getElementById('scoreExplanation').textContent = explanations[data.grade] || '';
```

---

#### 1.6 Förbättra AI-rekommendationer synlighet
**Fil:** `src/mobile/templates/dashboard.html`
**Rader:** 58-62

**Action:** Gör mer prominent och actionable

**Nuvarande:**
```html
<section class="section" id="suggestionsSection" style="display: none;">
    <h2 class="section-title">🤖 AI-rekommendationer</h2>
    <div id="suggestionsList"></div>
</section>
```

**Nytt:**
```html
<section class="ai-suggestions-hero" id="suggestionsSection" style="display: none;">
    <div class="suggestions-header">
        <h2 class="section-title-large">🤖 AI-rekommendationer</h2>
        <span class="suggestions-count" id="suggestionsCount">0</span>
    </div>
    <div id="suggestionsList" class="suggestions-list-hero"></div>
</section>
```

**CSS updates:**
```css
.ai-suggestions-hero {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1.5rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    color: white;
}

.suggestions-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
}

.section-title-large {
    font-size: 1.3rem;
    margin: 0;
    color: white;
}

.suggestions-count {
    background: rgba(255,255,255,0.3);
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-size: 0.9rem;
    font-weight: 600;
}

.suggestions-list-hero .suggestion-card {
    background: white;
    color: var(--text-primary);
    margin-bottom: 1rem;
    padding: 1rem;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

.suggestion-card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.75rem;
}

.suggestion-title {
    font-size: 1.1rem;
    font-weight: 600;
    flex: 1;
}

.suggestion-priority {
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
}

.suggestion-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
}

.btn-apply {
    flex: 1;
    background: var(--success-color);
    color: white;
    border: none;
    padding: 0.75rem;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
}

.btn-dismiss {
    background: #e0e0e0;
    color: var(--text-primary);
    border: none;
    padding: 0.75rem;
    border-radius: 8px;
    cursor: pointer;
}
```

**JavaScript updates in updateSuggestions():**
```javascript
function updateSuggestions(suggestions) {
    const section = document.getElementById('suggestionsSection');
    const list = document.getElementById('suggestionsList');
    const count = document.getElementById('suggestionsCount');

    if (!suggestions || suggestions.length === 0) {
        section.style.display = 'none';
        return;
    }

    count.textContent = suggestions.length;

    const priorityColors = {
        'high': '#f44336',
        'medium': '#ff9800',
        'low': '#4caf50'
    };

    const priorityLabels = {
        'high': 'HÖG',
        'medium': 'MEDEL',
        'low': 'LÅG'
    };

    list.innerHTML = suggestions.map(s => `
        <div class="suggestion-card">
            <div class="suggestion-card-header">
                <div class="suggestion-title">${s.title}</div>
                <span class="suggestion-priority" style="background: ${priorityColors[s.priority]}; color: white;">
                    ${priorityLabels[s.priority]}
                </span>
            </div>
            <p style="margin: 0.5rem 0; font-size: 0.9rem; color: var(--text-secondary);">${s.description}</p>
            <div style="display: flex; gap: 1rem; margin: 0.75rem 0; padding: 0.75rem; background: #f8f9fa; border-radius: 4px;">
                <div style="flex: 1;">
                    <div style="font-size: 0.75rem; color: var(--text-secondary);">COP-förbättring</div>
                    <div style="font-weight: 700; color: var(--success-color); font-size: 1.2rem;">+${s.expected_cop_improvement.toFixed(2)}</div>
                </div>
                <div style="flex: 1;">
                    <div style="font-size: 0.75rem; color: var(--text-secondary);">Besparing/år</div>
                    <div style="font-weight: 700; color: var(--success-color); font-size: 1.2rem;">${s.expected_savings_yearly.toFixed(0)} kr</div>
                </div>
            </div>
            <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.75rem;">
                <strong>💡 Resonemang:</strong> ${s.reasoning}
            </div>
            <div class="suggestion-actions">
                <button class="btn-apply" onclick="applySuggestion('${s.id}')">✓ Tillämpa</button>
                <button class="btn-dismiss" onclick="dismissSuggestion('${s.id}')">✕</button>
            </div>
        </div>
    `).join('');

    section.style.display = 'block';
}
```

---

### API Changes Needed for Phase 1

#### `/api/metrics` endpoint
**Add fields:**
```python
{
    # ... existing fields ...

    # Comparison data (yesterday's values)
    'cop_yesterday': float,
    'degree_minutes_yesterday': float,
    'delta_t_active_yesterday': float,

    # Simplified heating/hot water summary
    'heating_summary': {
        'cop': float,
        'cop_rating': {'badge': str, 'color': str},
        'runtime_hours': float,
        'num_cycles': int
    },
    'hot_water_summary': {
        'cop': float,
        'cop_rating': {'badge': str, 'color': str},
        'runtime_hours': float,
        'num_cycles': int
    }
}
```

#### `/api/performance-score` endpoint
**Add field:**
```python
{
    # ... existing fields ...
    'explanation': str  # Human-readable explanation of score
}
```

#### `/api/optimization-suggestions` endpoint
**Add apply/dismiss endpoints:**
```python
@app.route('/api/optimization-suggestions/<suggestion_id>/apply', methods=['POST'])
def apply_suggestion(suggestion_id):
    # Apply the suggestion
    pass

@app.route('/api/optimization-suggestions/<suggestion_id>/dismiss', methods=['POST'])
def dismiss_suggestion(suggestion_id):
    # Dismiss the suggestion
    pass
```

---

### Files to Create

#### `src/mobile/templates/analysis.html`
New detailed analysis page with:
- Full "Uppvärmning vs Varmvatten" comparison
- Historical COP graphs
- Degree Minutes explained with chart
- Compressor frequency analysis
- Temperature curves

---

### Testing Checklist

- [ ] Dashboard loads without errors
- [ ] Redundant sections removed
- [ ] Climate & Ventilation section works correctly
- [ ] System summary displays correct data
- [ ] Trends and comparisons show correctly
- [ ] Hero banner looks good on mobile and desktop
- [ ] AI suggestions are prominent and actionable
- [ ] Apply/Dismiss buttons work
- [ ] Link to analysis page works
- [ ] All API endpoints return expected data
- [ ] Responsive design works on small screens

---

### Estimated Impact

**Improvements:**
- ✅ Reduced scrolling by ~40%
- ✅ Removed 2 redundant sections
- ✅ Clearer visual hierarchy
- ✅ Actionable AI recommendations
- ✅ Better use of space

**User Benefits:**
- < 5 seconds to understand system status
- < 10 seconds to see what action to take
- More intuitive navigation
- Less cognitive load

---

## Next: Phase 2 & 3

After Phase 1 is complete and tested:

**Phase 2:** AI Agent page simplification
- Remove gradient backgrounds
- Add tabs for different views
- Make schedule dynamic
- Add undo functionality

**Phase 3:** Create analysis.html and history.html
- Detailed metrics page
- Timeline-based history view
- Before/after comparisons
