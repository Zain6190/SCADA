# infrastructure/ingestion/irsa_downloader.py
# Automated IRSA Daily Water Situation PDF downloader + ingestion.
# Fetches from http://pakirsa.gov.pk/Doc/Data{DD-MM-YYYY}.pdf
# Includes retry logic, PDF validation, and proper error handling.
import hashlib
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from infrastructure.ingestion.irsa_ingest import ingest_irsa_pdf

logger = logging.getLogger(__name__)

IRSA_URL_TEMPLATE = "http://pakirsa.gov.pk/Doc/Data{date_str}.pdf"
RAW_ARCHIVE_DIR = Path(__file__).parent / "raw_archive" / "irsa"


def validate_pdf_bytes(pdf_bytes: bytes) -> tuple[bool, str]:
    """Validate downloaded PDF bytes.
    
    Checks:
    - PDF magic bytes (%PDF-)
    - Minimum file size (likely not an error page)
    - Maximum file size (sanity check)
    
    Returns:
        (is_valid, error_message)
    """
    if len(pdf_bytes) < 1000:
        return False, f"File too small ({len(pdf_bytes)} bytes), likely not a valid PDF"
    
    if not pdf_bytes[:5] == b'%PDF-':
        return False, "Not a PDF file (missing %PDF- magic bytes)"
    
    if len(pdf_bytes) > 10_000_000:
        return False, f"File unexpectedly large ({len(pdf_bytes)} bytes)"
    
    return True, "OK"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=60, min=60, max=900),  # 1min, 2min, 4min
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _download_with_retry(url: str) -> httpx.Response:
    """Download with retry logic for transient errors."""
    client = httpx.Client(
        timeout=60.0,
        follow_redirects=True,
        headers={"User-Agent": "IBCP-SCADA/1.0 (water-data-ingestion)"},
    )
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp
    finally:
        client.close()


def download_irsa_pdf(target_date: date, archive: bool = True) -> tuple[bytes, str]:
    """Download IRSA daily PDF with retry and validation.
    
    Returns (pdf_bytes, url).
    
    Raises:
        FileNotFoundError: PDF doesn't exist (not published yet)
        ValueError: Downloaded content is not a valid PDF
        httpx.HTTPStatusError: Server error after retries exhausted
    """
    date_str = target_date.strftime("%d-%m-%Y")
    url = IRSA_URL_TEMPLATE.format(date_str=date_str)

    try:
        resp = _download_with_retry(url)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise FileNotFoundError(
                f"IRSA PDF not found for {target_date} (may not be published yet). "
                f"URL: {url}"
            )
        raise

    pdf_bytes = resp.content

    # Validate PDF content
    is_valid, error_msg = validate_pdf_bytes(pdf_bytes)
    if not is_valid:
        raise ValueError(f"Invalid PDF content for {target_date}: {error_msg}")

    if archive:
        RAW_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        archive_path = RAW_ARCHIVE_DIR / f"IRSA_{date_str}.pdf"
        archive_path.write_bytes(pdf_bytes)
        logger.info(f"Archived PDF to {archive_path}")

    return pdf_bytes, url


def auto_ingest_irsa(target_date: date = None) -> dict:
    """Download + parse + ingest IRSA PDF for a given date.

    If target_date is None, uses yesterday (IRSA publishes next-day data).
    Returns summary dict with fetch_status field.
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    # 1. Download
    logger.info(f"Downloading IRSA PDF for {target_date}...")
    try:
        pdf_bytes, url = download_irsa_pdf(target_date)
        fetch_status = "SUCCESS"
    except FileNotFoundError as e:
        logger.warning(str(e))
        return {
            "error": str(e),
            "date": str(target_date),
            "fetch_status": "FAILED",
        }
    except ValueError as e:
        logger.error(str(e))
        return {
            "error": str(e),
            "date": str(target_date),
            "fetch_status": "FAILED",
        }
    except Exception as e:
        logger.error(f"Download failed after retries: {e}")
        return {
            "error": str(e),
            "date": str(target_date),
            "fetch_status": "FAILED",
        }

    # 2. Write temp file for parser (parser expects file path)
    RAW_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = RAW_ARCHIVE_DIR / f"IRSA_{target_date.strftime('%d-%m-%Y')}.pdf"
    temp_path.write_bytes(pdf_bytes)

    # 3. Ingest
    logger.info(f"Ingesting {len(pdf_bytes)} bytes for {target_date}...")
    result = ingest_irsa_pdf(str(temp_path), target_date, url)
    result["fetch_status"] = fetch_status
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
