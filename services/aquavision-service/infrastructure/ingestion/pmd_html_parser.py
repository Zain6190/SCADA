# infrastructure/ingestion/pmd_html_parser.py
# Parse FFD/PMD flood bulletin HTML using data-ffd-* attributes.
# Source: https://ffd.pmd.gov.pk/bulletin/bulletin
# This parser extracts headroom data from the structured HTML attributes
# rather than relying on the concatenated text format.
import re
import logging
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Dict

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Station mapping: FFD attribute name → (canonical_name, river)
STATION_MAP = {
    "Tarbela": ("Tarbela Reservoir", "INDUS"),
    "Mangla": ("Mangla Reservoir", "JHELUM"),
    "Kalabagh": ("Kalabagh (Indus)", "INDUS"),
    "Chashma": ("Chashma Barrage", "INDUS"),
    "Taunsa": ("Taunsa Barrage", "INDUS"),
    "Guddu": ("Guddu Barrage", "INDUS"),
    "Sukkur": ("Sukkur Barrage", "INDUS"),
    "Kotri": ("Kotri Barrage", "INDUS"),
    "Nowshera": ("Kabul @ Nowshera", "KABUL"),
    "Marala": ("Chenab @ Marala", "CHENAB"),
    "Punjnad": ("Panjnad", "CHENAB"),
}

# Additional stations monitored but not in our 11 core assets
EXTRA_STATIONS = {
    "Khanki", "Qadirabad", "Trimmu", "Jassar", "Shahdara",
    "Balloki", "Sidhnai", "Sulemanki", "Islam",
}


@dataclass
class FFDObservation:
    """Parsed observation from an FFD bulletin."""
    station_name: str
    canonical_name: str
    river: str
    observed_at: date
    headroom_current: Optional[float] = None  # Current flow (thousands of cusecs)
    headroom_design: Optional[float] = None   # Design capacity
    flood_status: str = "NORMAL"
    levels: Dict[str, float] = None  # Threshold levels

    def __post_init__(self):
        if self.levels is None:
            self.levels = {}


def parse_ffd_html(html: str, target_date: date) -> List[FFDObservation]:
    """Parse FFD bulletin HTML using data-ffd-* attributes.
    
    Extracts structured data from the HTML headroom section:
    - data-ffd-headroom: Station name
    - data-ffd-now: Current flow (thousands of cusecs)
    - data-ffd-design: Design capacity
    - data-ffd-status: Flood status (NORMAL, LOW, MEDIUM, HIGH, etc.)
    - data-ffd-levels: Threshold levels (e.g., "Low:100.0|Medium:150.0|High:200.0")
    """
    soup = BeautifulSoup(html, "html.parser")
    observations = []

    # Find all elements with data-ffd-headroom attribute
    headroom_elements = soup.find_all(attrs={"data-ffd-headroom": True})

    for elem in headroom_elements:
        station_name = elem.get("data-ffd-headroom", "").strip()
        if not station_name:
            continue

        # Extract current value
        now_str = elem.get("data-ffd-now", "")
        headroom_current = None
        if now_str:
            try:
                headroom_current = float(now_str)
            except ValueError:
                logger.warning(f"Cannot parse data-ffd-now='{now_str}' for {station_name}")

        # Extract design capacity
        design_str = elem.get("data-ffd-design", "")
        headroom_design = None
        if design_str:
            try:
                headroom_design = float(design_str)
            except ValueError:
                pass

        # Extract flood status
        flood_status = elem.get("data-ffd-status", "NORMAL").upper()

        # Extract threshold levels
        levels = {}
        levels_str = elem.get("data-ffd-levels", "")
        if levels_str:
            for part in levels_str.split("|"):
                if ":" in part:
                    key, val = part.split(":", 1)
                    try:
                        levels[key.strip()] = float(val.strip())
                    except ValueError:
                        pass

        # Map to canonical name
        canonical, river = STATION_MAP.get(station_name, (station_name, "UNKNOWN"))

        obs = FFDObservation(
            station_name=station_name,
            canonical_name=canonical,
            river=river,
            observed_at=target_date,
            headroom_current=headroom_current,
            headroom_design=headroom_design,
            flood_status=_normalize_status(flood_status),
            levels=levels,
        )
        observations.append(obs)
        logger.debug(f"Parsed: {station_name} → {canonical} = {headroom_current}K cusecs, status={flood_status}")

    logger.info(f"Parsed {len(observations)} stations from FFD bulletin HTML (attribute-based)")
    return observations


def _text_fallback_parse(html: str, target_date: date, existing_stations: set) -> List[FFDObservation]:
    """Fallback parser: extract stations from plain text that weren't found via attributes.

    FFD bulletins sometimes list Nowshera/Kabul in the text body but not as
    data-ffd-headroom attributes. This parser finds those missing stations.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()

    observations = []

    # Search for stations in text that weren't found via attributes
    for search_key, (canonical_name, river) in STATION_MAP.items():
        if search_key in existing_stations:
            continue
        if search_key not in text:
            continue

        idx = text.find(search_key)
        after = text[idx + len(search_key):]

        # Find a status keyword
        status_match = re.search(
            r'(Below Low|Low|Medium|High|Very High|Exceptionally High|No sig)',
            after[:200],
        )
        if not status_match:
            continue

        before_status = after[:status_match.start()]
        status = status_match.group(0)

        # Extract numbers before status — pattern: "37.237.2" = level + discharge
        # Find all floats in before_status
        nums = re.findall(r'[\d.]+', before_status)
        gauge_level = None
        discharge_k = None  # thousands of cusecs
        if len(nums) >= 2:
            try:
                gauge_level = float(nums[0])
                discharge_k = float(nums[1])
            except ValueError:
                pass
        elif len(nums) == 1:
            try:
                discharge_k = float(nums[0])
            except ValueError:
                pass

        obs = FFDObservation(
            station_name=search_key,
            canonical_name=canonical_name,
            river=river,
            observed_at=target_date,
            headroom_current=discharge_k,
            headroom_design=None,
            flood_status=_normalize_status(status.upper()),
            levels={},
        )
        observations.append(obs)
        logger.info(f"Text fallback parsed: {search_key} = {discharge_k}K cusecs, status={status}")

    return observations


def _normalize_status(raw: str) -> str:
    """Normalize FFD flood status to standard format."""
    raw = raw.upper().strip()
    if "EXCEPTIONALLY" in raw:
        return "EXCEPTIONALLY_HIGH"
    elif "VERY" in raw and "HIGH" in raw:
        return "VERY_HIGH"
    elif raw.startswith("BELOW LOW") or raw == "BELOW_LOW" or raw == "BL":
        return "BELOW_LOW"
    elif "MEDIUM" in raw or raw == "M":
        return "MEDIUM"
    elif "HIGH" in raw or raw == "H":
        return "HIGH"
    elif "LOW" in raw or raw == "L":
        return "LOW"
    elif "NO SIG" in raw or raw == "NORMAL":
        return "NORMAL"
    return "NORMAL"
