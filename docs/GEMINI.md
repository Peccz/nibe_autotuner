# Nibe Autotuner

## Project Overview

**Nibe Autotuner** is an AI-powered optimization system for Nibe heat pumps (specifically F730 models). It bridges the gap between basic manufacturer settings and optimal efficiency by continuously analyzing operational data and applying intelligent adjustments.

**Key Capabilities:**
*   **Data Collection:** Logs 102+ heat pump parameters every 5 minutes via the myUplink API.
*   **AI Analysis:** Utilizes **Google Gemini 2.5 Flash** (for real-time chat/analysis) and **Claude 3.5 Sonnet** (for autonomous decision-making) to evaluate performance.
*   **Optimization:** Automatically adjusts heating curves and offsets to maximize COP (Coefficient of Performance) while maintaining comfort.
*   **Visualization:** Provides a web dashboard and PWA (Progressive Web App) for monitoring metrics like Degree Minutes, Delta T, and COP.
*   **Dual-Mode AI:**
    *   **Gemini:** Fast, cost-effective analysis and user interaction.
    *   **Claude:** Deep reasoning for autonomous control and complex scenarios.

## Directory Structure

*   **`src/`**: Core Python source code.
    *   `api_server.py`: FastAPI backend for the web interface and API.
    *   `data_logger.py`: Service that fetches data from myUplink.
    *   `gemini_agent.py`: Implementation of the Gemini AI integration.
    *   `autonomous_ai_agent.py`: Implementation of the Claude-based autonomous agent.
    *   `analyzer.py` & `optimizer.py`: Logic for performance analysis and rule-based optimization.
    *   `mobile/`: Flask-based mobile web application.
*   **`data/`**: Stores the SQLite database (`nibe_autotuner.db`) and generated plots.
*   **`docs/`**: Documentation for setup, baselines, and architecture.
*   **`scripts/`**: Shell scripts for automation, deployment, and cron jobs.
*   **`config/`**: Configuration files (e.g., parameter definitions).

## Key Components & Workflows

### 1. Data Collection
The `src/data_logger.py` script runs continuously (or via cron), fetching data from the myUplink API and storing it in `data/nibe_autotuner.db`.

### 2. Analysis & Optimization
*   **Rule-Based:** `src/auto_optimizer.py` applies standard engineering rules (e.g., "If cold & high COP -> increase curve").
*   **AI-Based:** `src/autonomous_ai_agent.py` and `src/gemini_agent.py` use LLMs to interpret complex patterns (weather forecasts + historical trends) to make nuanced decisions.

### 3. User Interface
*   **Web Dashboard:** Accessed via the API server (default port 8000) or Mobile App (default port 5000/8502).
*   **CLI:** Tools like `src/analyzer.py` can be run directly in the terminal for instant feedback.

## Development & Usage

### Prerequisites
*   Python 3.8+
*   A valid `.env` file with myUplink and AI API credentials.

### Common Commands

**Installation:**
```bash
# Create venv and install dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Running Services:**
```bash
# Start Data Logger (Manual)
python src/data_logger.py --interval 300

# Start REST API
python src/api_server.py

# Start Mobile App
python src/mobile_app.py
```

**AI & Analysis:**
```bash
# Run Gemini Analysis (Interactive Chat)
# (Via Web UI or API endpoint)

# Run Autonomous Agent (Dry Run - Safe Mode)
PYTHONPATH=./src python src/autonomous_ai_agent.py

# Generate Visualizations
python src/visualizer.py
```

### Systemd Services
The project is designed to run as background services on Linux (e.g., Raspberry Pi):
*   `nibe-autotuner.service`: Main data logging and backend.
*   `nibe-mobile.service`: Frontend web application.

## Configuration
Configuration is primarily handled via environment variables in `.env`:
*   `MYUPLINK_*`: API credentials for the heat pump.
*   `GOOGLE_API_KEY`: For Gemini AI features.
*   `ANTHROPIC_API_KEY`: For Claude AI features.
