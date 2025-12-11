import requests
import json
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from loguru import logger
import os

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
        self.cache_timestamp: Optional[datetime] = None
        self.cache_date_str: Optional[str] = None

        # Thread-safety: Lock för cache-access
        self._cache_lock = threading.Lock()

    def get_current_price(self) -> float:
        """
        Hämtar aktuellt timpris i SEK/kWh.
        Inkluderar INTE överföringsavgifter eller skatt, bara spotpriset.
        """
        try:
            now = datetime.now()
            prices = self._get_prices_for_date(now)
            
            if not prices:
                logger.warning("Could not fetch prices, using fallback default.")
                return 1.50 # Fallback: 1.50 kr om API är nere

            # Hitta rätt timme
            current_hour = now.hour
            
            for p in prices:
                # API format: "time_start": "2023-10-25T14:00:00+02:00"
                # Vi litar på ordningen eller parsear datumet
                try:
                    start_time = datetime.fromisoformat(p['time_start'])
                    if start_time.hour == current_hour:
                        # Priset är i SEK per kWh
                        return float(p['SEK_per_kWh'])
                except Exception:
                    continue
            
            logger.warning(f"Could not find price for hour {current_hour}, using fallback.")
            return 1.50

        except Exception as e:
            logger.error(f"Error fetching electricity price: {e}")
            return 1.50 # Fallback

    def get_price_analysis(self) -> Dict[str, Any]:
        """
        Ger en analys av prisläget:
        - current_price: Nuvarande pris
        - price_level: CHEAP, NORMAL, EXPENSIVE, VERY_EXPENSIVE
        - average: Dygnsmedel
        - is_cheap_soon: Om priset sjunker kommande timmar
        """
        current = self.get_current_price()
        
        # Hämta alla priser för idag för att räkna snitt
        prices = self._get_prices_for_date(datetime.now())
        if not prices:
            return {
                "current_price": current,
                "price_level": "NORMAL", # Utgå från normalt om vi inte vet
                "average": current,
                "trend": "STABLE"
            }

        daily_values = [float(p['SEK_per_kWh']) for p in prices]
        avg_price = sum(daily_values) / len(daily_values)
        
        # Bestäm nivå relativt till dygnsmedel
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

    def _get_prices_for_date(self, date_obj: datetime) -> List[Dict]:
        """Hämtar priser för ett specifikt datum med thread-safe caching"""
        date_str = date_obj.strftime('%Y/%m-%d') # Format: 2023/10-25

        # Check cache with lock (fast path)
        with self._cache_lock:
            if (self.cache_date_str == date_str and
                self.cache and
                self.cache_timestamp and
                (datetime.now() - self.cache_timestamp).total_seconds() < 3600):
                return self.cache.copy()  # Return copy to avoid mutation issues

        # Cache miss - fetch from API (outside lock to avoid blocking other threads)
        # Konstruera URL: https://www.elprisetjustnu.se/api/v1/prices/2023/10-25_SE3.json
        url = f"{self.api_base_url}/{date_str}_{self.zone}.json"

        try:
            logger.info(f"Fetching prices from {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Uppdatera cache med lock
            with self._cache_lock:
                self.cache = data
                self.cache_date_str = date_str
                self.cache_timestamp = datetime.now()

            return data
        except Exception as e:
            logger.error(f"Failed to fetch prices from Elprisetjustnu: {e}")
            return []

# Singleton instance
price_service = PriceService()
