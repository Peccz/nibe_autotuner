from datetime import datetime, timedelta
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from data.models import PlannedTest, Device, Parameter, ParameterChange

class TestProposer:
    def __init__(self, db: Session):
        self.db = db
        self.baseline_curve = 7.0
        self.baseline_offset = -3.0
        
        # Test configurations
        # Type: 'api' (automatic) or 'manual' (requires user action)
        self.variations = [
            # --- API TESTS (Automatic) ---
            
            # Room Sensor Influence (47394) - HIGH PRIORITY, IMMEDIATE ACTION
            {"param_id": "47394", "value": 2.0, "type": "api", "priority": "high", "reason": "Aktivera rumsgivare (Faktor 2)", "expected": "Jämnare innetemperatur, kompenserar för sol/vind", "instruction": "Rumsgivare (BT50) är nu aktiverad med påverkan 2. Systemet kommer att anpassa värmen baserat på din innetemperatur."},

            # Offset variations (47011) - Finetuning comfort/economy
            {"param_id": "47011", "value": -4.0, "type": "api", "priority": "medium", "reason": "Sänkt kurvjustering (Sparläge)", "expected": "Högre COP, något lägre inne", "instruction": None},
            {"param_id": "47011", "value": -2.0, "type": "api", "priority": "medium", "reason": "Höjd kurvjustering (Komfort)", "expected": "Bättre komfort, något lägre COP", "instruction": None},
            
            # Curve variations (47007) - Handling weather changes
            {"param_id": "47007", "value": 6.0, "type": "api", "priority": "low", "reason": "Flackare kurva", "expected": "Jämnare värme vid omslag i väder", "instruction": None},
            {"param_id": "47007", "value": 8.0, "type": "api", "priority": "low", "reason": "Brantare kurva", "expected": "Mer värme vid kyla", "instruction": None},
            
            # Degree Minutes variations (47206 - GM start) - Optimization of cycles
            {"param_id": "47206", "value": -160.0, "type": "api", "priority": "medium", "reason": "Tidig start kompressor (-160)", "expected": "Jämnare temp, fler starter", "instruction": None},
            {"param_id": "47206", "value": -800.0, "type": "api", "priority": "medium", "reason": "Sen start kompressor (-800)", "expected": "Färre starter, längre körningar (Bra för COP)", "instruction": None},
            
            # Hot water variations (47041)
            {"param_id": "47041", "value": 0.0, "type": "api", "priority": "low", "reason": "Litet varmvattenbehov", "expected": "Lägre förbrukning, snabbare återhämtning värme", "instruction": None},
            
            # Additional Heat Strategy (48072)
            {"param_id": "48072", "value": 2000.0, "type": "api", "priority": "medium", "reason": "Fördröj elpatron (2000 DM)", "expected": "Minimera dyr elspets", "instruction": None},
            
            # Heating Stop (47375)
            {"param_id": "47375", "value": 12.0, "type": "api", "priority": "low", "reason": "Sänkstopp för värme (12C)", "expected": "Sparar energi vår/höst", "instruction": None},

            # --- MANUAL TESTS (User Action Required) ---
            
            # Circulation Pump (Flow)
            {
                "param_id": "MANUAL_GP1", 
                "value": 0.0, # Placeholder
                "type": "manual",
                "priority": "medium",
                "reason": "Justera Cirkulationspump (Meny 5.1.14)", 
                "expected": "Optimera Delta T till 5-8°C. Om <4°C: Sänk hastighet. Om >10°C: Öka.",
                "instruction": "I värmepumpens display: Gå till Meny 5.1.14 'Flödesinställning klimatsystem'. Ändra till ett fast procentvärde (t.ex. 60%) för att uppnå en Delta T (skillnad mellan framledning och retur) på 5-8°C. Återkoppla i GUI när klart."
            },
            
            # Ventilation (Fan Speed)
            {
                "param_id": "MANUAL_FAN",
                "value": 0.0, # Placeholder
                "type": "manual", 
                "priority": "medium",
                "reason": "Justera Fläkthastighet (Meny 5.1.1)", 
                "expected": "Högre avluftstemp = mer energi till kompressor. Bättre COP.",
                "instruction": "I värmepumpens display: Gå till Meny 5.1.1 'Frånluftsfläkthastighet'. Om avluft (BT21) är >5°C vid kompressordrift, prova sänka fläkten 5% för att optimera energiutvinningen. Återkoppla i GUI när klart."
            }
        ]

    def propose_next_test(self, current_indoor_temp: float) -> Optional[PlannedTest]:
        """Propose the next logical test based on current state and history"""
        
        # 1. Safety Check
        device = self.db.query(Device).first()
        if not device:
            return None
            
        base_min = device.min_indoor_temp_user_setting
        comfort_offset = getattr(device, 'comfort_adjustment_offset', 0.0)
        safe_min_temp = base_min + comfort_offset
        
        is_temp_low = current_indoor_temp < (safe_min_temp + 0.5)
        
        # --- Prioritize the Rumsgivare test ---
        rumsgivare_test = next((v for v in self.variations if v['param_id'] == "47394" and v['type'] == 'api'), None)
        if rumsgivare_test:
            param_db_id = self._get_param_id_db(rumsgivare_test['param_id'])
            if param_db_id:
                # Check if this test is already pending or completed
                existing = self.db.query(PlannedTest).filter(
                    PlannedTest.parameter_id == param_db_id,
                    PlannedTest.proposed_value == rumsgivare_test['value'],
                    PlannedTest.status.in_(['pending', 'active', 'completed'])
                ).first()
                if not existing:
                    return self._create_proposal(rumsgivare_test, param_db_id)
        # --- End Rumsgivare priority ---

        # Filter valid variations for other tests
        allowed_variations = []
        for v in self.variations:
            if v['type'] == 'api': # Only consider API tests in this loop
                # Skip cooling tests if temp is already low
                if is_temp_low and not self._is_heating_increase(v):
                    continue
                allowed_variations.append(v)
        
        # Sort by priority (high > medium > low) and then by param_id for consistency
        priority_map = {"high": 3, "medium": 2, "low": 1}
        allowed_variations.sort(key=lambda v: (priority_map.get(v.get('priority', 'medium'), 0), v['param_id']), reverse=True)


        # 2. Check recently performed tests (last 7 days)
        recent_changes = self.db.query(ParameterChange).filter(
            ParameterChange.timestamp > datetime.utcnow() - timedelta(days=7)
        ).all()
        
        for variation in allowed_variations:
            param_db_id = self._get_param_id_db(variation['param_id'])
            if not param_db_id:
                continue
                
            # Check if we have a pending/active/completed test for this specific variation
            existing_planned_test = self.db.query(PlannedTest).filter(
                PlannedTest.parameter_id == param_db_id,
                PlannedTest.proposed_value == variation['value'],
                PlannedTest.status.in_(['pending', 'active', 'completed'])
            ).first()
            
            if existing_planned_test:
                continue # Already planned or done
                
            # Create proposal
            return self._create_proposal(variation, param_db_id)
                
        return None

    def _is_heating_increase(self, variation: Dict) -> bool:
        """Heuristic to determine if a change increases heating"""
        pid = variation['param_id']
        val = variation['value']
        
        # Explicit checks for known heating-increasing parameters
        if pid == "47011" and val > self.baseline_offset: return True # Higher offset
        if pid == "47007" and val > self.baseline_curve: return True # Steeper curve
        if pid == "47206" and val > -200: return True # Less negative DM (starts sooner/more frequently)
        if pid == "47375" and val > 13: return True # Higher stop heating temp
        if pid == "47394" and val > 0: return True # Activating room sensor influence can increase perceived heat

        # Default to false for unknown or non-heating params
        return False

    def _get_param_id_db(self, param_str_id: str) -> Optional[int]:
        param = self.db.query(Parameter).filter_by(parameter_id=param_str_id).first()
        return param.id if param else None

    def _create_proposal(self, variation: Dict, param_db_id: int) -> PlannedTest:
        return PlannedTest(
            parameter_id=param_db_id,
            proposed_value=variation['value'],
            current_value=0.0, # Placeholder, should be filled at execution
            hypothesis=variation['reason'],
            expected_improvement=variation['expected'],
            priority=variation.get('priority', 'medium'),
            status='pending',
            confidence=0.8,
            reasoning=f"Scientific Mode ({variation['type'].upper()}): {variation['expected']}",
            instruction=variation.get('instruction')
        )

