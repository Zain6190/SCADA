"""
Parse FFD bulletin PDFs and ingest observations into water_observations.
Extracts: date, station inflow/outflow, Tarbela/Mangla reservoir levels.
"""
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pdfplumber
from sqlalchemy import text

sys.path.insert(0, "/app")
from infrastructure.db.engine import SessionLocal

PDF_DIR = Path("/app/infrastructure/ingestion/raw_archive/ffl_pdfs")

# Map FFD station names to asset IDs
STATION_MAP = {
    "tarbela": 1,
    "mangla": 2,
    "chashma": 3,
    "kalabagh": 4,
    "taunsa": 5,
    "guddu": 6,
    "sukkur": 7,
    "kotri": 8,
    "nowshera": 9,  # Kabul @ Nowshera
    "marala": 10,   # Chenab @ Marala
    "panjnad": 11,
}

# Also handle river + station combinations
RIVER_STATION_MAP = {
    "indus": {
        "tarbela": 1, "kalabagh": 4, "chashma": 3,
        "taunsa": 5, "guddu": 6, "sukkur": 7, "kotri": 8,
    },
    "kabul": {"nowshera": 9},
    "jhelum": {"mangla": 2},
    "chenab": {"marala": 10},
    "indus": {
        "tarbela": 1, "kalabagh": 4, "chashma": 3,
        "taunsa": 5, "guddu": 6, "sukkur": 7, "kotri": 8,
    },
}


def parse_bulletin_date(text_content):
    """Extract date from FFD bulletin text. Format: 'Dated: 20th August-2026'"""
    match = re.search(r'Dated:\s*\d{1,2}(?:st|nd|rd|th)\s+(\w+)-(\d{4})', text_content)
    if match:
        month_str, year = match.groups()
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        month = month_map.get(month_str.lower())
        if month:
            # Find the day from the same pattern
            day_match = re.search(r'Dated:\s*(\d{1,2})', text_content)
            if day_match:
                return date(int(year), month, int(day_match.group(1)))
    return None


def parse_reservoir_levels(text_content):
    """Extract Tarbela and Mangla reservoir levels from text."""
    levels = {}
    # Tarbela: "Level 1550.00 ft"
    t_match = re.search(r'TARBELA.*?Level\s+([\d.]+)\s*ft', text_content, re.DOTALL)
    if t_match:
        levels[1] = float(t_match.group(1))  # Tarbela
    # Mangla: "Level 1214.05 ft"
    m_match = re.search(r'MANGLA.*?Level\s+([\d.]+)\s*ft', text_content, re.DOTALL)
    if m_match:
        levels[2] = float(m_match.group(1))  # Mangla
    return levels


def parse_flood_table(pdf):
    """Parse the quantitative flood forecast table (page 4)."""
    observations = []
    if len(pdf.pages) < 4:
        return observations
    
    page = pdf.pages[3]  # Page 4 (0-indexed)
    tables = page.extract_tables()
    
    for table in tables:
        if not table or len(table) < 3:
            continue
        # The main data table has: RIVERS | Stations | Inflow | Outflow | Forecast | Level | Historical | Year | Season
        for row in table:
            if not row or len(row) < 4:
                continue
            # Check if this looks like a data row (has numbers)
            river = (row[0] or "").strip().upper()
            station = (row[1] or "").strip()
            
            # Find which asset this maps to
            asset_id = None
            station_lower = station.lower()
            for key, aid in STATION_MAP.items():
                if key in station_lower:
                    asset_id = aid
                    break
            
            if asset_id is None:
                continue
            
            # Parse inflow (column 2, in thousands of cusecs)
            inflow = None
            outflow = None
            try:
                if row[2] and row[2].strip():
                    inflow = float(row[2].strip().replace(",", "")) * 1000
            except (ValueError, IndexError):
                pass
            
            try:
                if row[3] and row[3].strip():
                    outflow = float(row[3].strip().replace(",", "")) * 1000
            except (ValueError, IndexError):
                pass
            
            if inflow is not None or outflow is not None:
                observations.append({
                    "asset_id": asset_id,
                    "inflow": inflow,
                    "outflow": outflow,
                })
    
    return observations


def ingest_pdf(pdf_path, db, source_id):
    """Parse and ingest a single FFD PDF."""
    try:
        pdf = pdfplumber.open(str(pdf_path))
    except Exception as e:
        print(f"  ERROR opening {pdf_path.name}: {e}")
        return 0
    
    # Get first page text for date and reservoir levels
    first_text = pdf.pages[0].extract_text() if pdf.pages else ""
    all_text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    
    # Parse date
    obs_date = parse_bulletin_date(first_text)
    if not obs_date:
        print(f"  SKIP {pdf_path.name}: could not parse date")
        pdf.close()
        return 0
    
    obs_dt = datetime(obs_date.year, obs_date.month, obs_date.day, 
                      tzinfo=timezone.utc)
    
    # Parse observations
    flood_obs = parse_flood_table(pdf)
    reservoir_levels = parse_reservoir_levels(all_text)
    pdf.close()
    
    inserted = 0
    
    # Store reservoir levels
    for asset_id, level_ft in reservoir_levels.items():
        existing = db.execute(text("""
            SELECT id FROM aquavision.water_observations
            WHERE asset_id = :aid AND observed_at = :obs_at AND source_id = :sid
        """), {"aid": asset_id, "obs_at": obs_dt, "sid": source_id}).fetchone()
        
        if not existing:
            db.execute(text("""
                INSERT INTO aquavision.water_observations
                    (asset_id, source_id, observed_at, water_level_ft, 
                     data_status, data_origin, source_priority, created_at)
                VALUES (:aid, :sid, :obs_at, :level,
                        'FFD_BULLETIN', 'REAL', 2, NOW())
            """), {"aid": asset_id, "sid": source_id, "obs_at": obs_dt, "level": level_ft})
            inserted += 1
    
    # Store flood observations (inflow/outflow)
    for obs in flood_obs:
        asset_id = obs["asset_id"]
        # Skip if already stored as reservoir level
        if asset_id in reservoir_levels:
            continue
            
        existing = db.execute(text("""
            SELECT id FROM aquavision.water_observations
            WHERE asset_id = :aid AND observed_at = :obs_at AND source_id = :sid
        """), {"aid": asset_id, "obs_at": obs_dt, "sid": source_id}).fetchone()
        
        if not existing:
            db.execute(text("""
                INSERT INTO aquavision.water_observations
                    (asset_id, source_id, observed_at, inflow_cusecs, outflow_cusecs,
                     data_status, data_origin, source_priority, created_at)
                VALUES (:aid, :sid, :obs_at, :inflow, :outflow,
                        'FFD_BULLETIN', 'REAL', 2, NOW())
            """), {
                "aid": asset_id, "sid": source_id, "obs_at": obs_dt,
                "inflow": obs["inflow"], "outflow": obs["outflow"]
            })
            inserted += 1
    
    return inserted


def main():
    db = SessionLocal()
    
    # Get or create FFD source
    source = db.execute(text("""
        SELECT id FROM aquavision.water_sources WHERE authority = 'FFD/PMD'
    """)).fetchone()
    if not source:
        db.execute(text("""
            INSERT INTO aquavision.water_sources (authority, source_url, source_type, update_frequency, description)
            VALUES ('FFD/PMD', 'https://ffd.pmd.gov.pk', 'PDF_BULLETIN', 'DAILY', 'Pakistan Meteorological Department - Flood Forecasting Division')
        """))
        db.flush()
        source = db.execute(text("SELECT id FROM aquavision.water_sources WHERE authority = 'FFD/PMD'")).fetchone()
    source_id = source[0]
    
    # Process all PDFs
    pdf_files = sorted(PDF_DIR.glob("FFD_*.pdf"))
    print(f"Found {len(pdf_files)} PDF files")
    
    total_inserted = 0
    for pdf_path in pdf_files:
        print(f"Processing {pdf_path.name}...")
        count = ingest_pdf(pdf_path, db, source_id)
        total_inserted += count
        print(f"  Inserted {count} rows")
    
    db.commit()
    db.close()
    print(f"\n=== Total inserted: {total_inserted} rows ===")


if __name__ == "__main__":
    main()
