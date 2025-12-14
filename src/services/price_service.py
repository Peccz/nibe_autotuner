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
    Hämtar aktuella elpriser och lägger på ALLA avgifter för att få fram verklig kostnad.
    Baserat på användarens E.ON priser i Upplands Väsby.
    """

    # --- PRISKOMPONENTER (SEK/kWh) ---
    # Dessa värden är baserade på användarens faktiska priser från E.ON i Upplands Väsby.
    # Spotpriset från API:et antas vara EXKLUSIVE moms.
    
    GRID_FEE_FLAT = 0.25                                # Elöverföringsavgift: 25 öre/kWh (Dygnet runt)
    ENERGY_TAX_INCL_VAT = 0.5488                        # Energiskatt: 54.88 öre/kWh (Inklusive moms)
    RETAILER_FEE = float(os.getenv("PRICE_RETAILER", 0.05)) # Elhandlare: Påslag + Elcertifikat (Default 5 öre/kWh)
    VAT_RATE = 1.25                                     # Moms: 25% (på spotpris + nätavgift + påslag)
    
    def __init__(self):
        self.zone = os.getenv("ELECTRICITY_ZONE", "SE3")
        self.api_base_url = "https://www.elprisetjustnu.se/api/v1/prices"
        self.cache: Dict[str, Any] = {}
        self.date_caches: Dict[str, List[Dict]] = {}
        self._cache_lock = threading.Lock()

    def _calculate_total_cost(self, spot_price: float, dt: datetime) -> float:
        """
        Räknar ut totalt pris (Spot + Nät + Skatt + Påslag + Moms).
        """
        # Spotpriset från API:et är vanligen exklusive moms.
        spot_excl_vat = spot_price 
        
        # Komponenter som moms läggs på
        base_components_excl_vat = spot_excl_vat + self.GRID_FEE_FLAT + self.RETAILER_FEE
        
        # Lägg på moms på dessa komponenter
        total_incl_vat_excl_energy_tax = base_components_excl_vat * self.VAT_RATE
        
        # Lägg till Energiskatten (som du angav är inklusive moms)
        final_price_per_kwh = total_incl_vat_excl_energy_tax + self.ENERGY_TAX_INCL_VAT
        
        return final_price_per_kwh

    def get_current_price(self) -> float:
        try:
            now = datetime.now()
            prices = self._get_prices_for_date(now)
            
            spot = 1.0 # Fallback default spot
            if prices:
                for p in prices:
                    try:
                        start_time = datetime.fromisoformat(p['time_start'])
                        # Adjust for timezone if necessary (API is often +01:00 or +02:00)
                        # Ensure comparison is done on same timezone (UTC for now)
                        if start_time.replace(tzinfo=None).hour == now.hour:
                            spot = float(p['SEK_per_kWh'])
                            break
                    except: continue
            
            return self._calculate_total_cost(spot, now)

        except Exception as e:
            logger.error(f"Error fetching electricity price: {e}")
            return 1.50 # General fallback if API fails or other errors

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
                ts_str = item['time_start']
                if ts_str.endswith('Z'): ts_str = ts_str[:-1] + '+00:00'
                dt = datetime.fromisoformat(ts_str)
                
                spot_price = float(item['SEK_per_kWh'])
                total_price = self._calculate_total_cost(spot_price, dt)
                
                points.append(PricePoint(time_start=dt, price_per_kwh=total_price))
            except Exception as e:
                logger.warning(f"Failed to parse price item: {item} - {e}")
                pass
        return points

    def _get_prices_for_date(self, date_obj: datetime) -> List[Dict]:
        date_str = date_obj.strftime('%Y/%m-%d')
        with self._cache_lock:
            if date_str in self.date_caches and self.date_caches[date_str]:
                return self.date_caches[date_str]

        url = f"{self.api_base_url}/{date_str}_{self.zone}.json"
        try:
            logger.info(f"Fetching prices from {url}")
            response = requests.get(url, timeout=10)
            if response.status_code == 404:
                return [] # Not available yet
            response.raise_for_status()
            data = response.json()
            with self._cache_lock:
                self.date_caches[date_str] = data
            return data
        except Exception as e:
            logger.error(f"Failed to fetch prices: {e}")
            return []

# Singleton instance
price_service = PriceService()
