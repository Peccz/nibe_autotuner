with open('agent_v2_to_update_dm.py', 'r') as f:
    lines = f.readlines()

# Add DM_WRITE to prompt section
found_prompt_section = False
for i, line in enumerate(lines):
    if "Adjustable Parameters:" in line:
        found_prompt_section = True
    if found_prompt_section and "- Heating Curve (47007):" in line:
        lines.insert(i + 1, f"        prompt_parts.append(f\"- Degree Minutes ({{self.analyzer.PARAM_DM_WRITE}}): Current={{metrics.degree_minutes}}, Range=[-1500 to 1500], Step=10 (WRITEABLE - allows direct compressor control)\")\n")
        break

# Add DM_WRITE to _apply_decision
found_apply_decision = False
for i, line in enumerate(lines):
    if "def _apply_decision(self, decision: AIDecision) -> bool:" in line:
        found_apply_decision = True
    if found_apply_decision and 'elif decision.parameter_name == "Heating Curve":' in line:
        lines.insert(i + 1, '            elif decision.parameter_name == "Degree Minutes":\n')
        lines.insert(i + 2, '                parameter_id = self.analyzer.PARAM_DM_WRITE\n')
        break

with open('agent_v2_dm_optimized.py', 'w') as f:
    f.writelines(lines)
