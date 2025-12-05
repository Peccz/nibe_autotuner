"""
Price Service for Nibe Autotuner
Fetches 15-minute electricity prices (Spot Price) for Sweden.
Priority:
1. Tibber API (Requires TIBBER_API_TOKEN in .env) - Best for 15-min resolution
2. Elprisetjustnu.se (Fallback) - Hourly only
"""
import requests
import json
from datetime import datetime, timedelta
from loguru import logger
from typing import List, Dict, Optional
from config import settings

class ElectricityPriceService:
    def __init__(self, price_area: str = "SE3"):
        self.price_area = price_area
        self.tibber_token = settings.TIBBER_API_TOKEN
        
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

            # Validate response structure
            if not data.get('data', {}).get('viewer', {}).get('homes'):
                logger.error("Tibber API: No homes found in response")
                return self._get_hourly_fallback()

            home = data['data']['viewer']['homes'][0]

            if not home.get('currentSubscription'):
                logger.error("Tibber API: No active subscription found. Please ensure your Tibber account has an active electricity subscription.")
                return self._get_hourly_fallback()

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
        """Fallback to elprisetjustnu.se (Hourly prices)"""
        try:
            # Map SE regions to elprisetjustnu.se regions
            region_map = {
                "SE1": "SE1",  # Luleå
                "SE2": "SE2",  # Sundsvall
                "SE3": "SE3",  # Stockholm
                "SE4": "SE4",  # Malmö
            }
            region = region_map.get(self.price_area, "SE3")

            # Get today's prices
            today = datetime.now()
            url = f"https://www.elprisetjustnu.se/api/v1/prices/{today.year}/{today.month:02d}-{today.day:02d}_{region}.json"

            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"Elprisetjustnu.se API returned {resp.status_code}")
                return self._get_error_fallback()

            prices = resp.json()

            # Find current hour
            current_hour = datetime.now().hour
            current_price = None
            all_prices = []

            for p in prices:
                price_sek = p['SEK_per_kWh']
                all_prices.append(price_sek)

                # Check if this is the current hour
                time_start = datetime.fromisoformat(p['time_start'].replace('Z', '+00:00'))
                if time_start.hour == current_hour:
                    current_price = price_sek

            if current_price is None:
                logger.warning("Could not find current hour in price data")
                return self._get_error_fallback()

            avg_price = sum(all_prices) / len(all_prices) if all_prices else 0

            is_expensive = current_price > avg_price * 1.2
            is_cheap = current_price < avg_price * 0.8

            return {
                "current_price_sek": round(current_price, 3),
                "daily_avg_sek": round(avg_price, 3),
                "is_cheap": is_cheap,
                "is_expensive": is_expensive,
                "source": "Elprisetjustnu.se (Hourly)"
            }

        except Exception as e:
            logger.error(f"Hourly fallback failed: {e}")
            return self._get_error_fallback()

    def _get_error_fallback(self) -> Dict:
        """Return safe defaults when all price fetching fails"""
        return {
            "current_price_sek": 1.0,  # Reasonable default (~1 SEK/kWh)
            "daily_avg_sek": 1.0,
            "is_cheap": False,
            "is_expensive": False,
            "source": "Error/Default"
        }

if __name__ == "__main__":
    svc = ElectricityPriceService()
    print(json.dumps(svc.get_current_price_info(), indent=2))