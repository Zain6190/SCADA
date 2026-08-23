"""Re-ingest all real data sources into fresh DB."""
import os
os.environ["DATABASE_URL"] = "postgresql://postgres:1234@localhost:5433/ibcp_scada"
os.environ["PGPASSWORD"] = "1234"

from pathlib import Path
from datetime import date, datetime
from sqlalchemy import create_engine, text

engine = create_engine("postgresql://postgres:1234@localhost:5433/ibcp_scada")

# 1. IRSA PDFs from archive
print("=" * 60)
print("IRSA PDF INGESTION")
print("=" * 60)
from infrastructure.ingestion.irsa_ingest import ingest_irsa_pdf

archive = Path("infrastructure/ingestion/raw_archive/irsa")
total_stored = 0
total_skipped = 0
for pdf in sorted(archive.glob("IRSA_*.pdf")):
    name = pdf.stem
    date_str = name.replace("IRSA_", "")
    d = datetime.strptime(date_str, "%d-%m-%Y").date()
    try:
        r = ingest_irsa_pdf(str(pdf), d)
        s = r.get("stored", 0)
        sk = r.get("skipped", 0)
        total_stored += s
        total_skipped += sk
        print(f"  {date_str}: stored={s}, skipped={sk}")
    except Exception as e:
        print(f"  {date_str}: ERROR - {e}")

print(f"IRSA total: stored={total_stored}, skipped={total_skipped}")

# 2. FFD HTML from archive
print()
print("=" * 60)
print("FFD HTML INGESTION")
print("=" * 60)
from infrastructure.ingestion.ffd_bulk_ingest import ingest_ffd_html_file

ffd_archive = Path("infrastructure/ingestion/raw_archive/ffl")
total_ffd = 0
for html_file in sorted(ffd_archive.glob("FFD_*.html")):
    try:
        r = ingest_ffd_html_file(html_file)
        s = r.get("stored", 0)
        total_ffd += s
        print(f"  {html_file.name}: stored={s}")
    except Exception as e:
        print(f"  {html_file.name}: ERROR - {e}")

print(f"FFD total: stored={total_ffd}")

# 3. Summary
print()
print("=" * 60)
print("FINAL SUMMARY")
print("=" * 60)
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT source, COUNT(*) as cnt 
        FROM aquavision.water_observations 
        GROUP BY source ORDER BY cnt DESC
    """))
    total = 0
    for row in result:
        print(f"  {row[0]}: {row[1]}")
        total += row[1]
    print(f"  TOTAL: {total}")
