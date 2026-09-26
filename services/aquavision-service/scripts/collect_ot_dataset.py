# Collect the official Indus series the Soft OT twin replays.
# IRSA daily PDFs supply level, inflow, outflow, and canal withdrawals.
# FFD bulletins fill river-station gaps. Gate percent is derived, never measured.
#
#   python scripts/collect_ot_dataset.py --days 90
#   python scripts/collect_ot_dataset.py --days 90 --skip-ingest
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
OT_ROOT = REPO / "services" / "ot-runtime"
for path in (str(ROOT), str(OT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from infrastructure.ingestion.irsa_scraper import parse_irsa_pdf  # noqa: E402
from ot_runtime.series import (  # noqa: E402
    ASSET_NAME_TO_ID,
    OfficialDay,
    canal_offtake_cusecs,
    complete_day,
    fill_gauge_from_ffd,
)

logger = logging.getLogger("aquavision.ot.dataset")

IRSA_URL = "http://pakirsa.gov.pk/Doc/Data{date_str}.pdf"
CSV_PATH = REPO / "data" / "ot" / "indus_ot_daily.csv"
PDF_DIR = ROOT / "infrastructure" / "ingestion" / "raw_archive" / "irsa"
FFD_DIR = ROOT / "infrastructure" / "ingestion" / "raw_archive" / "ffl"
COLUMNS = [
    "observed_on",
    "asset_id",
    "device_code",
    "level_ft",
    "inflow_cusecs",
    "outflow_cusecs",
    "discharge_cusecs",
    "canal_offtake_cusecs",
    "gate_pct_derived",
    "source_authority",
    "source_url",
]


def _download_pdf(target: date) -> tuple[bytes, str] | None:
    url = IRSA_URL.format(date_str=target.strftime("%d-%m-%Y"))
    try:
        response = httpx.get(url, timeout=25.0, follow_redirects=True, headers={"User-Agent": "IBCP-SCADA/1.0"})
    except httpx.HTTPError as exc:
        logger.warning("IRSA download failed for %s: %s", target, exc)
        return None
    if response.status_code == 404:
        logger.info("IRSA PDF missing for %s", target)
        return None
    if response.status_code >= 400:
        logger.warning("IRSA HTTP %s for %s", response.status_code, target)
        return None
    body = response.content
    if not body.startswith(b"%PDF-") or len(body) < 1000:
        logger.warning("IRSA response for %s is not a PDF", target)
        return None
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    (PDF_DIR / f"IRSA_{target.strftime('%d-%m-%Y')}.pdf").write_bytes(body)
    return body, url


def days_from_pdf(pdf_path: Path, target: date, source_url: str) -> list[OfficialDay]:
    observations = parse_irsa_pdf(str(pdf_path), target, source_url)
    found: dict[int, OfficialDay] = {}
    for obs in observations:
        asset_id = ASSET_NAME_TO_ID.get(obs.asset_name)
        if asset_id is None:
            continue
        inflow = obs.inflow_cusecs if obs.inflow_cusecs is not None else obs.upstream_discharge_cusecs
        outflow = obs.outflow_cusecs if obs.outflow_cusecs is not None else obs.downstream_discharge_cusecs
        discharge = obs.discharge_cusecs if obs.discharge_cusecs is not None else outflow
        found[asset_id] = complete_day(OfficialDay(
            observed_on=target,
            asset_id=asset_id,
            level_ft=obs.water_level_ft,
            inflow_cusecs=inflow,
            outflow_cusecs=outflow,
            discharge_cusecs=discharge,
            canal_offtake_cusecs=canal_offtake_cusecs(obs.canal_withdrawals),
            source_authority="IRSA",
            source_url=source_url,
        ))
    return list(found.values())


def apply_ffd_archive(days: list[OfficialDay]) -> list[OfficialDay]:
    if not FFD_DIR.exists():
        return days
    try:
        from infrastructure.ingestion.pmd_html_parser import parse_ffd_html
    except Exception as exc:
        logger.warning("FFD parser unavailable: %s", exc)
        return days
    by_key = {(day.observed_on, day.asset_id): day for day in days}
    for path in sorted(FFD_DIR.glob("FFD_*.html")):
        stamp = path.stem.replace("FFD_", "")
        try:
            target = datetime.strptime(stamp, "%d-%m-%Y").date()
        except ValueError:
            continue
        try:
            parsed = parse_ffd_html(path.read_text(encoding="utf-8", errors="replace"), target)
        except Exception as exc:
            logger.warning("FFD parse skipped %s: %s", path.name, exc)
            continue
        for obs in parsed:
            asset_id = ASSET_NAME_TO_ID.get(obs.canonical_name)
            if asset_id is None:
                continue
            discharge = None if obs.headroom_current is None else float(obs.headroom_current) * 1000.0
            current = by_key.get((target, asset_id))
            if current is None:
                current = complete_day(OfficialDay(
                    observed_on=target,
                    asset_id=asset_id,
                    source_authority="FFD",
                    source_url="https://ffd.pmd.gov.pk/bulletins/archive",
                ))
                by_key[(target, asset_id)] = current
            fill_gauge_from_ffd(current, None, discharge, "https://ffd.pmd.gov.pk/bulletins/archive")
            complete_day(current)
    return list(by_key.values())


def write_csv(days: list[OfficialDay], path: Path = CSV_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(days, key=lambda day: (day.observed_on, day.asset_id))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for day in ordered:
            writer.writerow(complete_day(day).as_csv_row())
    return path


def upsert_process_days(days: list[OfficialDay]) -> int:
    from sqlalchemy import text
    from infrastructure.db.engine import SessionLocal

    if SessionLocal is None:
        return 0
    written = 0
    with SessionLocal() as db:
        for day in days:
            complete_day(day)
            db.execute(text("""
                INSERT INTO aquavision.water_ot_process_days (
                    observed_on, asset_id, device_code, level_ft, inflow_cusecs,
                    outflow_cusecs, discharge_cusecs, canal_offtake_cusecs,
                    gate_pct_derived, source_authority, source_url
                ) VALUES (
                    :observed_on, :asset_id, :device_code, :level_ft, :inflow_cusecs,
                    :outflow_cusecs, :discharge_cusecs, :canal_offtake_cusecs,
                    :gate_pct_derived, :source_authority, :source_url
                )
                ON CONFLICT (observed_on, asset_id) DO UPDATE SET
                    device_code = EXCLUDED.device_code,
                    level_ft = EXCLUDED.level_ft,
                    inflow_cusecs = EXCLUDED.inflow_cusecs,
                    outflow_cusecs = EXCLUDED.outflow_cusecs,
                    discharge_cusecs = EXCLUDED.discharge_cusecs,
                    canal_offtake_cusecs = EXCLUDED.canal_offtake_cusecs,
                    gate_pct_derived = EXCLUDED.gate_pct_derived,
                    source_authority = EXCLUDED.source_authority,
                    source_url = EXCLUDED.source_url
            """), day.as_csv_row())
            written += 1
        db.commit()
    return written


def collect(days_back: int, ingest_official: bool) -> dict:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days_back - 1)
    collected: list[OfficialDay] = []
    downloaded = 0
    missing = 0
    current = start
    while current <= end:
        archive = PDF_DIR / f"IRSA_{current.strftime('%d-%m-%Y')}.pdf"
        url = IRSA_URL.format(date_str=current.strftime("%d-%m-%Y"))
        if not archive.exists():
            fetched = _download_pdf(current)
            if fetched is None:
                missing += 1
                current += timedelta(days=1)
                continue
            downloaded += 1
        try:
            collected.extend(days_from_pdf(archive, current, url))
        except Exception as exc:
            logger.warning("Parse failed for %s: %s", current, exc)
            missing += 1
        if ingest_official and archive.exists():
            try:
                from infrastructure.ingestion.irsa_ingest import ingest_irsa_pdf
                ingest_irsa_pdf(str(archive), current, url)
            except Exception as exc:
                logger.warning("Official ingest skipped for %s: %s", current, exc)
                ingest_official = False
        current += timedelta(days=1)
    collected = apply_ffd_archive(collected)
    csv_path = write_csv(collected)
    stored = 0
    try:
        stored = upsert_process_days(collected)
    except Exception as exc:
        logger.warning("Process-day table not updated: %s", exc)
    return {
        "csv": str(csv_path),
        "rows": len(collected),
        "downloaded": downloaded,
        "missing": missing,
        "stored": stored,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--skip-ingest", action="store_true")
    args = parser.parse_args()
    result = collect(args.days, ingest_official=not args.skip_ingest)
    print(result)


if __name__ == "__main__":
    main()
