# infrastructure/ingestion/pmd_scraper.py
# Scrape PMD/FFD (Flood Forecasting Division) river gauge + flood data.
# Source: https://ffd.pmd.gov.pk/bulletin/bulletin
# Includes retry logic for transient HTTP errors.
import re
import hashlib
import logging
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Dict

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

PMD_BASE = "https://ffd.pmd.gov.pk"
PMD_BULLETIN_URL = f"{PMD_BASE}/bulletin/bulletin"


@dataclass
class PMDObservation:
    station_name: str
    river: str
    observed_at: date
    gauge_level_ft: Optional[float] = None
    discharge_cusecs: Optional[float] = None
    flood_status: str = "NORMAL"
    forecast_trend: str = "STEADY"
    forecast_range: str = ""
    historical_max: Optional[float] = None
    source_url: str = ""
    raw_text: str = ""


# Station definitions: (search_key, river, canonical_name)
STATIONS = [
    ("Tarbela", "INDUS", "Tarbela Reservoir"),
    ("Kalabagh", "INDUS", "Kalabagh (Indus)"),
    ("Chashma", "INDUS", "Chashma Barrage"),
    ("Taunsa", "INDUS", "Taunsa Barrage"),
    ("Guddu", "INDUS", "Guddu Barrage"),
    ("Sukkur", "INDUS", "Sukkur Barrage"),
    ("Kotri", "INDUS", "Kotri Barrage"),
    ("Nowshera", "KABUL", "Kabul @ Nowshera"),
    ("Mangla", "JHELUM", "Mangla Reservoir"),
    ("Marala", "CHENAB", "Chenab @ Marala"),
    ("Panjnad", "CHENAB", "Panjnad"),
]

STATUS_PATTERN = r'(Below Low|Low|Medium|High|Very High|Exceptionally High|No sig\.\s*change)'


class PMDScraper:
    """Scrape FFD Lahore flood bulletins and discharge reports."""

    def __init__(self):
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "IBCP-SCADA/1.0 (water-data-ingestion)"},
        )

    def fetch_bulletin_page(self) -> str:
        """Fetch the main FFD bulletin page with retry logic."""
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=60, min=60, max=900),  # 1min, 2min, 4min
            retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )
        def _fetch_with_retry() -> str:
            resp = self.client.get(PMD_BULLETIN_URL)
            resp.raise_for_status()
            return resp.text
        
        return _fetch_with_retry()

    def parse_flood_bulletin(self, html: str, target_date: date) -> List[PMDObservation]:
        """Parse river gauge/discharge data from FFD flood bulletin.
        
        FFD format (concatenated text):
        INDUSTarbela289.0288.5300 - 310Low832.0EH (2010)343.0
        
        Fields: RIVER + STATION + INFLOW + OUTFLOW + FORECAST_RANGE + STATUS + HISTORICAL_MAX + (YEAR) + CURRENT_YEAR_MAX
        
        Key insight: numbers run together (e.g., 289.0288.5300 = 289.0 + 288.5 + 300)
        Strategy: split on '.' and reconstruct using known structure.
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()

        observations = []

        # Find the observations section
        obs_match = re.search(r'Observations?\s+at\s+\d+', text)
        if not obs_match:
            logger.warning("No 'Observations at' section found in FFD bulletin")
            return observations

        # Extract the observations text block
        start = obs_match.start()
        end_match = re.search(r'Spatial:|Intensity|Note:', text[start+100:])
        if end_match:
            obs_text = text[start:start+100+end_match.start()]
        else:
            obs_text = text[start:start+5000]

        # Parse each known station from the concatenated text
        for search_key, river, canonical_name in STATIONS:
            idx = obs_text.find(search_key)
            if idx < 0:
                continue

            # Get text after station name
            after_station = obs_text[idx + len(search_key):]
            
            # Split on status word to get before/after
            status_match = re.search(STATUS_PATTERN, after_station)
            if not status_match:
                logger.debug(f"No status found for {search_key}")
                continue
            
            before_status = after_station[:status_match.start()]
            status = status_match.group(1)
            after_status = after_station[status_match.end():]
            
            # Before status: "289.0288.5300 - 310" = inflow + outflow + forecast
            # Split on " - " to separate forecast
            forecast_split = before_status.split(' - ')
            if len(forecast_split) == 2:
                numbers_part = forecast_split[0]  # "289.0288.5300"
                forecast_high = forecast_split[1]  # "310"
            else:
                numbers_part = before_status
                forecast_high = ""
            
            # Now split numbers_part: "289.0288.5300"
            # Strategy: split on '.' and reconstruct
            # Inflow = parts[0] + '.' + parts[1][0] = '289.0'
            # Outflow = parts[1][1:] + '.' + parts[2][0] = '288.5'
            # Forecast low = parts[2][1:] = '300'
            parts = numbers_part.split('.')
            
            inflow = None
            outflow = None
            forecast_range = before_status
            
            if len(parts) >= 3:
                try:
                    inflow = float(parts[0] + '.' + parts[1][0])
                    outflow = float(parts[1][1:] + '.' + parts[2][0])
                    forecast_low = parts[2][1:]
                    forecast_range = f"{forecast_low} - {forecast_high}"
                except (ValueError, IndexError):
                    pass
            
            # After status: "832.0EH (2010)343.0" = historical + year + current
            historical = None
            year = None
            current = None
            
            hist_match = re.match(r'([\d.]+)', after_status)
            if hist_match:
                try:
                    historical = float(hist_match.group(1))
                except ValueError:
                    pass
            
            year_match = re.search(r'\((\d{4})\)', after_status)
            if year_match:
                year = year_match.group(1)
            
            current_match = re.search(r'\((\d{4})\)([\d.]+)', after_status)
            if current_match:
                try:
                    current = float(current_match.group(2))
                except ValueError:
                    pass
            
            # FFD reports inflow in thousands of cusecs
            discharge_cusecs = inflow * 1000 if inflow else None

            # Normalize flood status
            flood_status_norm = self._normalize_flood_status(status)

            obs = PMDObservation(
                station_name=canonical_name,
                river=river.title(),
                observed_at=target_date,
                gauge_level_ft=outflow,
                discharge_cusecs=discharge_cusecs,
                flood_status=flood_status_norm,
                forecast_trend="STEADY",
                forecast_range=forecast_range,
                historical_max=historical,
                raw_text=after_station[:100],
            )
            observations.append(obs)
            logger.info(f"Parsed: {canonical_name} - inflow={inflow}K, outflow={outflow}, status={status}")

        logger.info(f"Parsed {len(observations)} observations from FFD bulletin")
        return observations

    def _normalize_flood_status(self, raw: str) -> str:
        raw_upper = raw.upper().strip()
        if "EXCEPTIONALLY" in raw_upper:
            return "EXCEPTIONALLY_HIGH"
        elif "VERY" in raw_upper and "HIGH" in raw_upper:
            return "VERY_HIGH"
        elif raw_upper.startswith("BELOW LOW") or raw_upper == "BELOW LOW":
            return "BELOW_LOW"
        elif "MEDIUM" in raw_upper:
            return "MEDIUM"
        elif "HIGH" in raw_upper:
            return "HIGH"
        elif "LOW" in raw_upper:
            return "LOW"
        elif "NO SIG" in raw_upper:
            return "NORMAL"
        return "NORMAL"

    def close(self):
        self.client.close()


def scrape_pmd_today() -> List[PMDObservation]:
    """Convenience: scrape today's FFD data."""
    scraper = PMDScraper()
    try:
        html = scraper.fetch_bulletin_page()
        return scraper.parse_flood_bulletin(html, date.today())
    finally:
        scraper.close()


if __name__ == "__main__":
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)

    scraper = PMDScraper()
    try:
        html = scraper.fetch_bulletin_page()
        obs = scraper.parse_flood_bulletin(html, date.today())
        print(f"\nParsed {len(obs)} observations:")
        for o in obs:
            print(f"  {o.station_name} ({o.river}): inflow={o.discharge_cusecs}, outflow={o.gauge_level_ft} ft, status={o.flood_status}, forecast={o.forecast_range}")
    finally:
        scraper.close()
