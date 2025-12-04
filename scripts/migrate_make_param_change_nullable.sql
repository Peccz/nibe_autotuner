-- Migration: Make parameter_change_id nullable in ab_test_results
-- This allows ABTestResult to be used for PlannedTests (scientific tests)
-- which are not associated with a specific ParameterChange

BEGIN TRANSACTION;

-- Create new table with nullable parameter_change_id
CREATE TABLE ab_test_results_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parameter_change_id INTEGER,  -- Now nullable (was NOT NULL)
    before_start DATETIME NOT NULL,
    before_end DATETIME NOT NULL,
    after_start DATETIME NOT NULL,
    after_end DATETIME NOT NULL,
    cop_before FLOAT,
    cop_after FLOAT,
    cop_change_percent FLOAT,
    delta_t_before FLOAT,
    delta_t_after FLOAT,
    delta_t_change_percent FLOAT,
    indoor_temp_before FLOAT,
    indoor_temp_after FLOAT,
    indoor_temp_change FLOAT,
    outdoor_temp_before FLOAT,
    outdoor_temp_after FLOAT,
    compressor_freq_before FLOAT,
    compressor_freq_after FLOAT,
    compressor_cycles_before INTEGER,
    compressor_cycles_after INTEGER,
    runtime_hours_before FLOAT,
    runtime_hours_after FLOAT,
    cost_per_day_before FLOAT,
    cost_per_day_after FLOAT,
    cost_savings_per_day FLOAT,
    cost_savings_per_year FLOAT,
    success_score FLOAT,
    recommendation TEXT,
    created_at DATETIME,
    FOREIGN KEY (parameter_change_id) REFERENCES parameter_changes(id)
);

-- Copy existing data
INSERT INTO ab_test_results_new
SELECT * FROM ab_test_results;

-- Drop old table
DROP TABLE ab_test_results;

-- Rename new table
ALTER TABLE ab_test_results_new RENAME TO ab_test_results;

COMMIT;
