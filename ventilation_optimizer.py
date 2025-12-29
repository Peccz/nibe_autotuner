"""
Ventilation Optimizer Service
Optimizes ventilation speed based on outdoor temperature and electricity price.
Parameter: 50005 (Ventilation Normal/Speed 1-4)
"""
from typing import Dict, Any, Optional
from loguru import logger
from datetime import datetime

from services.analyzer import HeatPumpAnalyzer
from services.price_service import price_service
from integrations.api_client import MyUplinkClient

class VentilationOptimizer:
    def __init__(self, api_client: MyUplinkClient, analyzer: HeatPumpAnalyzer, device_id: str):
        self.api_client = api_client
        self.analyzer = analyzer
        self.device_id = device_id
        self.PARAM_VENTILATION = '50005'
        
        # Default settings
        self.TEMP_THRESHOLD_COLD = -10.0 # Sänk om kallare än -10
        self.PRICE_THRESHOLD_HIGH = 3.00 # Sänk om dyrare än 3 kr/kWh
        
    def get_current_status(self) -> Dict[str, Any]:
        """Get current ventilation status"""
        try:
            device = self.analyzer.get_device()
            current_val = self.analyzer.get_latest_value(device, self.PARAM_VENTILATION)
            
            if current_val is None:
                current_val = 0 # Assuming 0 is Normal
                
            return {
                "current_speed": current_val,
                "status": "NORMAL" if current_val == 0 else f"SPEED {current_val}"
            }
        except Exception as e:
            logger.error(f"Error getting ventilation status: {e}")
            return {"current_speed": None, "status": "UNKNOWN"}

    def analyze_optimization(self) -> Dict[str, Any]:
        """
        Analyze if ventilation should be adjusted.
        Returns recommendation.
        """
        result = {
            "action": "hold",
            "reason": "Normal operation",
            "suggested_value": 0 # Normal
        }
        
        try:
            # 1. Check Outdoor Temp
            device = self.analyzer.get_device()
            outdoor_temp = self.analyzer.get_latest_value(device, self.analyzer.PARAM_OUTDOOR_TEMP)
            
            if outdoor_temp is not None and outdoor_temp < self.TEMP_THRESHOLD_COLD:
                result["action"] = "reduce"
                result["reason"] = f"Outdoor temp ({outdoor_temp:.1f}C) is very low (<{self.TEMP_THRESHOLD_COLD}C). Reducing ventilation to save heat."
                result["suggested_value"] = 1 # Low speed
                return result

            # 2. Check Price
            price_info = price_service.get_price_analysis()
            current_price = price_info.get("current_price", 0)
            
            if current_price > self.PRICE_THRESHOLD_HIGH:
                result["action"] = "reduce"
                result["reason"] = f"Electricity price ({current_price:.2f} SEK) is very high (>{self.PRICE_THRESHOLD_HIGH} SEK). Reducing ventilation."
                result["suggested_value"] = 1 # Low speed
                return result
                
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing ventilation: {e}")
            return result
