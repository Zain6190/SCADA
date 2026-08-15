# infrastructure/ingestion/irsa_downloader.py
# Automated IRSA Daily Water Situation PDF downloader + ingestion.
# Fetches from http://pakirsa.gov.pk/Doc/Data{DD-MM-YYYY}.pdf
import hashlib
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from infrastructure.ingestion.irsa_ingest import ingest_irsa_pdf

logger = logging.getLogger(__name__)

IRSA_URL_TEMPLATE = "http://pakirsa.gov.pk/Doc/Data{date_str}.pdf"
RAW_ARCHIVE_DIR = Path(__file__).parent / "raw_archive" / "irsa"


def download_irsa_pdf(target_date: date, archive: bool = True) -> tuple[bytes, str]:
    """Download IRSA daily PDF. Returns (pdf_bytes, url).

    Raises FileNotFoundError if the PDF doesn't exist yet (IRSA publishes
    around 06:00-07:00 PKT; calling before that will fail).
    """
    date_str = target_date.strftime("%d-%m-%Y")
    url = IRSA_URL_TEMPLATE.format(date_str=date_str)

    client = httpx.Client(
        timeout=60.0,
        follow_redirects=True,
        headers={"User-Agent": "IBCP-SCADA/1.0 (water-data-ingestion)"},
    )

    try:
        resp = client.get(url)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise FileNotFoundError(
                f"IRSA PDF not found for {target_date} (may not be published yet). "
                f"URL: {url}"
            )
        raise
    finally:
        client.close()

    pdf_bytes = resp.content

    if archive:
        RAW_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        archive_path = RAW_ARCHIVE_DIR / f"IRSA_{date_str}.pdf"
        archive_path.write_bytes(pdf_bytes)
        logger.info(f"Archived PDF to {archive_path}")

    return pdf_bytes, url


def auto_ingest_irsa(target_date: date = None) -> dict:
    """Download + parse + ingest IRSA PDF for a given date.

    If target_date is None, uses yesterday (IRSA publishes next-day data).
    Returns summary dict.
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    # 1. Download
    logger.info(f"Downloading IRSA PDF for {target_date}...")
    try:
        pdf_bytes, url = download_irsa_pdf(target_date)
    except FileNotFoundError as e:
        logger.warning(str(e))
        return {"error": str(e), "date": str(target_date)}

    # 2. Write temp file for parser (parser expects file path)
    RAW_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = RAW_ARCHIVE_DIR / f"IRSA_{target_date.strftime('%d-%m-%Y')}.pdf"
    temp_path.write_bytes(pdf_bytes)

    # 3. Ingest
    logger.info(f"Ingesting {len(pdf_bytes)} bytes for {target_date}...")
    result = ingest_irsa_pdf(str(temp_path), target_date, url)
    logger.info(f"Result: {result}")

    return result


def backfill_irsa(start_date: date, end_date: date = None) -> list[dict]:
    """Download + ingest IRSA PDFs for a date range.

    Useful for filling historical gaps.
    """
    if end_date is None:
        end_date = date.today() - timedelta(days=1)

    results = []
    current = start_date
    while current <= end_date:
        # Skip weekends (IRSA may not publish on weekends)
        result = auto_ingest_irsa(current)
        results.append(result)
        current += timedelta(days=1)

    return results


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        # Backfill last 30 days
        start = date.today() - timedelta(days=30)
        results = backfill_irsa(start)
        stored = sum(r.get("stored", 0) for r in results)
        errors = sum(1 for r in results if "error" in r)
        print(f"\nBackfill complete: {stored} observations stored, {errors} errors")
    else:
        # Single day (yesterday)
        result = auto_ingest_irsa()
        print(f"\nResult: {result}")
