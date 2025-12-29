with open('agent_v2_missing_example.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "**IMPORTANT:** Respond ONLY with a valid JSON object." in line:
        # Insert example before this line
        example = """
Example JSON Response:
{
  "action": "adjust",
  "parameter": "gm_account.mode",
  "suggested_value": "NORMAL",
  "reasoning": "Standard operation.",
  "confidence": 1.0,
  "expected_impact": "System continues as planned."
}
"""
        lines.insert(i, example)
        break

with open('agent_v2_final_fixed.py', 'w') as f:
    f.writelines(lines)