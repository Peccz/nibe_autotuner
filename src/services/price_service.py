import requests
import json
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from loguru import logger
import os

@dataclass
class PricePoint:
    time_start: datetime
    price_per_kwh: float

class PriceService:
    """
    Hämtar aktuella elpriser (spotpris) från Elprisetjustnu.se (gratis, inget konto).
    """

    def __init__(self):
        # Standardzon SE3 (Stockholm) om inget annat anges i .env
        self.zone = os.getenv("ELECTRICITY_ZONE", "SE3")
        self.api_base_url = "https://www.elprisetjustnu.se/api/v1/prices"

        # Enkel cache för att slippa anropa API:t varje gång
        self.cache: Dict[str, Any] = {}
        # Cache per datumsträng
        self.date_caches: Dict[str, List[Dict]] = {}
        
        # Thread-safety: Lock för cache-access
        self._cache_lock = threading.Lock()

    def get_current_price(self) -> float:
        """
        Hämtar aktuellt timpris i SEK/kWh.
        Inkluderar INTE överföringsavgifter eller skatt, bara spotpriset.
        Fallback till 1.50 om fel.
        """
        try:
            now = datetime.now()
            prices = self._get_prices_for_date(now)
            
            if not prices:
                return self._get_fallback_price(now)

            current_hour = now.hour
            
            for p in prices:
                try:
                    start_time = datetime.fromisoformat(p['time_start'])
                    if start_time.hour == current_hour:
                        return float(p['SEK_per_kWh'])
                except Exception:
                    continue
            
            return self._get_fallback_price(now)

        except Exception as e:
            logger.error(f"Error fetching electricity price: {e}")
            return 1.50 # Fallback

    def _get_fallback_price(self, dt: datetime) -> float:
        # Enkel fallback: dyrare på dagen (06-22), billigare på natten
        if 6 <= dt.hour < 22:
            return 1.50
        return 0.50

    def get_price_analysis(self) -> Dict[str, Any]:
        """
        Ger en analys av prisläget:
        - current_price: Nuvarande pris
        - price_level: CHEAP, NORMAL, EXPENSIVE, VERY_EXPENSIVE
        - average: Dygnsmedel
        """
        current_obj = self.get_current_price_point()
        current = current_obj.price_per_kwh
        
        # Hämta alla priser för idag för att räkna snitt
        prices_today = self.get_prices_today()
        
        if not prices_today:
            return {
                "current_price": current,
                "price_level": "NORMAL",
                "average": current,
                "trend": "STABLE"
            }

        daily_values = [p.price_per_kwh for p in prices_today]
        avg_price = sum(daily_values) / len(daily_values) if daily_values else current
        
        if current < avg_price * 0.8:
            level = "CHEAP"
        elif current > avg_price * 1.4:
            level = "VERY_EXPENSIVE"
        elif current > avg_price * 1.15:
            level = "EXPENSIVE"
        else:
            level = "NORMAL"

        return {
            "current_price": round(current, 3),
            "price_level": level,
            "average": round(avg_price, 3),
            "currency": "SEK"
        }

    def get_current_price_point(self) -> PricePoint:
        now = datetime.now()
        price = self.get_current_price()
        return PricePoint(time_start=now, price_per_kwh=price)

    def get_prices_today(self) -> List[PricePoint]:
        data = self._get_prices_for_date(datetime.now())
        return self._parse_prices(data)

    def get_prices_tomorrow(self) -> List[PricePoint]:
        tomorrow = datetime.now() + timedelta(days=1)
        data = self._get_prices_for_date(tomorrow)
        return self._parse_prices(data)

    def _parse_prices(self, data: List[Dict]) -> List[PricePoint]:
        points = []
        for item in data:
            try:
                # Handle potential timezone offsets or Z
                ts_str = item['time_start']
                if ts_str.endswith('Z'):
                    ts_str = ts_str[:-1] + '+00:00'
                dt = datetime.fromisoformat(ts_str)
                
                price = float(item['SEK_per_kWh'])
                points.append(PricePoint(time_start=dt, price_per_kwh=price))
            except Exception as e:
                logger.warning(f"Failed to parse price item: {item} - {e}")
                pass
        return points

    def _get_prices_for_date(self, date_obj: datetime) -> List[Dict]:
        """Hämtar priser för ett specifikt datum med thread-safe caching"""
        date_str = date_obj.strftime('%Y/%m-%d') # Format: 2023/10-25

        with self._cache_lock:
            if date_str in self.date_caches:
                # Simple TTL check could be added here, but prices for a past/current date are static mostly.
                # Only "tomorrow" might appear later in the day.
                # For now, trust the cache if it has data.
                if self.date_caches[date_str]:
                    return self.date_caches[date_str]

        # Cache miss - fetch from API
        url = f"{self.api_base_url}/{date_str}_{self.zone}.json"

        try:
            logger.info(f"Fetching prices from {url}")
            response = requests.get(url, timeout=10)
            if response.status_code == 404:
                logger.info("Prices not available yet (404)")
                return []
            
            response.raise_for_status()
            data = response.json()

            with self._cache_lock:
                self.date_caches[date_str] = data

            return data
        except Exception as e:
            logger.error(f"Failed to fetch prices from Elprisetjustnu: {e}")
            return []

# Singleton instance
price_service = PriceService()