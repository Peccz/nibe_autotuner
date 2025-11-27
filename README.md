# Nibe Autotuner

AI-powered optimization system for Nibe heat pumps. Collects operational data via myUplink API, analyzes performance, and generates intelligent recommendations to improve efficiency and comfort.

## Features

- **Continuous Data Logging**: Automatically collects 102 heat pump parameters every 5 minutes
- **Efficiency Analysis**: Calculates COP, degree minutes, and other key performance indicators
- **Smart Recommendations**: AI-driven suggestions for optimizing heating curve, offset, and other settings
- **Scientific Foundation**: Grounded in academic research, manufacturer specifications, and industry best practices
  - [Scientific Baseline](docs/SCIENTIFIC_BASELINE.md) - Academic research citations
  - [Nibe F730 Technical Baseline](docs/NIBE_F730_BASELINE.md) - Model-specific specifications
- **Data Visualization**: Beautiful charts showing temperatures, efficiency trends, and COP over time
- **CSV Import/Export**: Backfill historical data or export for analysis
- **REST API**: Complete API for mobile app integration
- **Systemd Integration**: Runs as background service with automatic restart

## Project Status

**Backend**: ✅ Complete and functional
- Data collection service
- Analysis engine
- Recommendation system
- Visualization tools
- REST API

**Android App**: 🚧 Not yet started (backend ready for integration)

## Quick Start

### 1. Prerequisites

```bash
# Python 3.8+
python --version

# Git
git --version
```

### 2. Installation

```bash
# Clone repository
git clone https://github.com/Peccz/nibe_autotuner.git
cd nibe_autotuner

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Linux/Mac
# Or: venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

1. Register at [myUplink Developer Portal](https://dev.myuplink.com/)
2. Create an OAuth2 application
3. Copy `.env.example` to `.env`
4. Add your credentials:

```bash
MYUPLINK_CLIENT_ID=your_client_id_here
MYUPLINK_CLIENT_SECRET=your_client_secret_here
MYUPLINK_CALLBACK_URL=http://localhost:8080/oauth/callback
```

### 4. Authentication

```bash
# Run authentication flow (opens browser)
python src/auth.py

# Follow the authorization steps
# Tokens will be saved to ~/.myuplink_tokens.json
```

### 5. Start Data Collection

**Option A: Run manually**
```bash
python src/data_logger.py --interval 300  # 5 minutes
```

**Option B: Install as systemd service (Linux)**
```bash
./install_service.sh

# Manage service
sudo systemctl start nibe-autotuner
sudo systemctl stop nibe-autotuner
sudo systemctl status nibe-autotuner
journalctl -u nibe-autotuner -f  # View logs
```

## Usage

### Analyze Performance

```bash
# Run full analysis
python src/analyzer.py

# Output:
# - Current system metrics
# - Efficiency calculations
# - Optimization recommendations
```

### Generate Visualizations

```bash
# Create all plots
python src/visualizer.py

# Generated files:
# - data/temperature_plot.png
# - data/efficiency_plot.png
# - data/cop_plot.png
# - data/dashboard.png
```

### Import Historical Data

```bash
# Import CSV from myUplink web export
python src/csv_importer.py import data/myuplink_export.csv

# Export current data
python src/csv_importer.py export data/backup.csv
```

### Start API Server

```bash
# Start REST API server
python src/api_server.py

# API Documentation: http://localhost:8000/docs
# Base URL: http://localhost:8000/api
```

## API Endpoints

### System Status
```bash
GET /api/status
```
Returns current heat pump status with all key parameters.

### Performance Metrics
```bash
GET /api/metrics?hours_back=24
```
Calculate efficiency metrics for specified time period.

### Recommendations
```bash
GET /api/recommendations?hours_back=24&min_confidence=0.6
```
Get AI-generated optimization recommendations.

### Parameter History
```bash
GET /api/history/40004?hours_back=24
```
Get historical readings for specific parameter (e.g., 40004 = outdoor temp).

### Visualizations
```bash
GET /api/visualizations/dashboard?hours_back=24
GET /api/visualizations/temperature?hours_back=24
GET /api/visualizations/efficiency?hours_back=24
GET /api/visualizations/cop?hours_back=168
```
Generate and return visualization plots.

### Record Parameter Change
```bash
POST /api/parameter-change
{
  "parameter_id": "47007",
  "old_value": 7.0,
  "new_value": 7.5,
  "reason": "Applied recommendation to improve degree minutes"
}
```

### Database Statistics
```bash
GET /api/database-stats
```

## Key Parameters

| Parameter ID | Name | Purpose |
|--------------|------|---------|
| 40004 | Outdoor Temperature | Input for heating curve calculation |
| 40008 | Supply Temperature | Water temperature to radiators |
| 40012 | Return Temperature | Water temperature from radiators |
| 40033 | Indoor Temperature | Room temperature measurement |
| 40940 | Degree Minutes | Heating balance indicator (target: -200) |
| 41778 | Compressor Frequency | Current compressor speed (Hz) |
| 47007 | Heating Curve | Main optimization parameter (0-15) |
| 47011 | Curve Offset | Temperature offset adjustment (-10 to +10) |
| 47206 | DM Heating Start | Degree minutes threshold to start heating |
| 48072 | DM Heating Stop | Degree minutes threshold to stop heating |

## Understanding Degree Minutes (DM)

Degree Minutes is the key metric for heat pump optimization:

- **Target: -200 DM** - Optimal balance between comfort and efficiency
- **< -300 DM** - System is too cold, increase heating curve
- **> -100 DM** - System is too warm, decrease heating curve
- **-300 to -100 DM** - Comfort zone

## Database Schema

**SQLite database**: `data/nibe_autotuner.db`

Tables:
- `systems` - Heat pump systems
- `devices` - Physical devices
- `parameters` - Parameter catalog (102 parameters)
- `parameter_readings` - Time-series data (main table)
- `parameter_changes` - Manual changes tracking
- `recommendations` - AI-generated suggestions
- `recommendation_results` - Effectiveness tracking

## Data Storage

- **Readings per day**: ~288 (every 5 minutes)
- **Data points per day**: ~29,376 (102 parameters × 288)
- **Database growth**: ~1.5 MB/day, ~45 MB/month, ~550 MB/year

## Project Structure

```
nibe_autotuner/
├── src/
│   ├── auth.py              # OAuth2 authentication
│   ├── api_client.py        # myUplink API client
│   ├── models.py            # Database models
│   ├── data_logger.py       # Continuous data collection
│   ├── analyzer.py          # Performance analysis & recommendations
│   ├── visualizer.py        # Data visualization
│   ├── csv_importer.py      # CSV import/export
│   ├── api_server.py        # FastAPI REST server
│   └── test_*.py            # Test scripts
├── data/
│   └── nibe_autotuner.db    # SQLite database
├── logs/
│   ├── data_logger.log      # Service logs
│   └── data_logger_error.log
├── docs/
│   ├── DATABASE_DESIGN.md       # Database schema documentation
│   ├── SCIENTIFIC_BASELINE.md   # Academic research references
│   └── NIBE_F730_BASELINE.md    # Nibe F730 technical specifications
├── config/
│   └── parameters.json      # Parameter definitions
├── nibe-autotuner.service   # Systemd service file
├── install_service.sh       # Service installation script
├── uninstall_service.sh     # Service removal script
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variables template
└── README.md                # This file
```

## Development Roadmap

### Phase 1: Backend (✅ Complete)
- [x] myUplink API integration
- [x] Data collection service
- [x] Database design and implementation
- [x] Analysis engine
- [x] Recommendation system
- [x] Visualization tools
- [x] CSV import/export
- [x] REST API
- [x] Systemd service

### Phase 2: Android App (🚧 Planned)
- [ ] Design UI/UX mockups
- [ ] Implement main dashboard
- [ ] Display current system status
- [ ] Show recommendations
- [ ] View historical charts
- [ ] Record parameter changes
- [ ] Push notifications for recommendations
- [ ] Settings and configuration

### Phase 3: ML Enhancement (🔮 Future)
- [ ] Train ML model on collected data
- [ ] Predict optimal settings based on weather forecasts
- [ ] Learn from user feedback
- [ ] Automated A/B testing of settings
- [ ] Energy cost optimization

### Phase 4: Advanced Features (🔮 Future)
- [ ] Multi-device support
- [ ] Cloud sync
- [ ] Community insights (anonymized)
- [ ] Integration with home automation
- [ ] Voice assistant integration

## Semi-Automated Mode

**Important**: The myUplink API does not provide write access for external applications. This means:

- ✅ App can READ all parameters
- ✅ App can ANALYZE and RECOMMEND
- ❌ App cannot WRITE parameters automatically

**Workflow**:
1. App generates recommendations
2. User reviews recommendations in app
3. User manually applies changes via Nibe heat pump panel
4. User confirms changes in app for tracking
5. App monitors results and learns

This semi-automated approach ensures safety while still providing intelligent optimization guidance.

## Troubleshooting

### Authentication Issues

```bash
# Delete old tokens and re-authenticate
rm ~/.myuplink_tokens.json
python src/auth.py
```

### Database Issues

```bash
# Check database status
python -c "from src.test_analyzer import check_data_availability; check_data_availability()"

# Rebuild database (WARNING: deletes all data)
rm data/nibe_autotuner.db
python src/data_logger.py --interval 300
```

### Service Issues

```bash
# View service logs
journalctl -u nibe-autotuner -f

# Restart service
sudo systemctl restart nibe-autotuner

# Check service status
sudo systemctl status nibe-autotuner
```

### API Issues

```bash
# Test if API is responding
curl http://localhost:8000/api/database-stats

# View API documentation
# Open http://localhost:8000/docs in browser
```

## Contributing

This is a personal project, but suggestions and feedback are welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - See LICENSE file for details

## Acknowledgments

- **Nibe** - For creating excellent heat pumps
- **myUplink** - For providing API access
- **MarshFlattsFarm** - For myUplink API documentation
- **Claude AI** - For development assistance

## Contact

Project Link: [https://github.com/Peccz/nibe_autotuner](https://github.com/Peccz/nibe_autotuner)

## Disclaimer

This project is not affiliated with, endorsed by, or connected to Nibe, myUplink, or any related companies. Use at your own risk. Always verify recommendations before making changes to your heat pump settings.
