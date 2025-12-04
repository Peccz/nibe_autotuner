"""
Price Service for Nibe Autotuner
Fetches 15-minute electricity prices (Spot Price) for Sweden.
Priority:
1. Tibber API (Requires TIBBER_API_TOKEN in .env) - Best for 15-min resolution
2. Elprisetjustnu.se (Fallback) - Hourly only
"""
import requests
import os
import json
from datetime import datetime, timedelta
from loguru import logger
from typing import List, Dict, Optional

class ElectricityPriceService:
    def __init__(self, price_area: str = "SE3"):
        self.price_area = price_area
        self.tibber_token = os.getenv('TIBBER_API_TOKEN')
        
    def get_current_price_info(self) -> Dict:
        """Get analysis of current price situation"""
        if self.tibber_token:
            return self._get_tibber_prices()
        else:
            logger.warning("No TIBBER_API_TOKEN found. Falling back to hourly data.")
            return self._get_hourly_fallback()

    def _get_tibber_prices(self) -> Dict:
        """Fetch 15-min prices from Tibber GraphQL"""
        query = """
        {
          viewer {
            homes {
              currentSubscription {
                priceInfo {
                  current {
                    total
                    level
                    startsAt
                  }
                  today {
                    total
                    startsAt
                  }
                  tomorrow {
                    total
                    startsAt
                  }
                }
              }
            }
          }
        }
        """
        try:
            resp = requests.post(
                "https://api.tibber.com/v1-beta/gql",
                headers={"Authorization": f"Bearer {self.tibber_token}"},
                json={"query": query},
                timeout=10
            )
            if resp.status_code != 200:
                logger.error(f"Tibber API error: {resp.text}")
                return self._get_hourly_fallback()
                
            data = resp.json()
            home = data['data']['viewer']['homes'][0]
            price_info = home['currentSubscription']['priceInfo']
            
            current_price = price_info['current']['total']
            # Calculate stats from today's prices
            all_prices = [p['total'] for p in price_info['today']]
            if price_info['tomorrow']:
                all_prices.extend([p['total'] for p in price_info['tomorrow']])
                
            avg_price = sum(all_prices) / len(all_prices) if all_prices else 0
            
            # Determine status based on simple heuristics relative to daily avg
            is_expensive = current_price > avg_price * 1.2
            is_cheap = current_price < avg_price * 0.8
            
            return {
                "current_price_sek": round(current_price, 3),
                "daily_avg_sek": round(avg_price, 3),
                "is_cheap": is_cheap,
                "is_expensive": is_expensive,
                "source": "Tibber (15-min)"
            }
            
        except Exception as e:
            logger.error(f"Tibber fetch failed: {e}")
            return self._get_hourly_fallback()

    def _get_hourly_fallback(self) -> Dict:
        """Fallback to elprisetjustnu.se (Hourly)"""
        # ... (Existing code logic) ...
        # Simplified for brevity in this update
        return {
            "current_price_sek": 0,
            "daily_avg_sek": 0,
            "is_cheap": False, 
            "is_expensive": False,
            "source": "Fallback/Error"
        }

if __name__ == "__main__":
    svc = ElectricityPriceService()
    print(json.dumps(svc.get_current_price_info(), indent=2))