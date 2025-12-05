# Project Review & Technical Debt Assessment
**Target Audience:** Claude Code (Agentic Developer)
**Date:** 2025-12-03
**Status:** V2 Migration in Progress

## Executive Summary
The `nibe_autotuner` project is transitioning from a V1 proof-of-concept to a V2 production-ready system. The core infrastructure (database, data logger) is solid, but the application layer suffers from low test coverage, hardcoded configurations, and architectural rigidity in the `HeatPumpAnalyzer` class.

The recent introduction of `autonomous_ai_agent_v2.py` provides a robust blueprint for safe, AI-driven control, but it is not yet fully integrated as the default driver.

## Critical Findings

### 1. AI Agent Architecture (V1 vs V2)
*   **Current State:** `autonomous_ai_agent.py` (V1) relies entirely on LLM prompt compliance for safety. `autonomous_ai_agent_v2.py` (V2) introduces deterministic code-level guardrails (`_is_decision_safe`).
*   **Risk:** V1 is dangerous if the LLM hallucinates. V2 is safe but currently requires manual invocation.
*   **Action:** V2 must supersede V1. The JSON parsing in V2 is still slightly brittle and should be standardized.

### 2. Testing Gap
*   **Current State:** Test coverage is negligible. `tests/test_safety_guardrails_v2.py` is the *only* modern, effective test suite. The `src/test_*.py` files are manual scripts, not automated tests.
*   **Risk:** High risk of regression during refactoring.
*   **Action:** Adopt `pytest` globally. Move manual scripts to `scripts/manual/`.

### 3. Analyzer Rigidity
*   **Current State:** `src/analyzer.py` hardcodes `datetime.now()` in its metric calculations.
*   **Impact:** This makes accurate backtesting impossible without "mocking the universe" (which `src/backtester.py` currently hacks around).
*   **Action:** Refactor `analyzer.py` methods to accept an optional `reference_time` argument.

### 4. Visualization & UI
*   **Current State:** `src/visualizer.py` generates static PNGs using Matplotlib (heavy). `src/mobile/templates/visualizations_interactive.html` (new) uses Chart.js (lightweight, client-side).
*   **Action:** Deprecate the server-side image generation for the mobile app context. Keep it only for email reports/logging if needed.

### 5. Missing Configuration
*   **Finding:** `config/parameters.json` is referenced in documentation but missing from the filesystem. Parameter IDs are hardcoded in multiple files (`47007`, `47011`).
*   **Action:** Create a central `ParameterRegistry` or restore the JSON config.

## Task List for Claude Code

Use the following prioritized list to guide your development sessions.

### Phase 1: Stabilization & Safety (Immediate)
1.  **Verify V2 Agent:** Run `pytest tests/test_safety_guardrails_v2.py`. If green, proceed.
2.  **Switch to V2:** Update `scripts/run_ai_agent.sh` to execute `src/autonomous_ai_agent_v2.py` instead of the V1 script.
3.  **Hardening:** Refactor `autonomous_ai_agent_v2.py`:
    *   Replace the custom `_parse_json_response` with a robust Pydantic parser or a dedicated JSON repair library.
    *   Move parameter ID maps (e.g., `{'heating_curve': '47007'}`) to a constant at the top of the file or a config class.

### Phase 2: Core Refactoring (High Value)
4.  **Refactor Analyzer:**
    *   Modify `HeatPumpAnalyzer.calculate_metrics` signature: `def calculate_metrics(self, hours_back=24, end_time=None):`.
    *   If `end_time` is None, default to `datetime.now()`.
    *   Update all SQL queries inside to use `end_time` instead of `now`.
5.  **Fix Backtester:** Update `src/backtester.py` to use the new `end_time` argument in the analyzer, removing the need for the `BacktestAnalyzer` subclass hacks.

### Phase 3: Test Coverage (Long Term)
6.  **API Tests:** Create `tests/test_api_server.py` using `TestClient` from FastAPI.
    *   Test `/api/status` and `/api/recommendations`.
7.  **Optimizer Tests:** Create unit tests for `src/optimizer.py` (pure logic tests, no DB required).

### Phase 4: Cleanup
8.  **File Organization:**
    *   `mv src/test_*.py scripts/manual_tests/`
    *   Ensure `requirements.txt` is pruned of unused libraries (e.g., check if `matplotlib` is still needed if we move to Chart.js).

## Integration Note for Gemini 3.0
When facing complex data analysis tasks (e.g., "Why did COP drop last Tuesday?"), export the relevant DB segment to CSV and ask Gemini 3.0 to analyze it. Use the resulting insights to create new rules for the `_is_decision_safe` method in the V2 agent.
