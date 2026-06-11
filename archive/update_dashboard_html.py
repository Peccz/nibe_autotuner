{% extends "base.html" %}
{% set active_page = 'dashboard' %}

{% block content %}
<div class="container-fluid mt-3">
    <!-- Status Cards -->
    <div class="row g-3 mb-4">
        <!-- Indoor Temp -->
        <div class="col-6 col-md-3">
            <div class="card bg-dark text-white h-100 border-0 shadow-sm">
                <div class="card-body text-center p-3">
                    <h6 class="card-title text-muted mb-1"><i class="bi bi-thermometer-half"></i> Inne</h6>
                    <h2 class="display-6 fw-bold mb-0" id="indoor-temp">--</h2>
                    <small class="text-success" id="indoor-target">Mål: 21.0°C</small>
                </div>
            </div>
        </div>
        
        <!-- GM Bank (NEW) -->
        <div class="col-6 col-md-3">
            <div class="card bg-dark text-white h-100 border-0 shadow-sm">
                <div class="card-body text-center p-3">
                    <h6 class="card-title text-muted mb-1"><i class="bi bi-bank"></i> GM Bank</h6>
                    <h2 class="display-6 fw-bold mb-0" id="gm-balance">--</h2>
                    <small id="gm-mode-badge" class="badge bg-secondary">--</small>
                </div>
            </div>
        </div>

        <!-- Price -->
        <div class="col-6 col-md-3">
            <div class="card bg-dark text-white h-100 border-0 shadow-sm">
                <div class="card-body text-center p-3">
                    <h6 class="card-title text-muted mb-1"><i class="bi bi-lightning-charge"></i> Elpris</h6>
                    <h2 class="display-6 fw-bold mb-0" id="current-price">--</h2>
                    <small class="text-muted">SEK/kWh</small>
                </div>
            </div>
        </div>

        <!-- Outdoor -->
        <div class="col-6 col-md-3">
            <div class="card bg-dark text-white h-100 border-0 shadow-sm">
                <div class="card-body text-center p-3">
                    <h6 class="card-title text-muted mb-1"><i class="bi bi-cloud-sun"></i> Ute</h6>
                    <h2 class="display-6 fw-bold mb-0" id="outdoor-temp">--</h2>
                    <small class="text-muted" id="weather-desc">--</small>
                </div>
            </div>
        </div>
    </div>

    <!-- Heating Plan (NEW) -->
    <div class="card bg-dark text-white mb-4 shadow-sm">
        <div class="card-header border-secondary d-flex justify-content-between align-items-center">
            <span><i class="bi bi-calendar-check"></i> Värmeplan (24h)</span>
            <span class="badge bg-primary">SmartPlanner</span>
        </div>
        <div class="card-body p-0">
            <div class="table-responsive">
                <table class="table table-dark table-sm mb-0" style="font-size: 0.9rem;">
                    <thead>
                        <tr>
                            <th>Tid</th>
                            <th>Aktion</th>
                            <th>Pris</th>
                            <th>Ute</th>
                            <th>Inne (Sim)</th>
                        </tr>
                    </thead>
                    <tbody id="schedule-table-body">
                        <tr><td colspan="5" class="text-center text-muted py-3">Laddar plan...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Recent Activity Log -->
    <div class="card bg-dark text-white mb-4 shadow-sm">
        <div class="card-header border-secondary">
            <span><i class="bi bi-activity"></i> Logg</span>
        </div>
        <div class="list-group list-group-flush list-group-dark" id="activity-log">
            <!-- Items injected by JS -->
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
    async function updateDashboard() {
        try {
            // 1. Basic Metrics
            const mRes = await fetch('/api/metrics');
            const metrics = await mRes.json();
            
            document.getElementById('indoor-temp').innerText = metrics.avg_indoor_temp ? metrics.avg_indoor_temp.toFixed(1) : '--';
            document.getElementById('outdoor-temp').innerText = metrics.avg_outdoor_temp ? metrics.avg_outdoor_temp.toFixed(1) : '--';
            
            // 2. GM Status (NEW)
            const gmRes = await fetch('/api/gm-status');
            const gmData = await gmRes.json();
            document.getElementById('gm-balance').innerText = gmData.balance !== undefined ? Math.round(gmData.balance) : '--';
            
            const badge = document.getElementById('gm-mode-badge');
            badge.innerText = gmData.mode || 'UNKNOWN';
            badge.className = 'badge ' + (gmData.mode === 'SPEND' ? 'bg-success' : gmData.mode === 'SAVE' ? 'bg-warning text-dark' : 'bg-secondary');

            // 3. Price
            const pRes = await fetch('/api/price/now');
            const price = await pRes.json();
            document.getElementById('current-price').innerText = price.price ? price.price.toFixed(2) : '--';

            // 4. Schedule (NEW)
            const sRes = await fetch('/api/schedule');
            const schedule = await sRes.json();
            const tbody = document.getElementById('schedule-table-body');
            tbody.innerHTML = '';
            
            if (schedule.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">Ingen plan tillgänglig</td></tr>';
            } else {
                schedule.slice(0, 12).forEach(row => { // Show next 12 hours
                    const tr = document.createElement('tr');
                    const time = new Date(row.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                    
                    let actionColor = 'text-muted';
                    if (row.action === 'RUN' || row.action === 'MUST_RUN') actionColor = 'text-success fw-bold';
                    if (row.action === 'REST' || row.action === 'MUST_REST') actionColor = 'text-warning';

                    tr.innerHTML = `
                        <td>${time}</td>
                        <td class="${actionColor}">${row.action}</td>
                        <td>${row.price.toFixed(2)}</td>
                        <td>${row.outdoor_temp.toFixed(1)}</td>
                        <td>${row.indoor_sim.toFixed(1)}</td>
                    `;
                    tbody.appendChild(tr);
                });
            }

            // 5. Activity Log (Standard)
            const logRes = await fetch('/api/ai-agent/latest-decision');
            const log = await logRes.json();
            const logContainer = document.getElementById('activity-log');
            logContainer.innerHTML = '';
            
            if(log) {
                const item = document.createElement('div');
                item.className = 'list-group-item bg-dark text-white border-secondary';
                const time = new Date(log.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                item.innerHTML = `
                    <div class="d-flex w-100 justify-content-between">
                        <small class="text-muted">${time}</small>
                        <small class="badge bg-secondary">${log.action}</small>
                    </div>
                    <p class="mb-1 small">${log.reasoning || 'No details'}</p>
                `;
                logContainer.appendChild(item);
            }

        } catch (e) {
            console.error("Dashboard update failed:", e);
        }
    }

    // Refresh every 60s
    updateDashboard();
    setInterval(updateDashboard, 60000);
</script>
{% endblock %}
