# infrastructure/ingestion/ffd_archive_download.py
# Download FFD bulletin HTML files from the FFD archive.
# Source: https://ffd.pmd.gov.pk/bulletin/bulletin (current) or archive URLs
#
# Usage:
#   python -m infrastructure.ingestion.ffd_archive_download --start-date 2024-01-01 --end-date 2025-12-31
#   python -m infrastructure.ingestion.ffd_archive_download --start-date 2024-06-01 --end-date 2024-08-31 --output-dir raw_archive/ffl
#
# FFD archive pattern: The archive is at https://ffd.pmd.gov.pk/bulletins/archive
# Each bulletin is named FFD_DD-MM-YYYY.html
#
# Note: FFD may rate-limit or block excessive requests.
# This script uses retry logic with exponential backoff.
import io
import logging
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

FFD_BASE = "https://ffd.pmd.gov.pk"
FFD_ARCHIVE_URL = f"{FFD_BASE}/bulletins/archive"
FFD_CURRENT_URL = f"{FFD_BASE}/bulletin/bulletin"


def _build_archive_urls(start_date: date, end_date: date) -> List[tuple]:
    """Build list of (date, url) pairs for FFD bulletins."""
    urls = []
    current = start_date
    while current <= end_date:
        # FFD naming: FFD_DD-MM-YYYY.html
        filename = f"FFD_{current.strftime('%d-%m-%Y')}.html"
        # Try the archive URL pattern
        url = f"{FFD_ARCHIVE_URL}/{filename}"
        urls.append((current, url, filename))
        current += timedelta(days=1)
    return urls


def download_ffd_bulletin(
    client: httpx.Client,
    url: str,
    target_date: date,
    output_dir: Path,
    max_retries: int = 3,
) -> Optional[Path]:
    """Download a single FFD bulletin HTML file."""
    filename = f"FFD_{target_date.strftime('%d-%m-%Y')}.html"
    output_path = output_dir / filename

    # Skip if already downloaded
    if output_path.exists():
        logger.debug(f"Already exists: {filename}")
        return output_path

    @retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=30, min=30, max=300),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch() -> bytes:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content

    try:
        content = _fetch()
        output_path.write_bytes(content)
        logger.info(f"Downloaded: {filename} ({len(content)} bytes)")
        return output_path
    except Exception as e:
        logger.warning(f"Failed to download {filename}: {e}")
        return None


def download_ffd_archive(
    start_date: date,
    end_date: date,
    output_dir: Path = None,
    delay_seconds: float = 2.0,
) -> dict:
    """Download FFD bulletin archive for a date range.
    
    Args:
        start_date: First bulletin date to download
        end_date: Last bulletin date to download
        output_dir: Directory to save HTML files
        delay_seconds: Delay between requests to avoid rate limiting
    
    Returns:
        Summary dict with counts
    """
    if output_dir is None:
        output_dir = Path(__file__).parent / "raw_archive" / "ffl"
    output_dir.mkdir(parents=True, exist_ok=True)

    urls = _build_archive_urls(start_date, end_date)
    logger.info(f"Will attempt to download {len(urls)} bulletins from {start_date} to {end_date}")

    downloaded = 0
    skipped = 0
    failed = 0

    with httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": "IBCP-SCADA/1.0 (water-data-ingestion)"},
    ) as client:
        for i, (target_date, url, filename) in enumerate(urls):
            output_path = output_dir / filename

            # Skip if already exists
            if output_path.exists():
                skipped += 1
                continue

            result = download_ffd_bulletin(client, url, target_date, output_dir)
            if result:
                downloaded += 1
            else:
                failed += 1

            # Rate limiting
            if i < len(urls) - 1:
                time.sleep(delay_seconds)

    summary = {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "total_days": (end_date - start_date).days + 1,
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "output_dir": str(output_dir),
    }

    logger.info(
        f"Download complete: {downloaded} downloaded, {skipped} skipped, {failed} failed"
    )
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download FFD bulletin archive")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "raw_archive" / "ffl",
        help="Output directory for HTML files",
    )
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests (seconds)")
    args = parser.parse_args()

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)

    result = download_ffd_archive(start, end, args.output_dir, args.delay)

    print("\n" + "=" * 60)
    print("FFD Archive Download Summary")
    print("=" * 60)
    print(f"Date range: {result['start_date']} to {result['end_date']}")
    print(f"Total days: {result['total_days']}")
    print(f"Downloaded: {result['downloaded']}")
    print(f"Skipped:    {result['skipped']}")
    print(f"Failed:     {result['failed']}")
    print(f"Output dir: {result['output_dir']}")
