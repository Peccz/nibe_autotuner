import requests
import json
import threading
from datetime import datetime, timedelta, timezone
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

    # Single source of truth for "no price available" total cost (SEK/kWh).
    # Used here AND by smart_planner so the fallback behaviour is identical on
    # every code path (see DNA pitfall #2).
    FALLBACK_PRICE_SEK = 1.0
    
    def __init__(self):
        self.zone = os.getenv("ELECTRICITY_ZONE", "SE3")
        self.api_base_url = "https://www.elprisetjustnu.se/api/v1/prices"
        self.cache: Dict[str, Any] = {}
        self.date_caches: Dict[str, List[Dict]] = {}
        self._cache_lock = threading.Lock()

    def _calculate_total_cost(self, spot_price_incl_vat: float, dt: datetime) -> float:
        """
        Räknar ut totalt pris (Spot + Nät + Skatt + Påslag + Moms).
        Spotpriset från API:et (elprisetjustnu.se) inkluderar redan 25% moms.
        """
        # Spotpriset inkluderar redan moms.
        
        # Nätavgift och elhandlarpåslag (antag exkl. moms i konstanterna)
        base_fees_excl_vat = self.GRID_FEE_FLAT + self.RETAILER_FEE
        fees_incl_vat = base_fees_excl_vat * self.VAT_RATE
        
        # Totalt pris inkl. moms men exkl. energiskatt
        subtotal_incl_vat = spot_price_incl_vat + fees_incl_vat
        
        # Lägg till Energiskatten (som är inklusive moms)
        final_price_per_kwh = subtotal_incl_vat + self.ENERGY_TAX_INCL_VAT
        
        return final_price_per_kwh

    def get_current_price(self) -> float:
        return self.get_current_price_details()['total']

    def get_current_price_details(self) -> Dict[str, float]:
        """Returns detailed price info: {'total': float, 'spot': float}"""
        return self.get_price_details_at(datetime.now())

    def get_price_at(self, dt: datetime) -> float:
        """Returns the total price at a specific historical datetime"""
        return self.get_price_details_at(dt)['total']

    def get_price_details_at(self, dt: datetime) -> Dict[str, float]:
        """Returns detailed price info for a specific datetime.

        Matching is done in UTC so it does not depend on the host timezone
        matching the price zone (DNA pitfall #2). Naive datetimes are assumed
        to be system-local. When no price is available the total falls back to
        FALLBACK_PRICE_SEK, identical to smart_planner's per-hour fallback.
        """
        try:
            prices = self._get_prices_for_date(dt)
            target_utc = (dt if dt.tzinfo else dt.astimezone()).astimezone(timezone.utc)

            matched_spot = None
            if prices:
                for p in prices:
                    try:
                        start_utc = datetime.fromisoformat(p['time_start']).astimezone(timezone.utc)
                        if (start_utc.year, start_utc.month, start_utc.day, start_utc.hour) == \
                           (target_utc.year, target_utc.month, target_utc.day, target_utc.hour):
                            matched_spot = float(p['SEK_per_kWh'])
                            break
                    except Exception:
                        continue

            if matched_spot is None:
                return {'total': self.FALLBACK_PRICE_SEK, 'spot': 0.0}

            total = self._calculate_total_cost(matched_spot, dt)
            return {'total': total, 'spot': matched_spot}
        except Exception as e:
            logger.error(f"Error fetching price at {dt}: {e}")
            return {'total': self.FALLBACK_PRICE_SEK, 'spot': 0.0}

    def get_prices_yesterday(self) -> List[PricePoint]:
        yesterday = datetime.now() - timedelta(days=1)
        data = self._get_prices_for_date(yesterday)
        return self._parse_prices(data)

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

