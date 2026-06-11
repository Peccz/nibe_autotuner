with open('agent_v2_clean_base.py', 'r') as f: # Use the downloaded clean base
    lines = f.readlines()

# 1. Add SmartPlanner and GMAccount imports
for i, line in enumerate(lines):
    if "from integrations.autonomous_ai_agent import AIDecision, AutonomousAIAgent" in line:
        lines.insert(i, "from services.smart_planner import SmartPlanner\n")
        lines.insert(i + 1, "from data.models import GMAccount, PlannedHeatingSchedule # Added for GM Bank integration\n")
        break

# 2. Instantiate SmartPlanner in __init__
for i, line in enumerate(lines):
    if "self.learning_service = LearningService(self.db, self.analyzer)" in line:
        lines.insert(i + 1, "        self.planner = SmartPlanner()\n")
        break

# 3. Modify analyze_and_decide for new passive role
start_analyze_decide_idx = -1
for i, line in enumerate(lines):
    if "def analyze_and_decide(self, hours_back: int = 72, dry_run: bool = True, mode: str = \"tactical\") -> AIDecision:" in line:
        start_analyze_decide_idx = i
        break

if start_analyze_decide_idx != -1:
    # Find the block from "Metrics & Context" to "return decision"
    # This block represents the old decision-making. We replace it.
    replace_start_marker = "        # Metrics & Context"
    replace_end_marker = "            return decision" # This is the end of the try block

    replace_start_idx = -1
    replace_end_idx = -1

    for i in range(start_analyze_decide_idx, len(lines)):
        if replace_start_marker in lines[i]:
            replace_start_idx = i
        if replace_end_marker in lines[i]:
            replace_end_idx = i + 1 # Include the return decision line
            break
            
    if replace_start_idx != -1 and replace_end_idx != -1:
        del lines[replace_start_idx:replace_end_idx]

        new_analyze_decide_logic = """
        # Call the SmartPlanner to generate the 24h heating schedule
        # The AI's primary role in this phase is to initiate the planning.
        try:
            self.planner.plan_next_24h()
            logger.info(\"✓ SmartPlanner generated a new 24h heating plan.\")
        except Exception as e:
            logger.error(f\"❌ SmartPlanner failed to generate plan: {e}\")
            import traceback
            traceback.print_exc()
            return AIDecision('hold', None, None, None, f\"Planner error: {str(e)}\", 0.0, \"None\")

        # Get GM Account state
        gm_account = self.db.query(GMAccount).first()
        current_gm_balance = gm_account.balance if gm_account else 0.0
        gm_mode = gm_account.mode if gm_account else 'NORMAL'
        
        # AI's new simplified decision for this phase: just report plan generated, and mode.
        decision = AIDecision(
            action='hold',
            parameter=None,
            current_value=None,
            suggested_value=None,
            reasoning=f\"SmartPlanner generated a 24h heating plan. Current GM Bank Mode: '{gm_mode}', Balance: {current_gm_balance:.1f}.\",
            confidence=1.0,
            expected_impact=\"System will follow the planned schedule.\"
        )
        
        # Log decision (no actual application yet, as GMController handles pump)
        self._log_decision(decision, applied=False) 
        return decision
"""
        lines.insert(replace_start_idx, new_analyze_decide_logic)

# --- 4. Simplify _create_optimized_prompt (it's no longer used for strategy) ---
# We will just make it a dummy, as analyze_and_decide no longer calls it for its core logic
for i, line in enumerate(lines):
    if "def _create_optimized_prompt(self, context: str, min_temp: float, target_min: float, target_max: float, mode: str = \"tactical\", metrics=None, device=None) -> str:" in line:
        # Delete everything until "return prompt"
        prompt_def_idx = i
        prompt_return_idx = -1
        for j in range(prompt_def_idx, len(lines)):
            if "return prompt" in lines[j]:
                prompt_return_idx = j
                break
        
        if prompt_def_idx != -1 and prompt_return_idx != -1:
            del lines[prompt_def_idx+1:prompt_return_idx]
            lines.insert(prompt_def_idx+1, '        return "AI Prompt is no longer used for direct strategy in this phase."\n')
            
            # Remove calls to _create_optimized_prompt from analyze_and_decide (already done by deleting block)


# --- 5. Update _apply_decision for the new limited role ---
# The AI's apply decision is now only for GMAccount.mode, not Nibe parameters directly
for i, line in enumerate(lines):
    if "def _apply_decision(self, decision: AIDecision) -> bool:" in line:
        # Delete old implementation
        apply_start_idx = i
        apply_end_idx = -1
        for j in range(apply_start_idx, len(lines)):
            # This is fragile, assuming 'return False' is the last line of the method before a new def or class.
            if ("return False" in lines[j] or "return True" in lines[j]) and j > apply_start_idx and ("except Exception" in lines[j-1] or "logger.error" in lines[j-1]):
                 apply_end_idx = j + 1
                 break
        
        if apply_start_idx != -1 and apply_end_idx != -1:
            del lines[apply_start_idx+1:apply_end_idx]

            new_apply_logic = """        # AI's apply decision is now only for GMAccount.mode
        if decision.parameter == 'gm_account.mode':
            try:
                gm_account = self.db.query(GMAccount).first()
                if not gm_account:
                    gm_account = GMAccount(balance=0.0, mode=decision.new_value)
                    self.db.add(gm_account)
                else:
                    gm_account.mode = decision.new_value
                self.db.commit()
                logger.info(f"GM Account Mode set to: {decision.new_value} by AI.")
                return True
            except Exception as e:
                logger.error(f"Failed to set GM Account Mode: {e}")
                return False
        else:
            logger.warning(f"AI attempted to apply unknown parameter: {decision.parameter}. No direct Nibe control in this phase.")
            return False
"""
            lines.insert(apply_start_idx + 1, new_apply_logic)
        break


# --- 6. Remove ParameterConfig class and related unused imports ---
# Find 'class ParameterConfig:'
for i, line in enumerate(lines):
    if "class ParameterConfig:" in line:
        # Delete the whole class definition
        class_start_idx = i
        class_end_idx = -1
        for j in range(class_start_idx, len(lines)):
            if (lines[j].strip() == "" or not lines[j].startswith(" ")) and j > class_start_idx:
                class_end_idx = j
                break
        if class_start_idx != -1 and class_end_idx != -1:
            del lines[class_start_idx:class_end_idx]
            break

# Remove calls to ParameterConfig (param_id = ParameterConfig.PARAMETER_IDS.get)
# And related old logic.
for i, line in enumerate(lines):
    if "param_id = ParameterConfig.PARAMETER_IDS.get(decision.parameter)" in line:
        lines[i] = "            # No direct Nibe parameter ID needed for gm_account.mode as AI only sets mode\n"
    if "if not param_id:" in line: # This check is now obsolete
        lines[i] = "            # Obsolete check for param_id, AI only sets gm_account.mode\n"


with open('agent_v2_passive_planner.py', 'w') as f:
    f.writelines(lines)
