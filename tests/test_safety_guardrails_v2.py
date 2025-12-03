"""
Safety Guardrails Tests for Nibe Autotuner V2
Verifies that the V2 Agent effectively blocks dangerous or nonsensical changes.
"""
import pytest
from unittest.mock import Mock, patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/src')

from autonomous_ai_agent_v2 import AutonomousAIAgentV2
from autonomous_ai_agent import AIDecision

class TestSafetyGuardrailsV2:
    
    @pytest.fixture
    def agent_v2(self):
        analyzer = Mock()
        api_client = Mock()
        weather_service = Mock()
        
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'mock-key'}):
            agent = AutonomousAIAgentV2(analyzer, api_client, weather_service, "device-123", "mock-key")
        
        # Mock client to avoid API calls
        agent.client = Mock()
        return agent

    def test_block_low_indoor_temp(self, agent_v2):
        """V2 should explicitly BLOCK dangerous indoor temps"""
        
        unsafe_decision = AIDecision(
            action='adjust',
            parameter='room_temp',
            current_value=20,
            suggested_value=15, # TOO LOW (<19)
            reasoning="Freeze the house",
            confidence=0.99,
            expected_impact="Bad things"
        )
        
        is_safe, reason = agent_v2._is_decision_safe(unsafe_decision)
        
        assert is_safe is False
        assert "below safety limit" in reason

    def test_block_aggressive_change(self, agent_v2):
        """V2 should BLOCK large sudden changes"""
        
        aggressive_decision = AIDecision(
            action='adjust',
            parameter='curve_offset',
            current_value=0,
            suggested_value=5, # +5 change (limit is 2)
            reasoning="YOLO",
            confidence=0.95,
            expected_impact="Huge jump"
        )
        
        is_safe, reason = agent_v2._is_decision_safe(aggressive_decision)
        
        assert is_safe is False
        assert "too aggressive" in reason

    def test_allow_safe_change(self, agent_v2):
        """V2 should ALLOW safe, modest changes"""
        
        safe_decision = AIDecision(
            action='adjust',
            parameter='curve_offset',
            current_value=0,
            suggested_value=-1, # Small change
            reasoning="Optimize COP",
            confidence=0.85,
            expected_impact="Good things"
        )
        
        is_safe, reason = agent_v2._is_decision_safe(safe_decision)
        
        assert is_safe is True
        assert reason == ""
