"""
scripts/run_pipeline.py
AquaVision - Orchestrated weekly water pipeline with full run observability.

Every execution is recorded in system.pipeline_runs with a status lifecycle:

    QUEUED -> RUNNING -> SUCCESS | PARTIAL_SUCCESS | FAILED
             (operator abort before RUNNING: CANCELLED)

Per-stage outcomes land in system.pipeline_run_stages (status, counts,
timing, log path). Logs are written under logs/<run_id>/<stage>.log so history
is preserved per run.

Safeguards:
    - Postgres advisory lock (PIPELINE_LOCK_KEY) so two invocations can never
      run the pipeline concurrently - a second process aborts at startup.
    - Per-stage subprocess timeout (PIPELINE_STAGE_TIMEOUT seconds) so a hung
      stage can never leave a run stuck in RUNNING forever.
    - Stale-run sweep at startup: any RUNNING run older than
      PIPELINE_STALE_AFTER is auto-failed before a new run starts.
    - Data-integrity gate for the GEE source: with --with-fetch the orchestrator
      runs the REAL gee.gee_fetch (not a stub). If GEE credentials are absent the
      stage is recorded SKIPPED (never a silent FAILED+continue). If the fetch
      cannot refresh Data/raw/region_features.csv (no creds / GEE error / no
      mtime change) and the cached CSV is older than PIPELINE_MAX_CACHE_DAYS,
      the core stages run with SYNC_DATA_STATUS=STALE so indicators are published
      as quality_status='STALE' instead of 'VALID' - stale data cannot masquerade
      as fresh.

Stages (each is idempotent - upserts, so re-runs never duplicate rows):

    [optional] gee_fetch            refresh Data/raw/region_features.csv from GEE
    sync_indicators                 real WAI indicators -> water_indicators_weekly
    sync_surface_water              NDWI/MNDWI water area -> surface_water_weekly
    predict_weekly                  XGBoost forecast   -> water_predictions_weekly
    run_risk_alerts                 MODEL alerts       -> water_alerts
    [optional] validate_preds       score forecasts against closed actuals

gee_fetch and validate_preds are optional: fetch needs GEE credentials/network
(SKIPPED otherwise), validation needs a closed forecast period (no-op until then).

Usage (run from packages/ml-pipeline):
    python -m scripts.run_pipeline                    # core stages, no fetch
    python -m scripts.run_pipeline --with-fetch       # refresh GEE features first
    python -m scripts.run_pipeline --stage sync_indicators   # single stage
    python -m scripts.run_pipeline --trigger MANUAL
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

ML_ROOT = Path(__file__).resolve().parent.parent
DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"
)
PIPELINE_NAME = "weekly_water_pipeline"
CODE_VERSION = os.getenv("GEE_CODE_VERSION", "1.0.0")
SOURCE_VERSION = os.getenv("GEE_SOURCE_VERSION", "GEE-CHIRPS/ERA5-JRC-2026.8")
MODEL_VERSION = os.getenv("GEE_MODEL_VERSION", "xgb-v1.0")
LOG_DIR = ML_ROOT / "logs"
LOCK_KEY = int(os.getenv("PIPELINE_LOCK_KEY", "1463592275"))  # stable bigint advisory-lock key
STAGE_TIMEOUT = int(os.getenv("PIPELINE_STAGE_TIMEOUT", "1800"))  # seconds per stage
STALE_AFTER = os.getenv("PIPELINE_STALE_AFTER", "2 hours")
MAX_CACHE_DAYS = int(os.getenv("PIPELINE_MAX_CACHE_DAYS", "7"))  # max cached-CSV age before STALE
RAW_CSV = ML_ROOT / "Data" / "raw" / "region_features.csv"
SURFACE_WATER_CSV = ML_ROOT / "Data" / "raw" / "surface_water.csv"

STAGES = ["sync_indicators", "sync_surface_water", "predict_weekly", "run_risk_alerts"]

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL)
    return _engine


def next_run_id(conn) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n = conn.execute(
        text(
            "SELECT count(*) FROM system.pipeline_runs WHERE run_id LIKE :p"
        ).bindparams(p=f"RUN-{day}-%")
    ).scalar() or 0
    return f"RUN-{day}-{n + 1:03d}"


def create_run(trigger: str) -> tuple[int, str]:
    with engine().begin() as conn:
        run_id = next_run_id(conn)
        row = conn.execute(
            text(
                """
                INSERT INTO system.pipeline_runs
                    (pipeline_name, status, run_id, trigger_type, code_version,
                     source_version, model_version, log_path, started_at)
                VALUES (:name, 'QUEUED', :run_id, :trigger, :code, :src, :model,
                        :log_dir, now())
                RETURNING id
                """
            ),
            {"name": PIPELINE_NAME, "run_id": run_id, "trigger": trigger,
             "code": CODE_VERSION, "src": SOURCE_VERSION, "model": MODEL_VERSION,
             "log_dir": str(LOG_DIR)},
        ).first()
        return row[0], run_id


def update_run(run_pk: int, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = run_pk
    with engine().begin() as conn:
        conn.execute(text(f"UPDATE system.pipeline_runs SET {sets} WHERE id = :id"), fields)


def acquire_lock(conn) -> bool:
    """Non-blocking Postgres advisory lock - false means a run is in progress."""
    return bool(conn.execute(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY}
    ).scalar())


def release_lock(conn) -> None:
    conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})


def sweep_stale_runs(stale_after: str = STALE_AFTER) -> int:
    """Auto-fail runs stuck in RUNNING longer than stale_after (self-healing)."""
    with engine().begin() as conn:
        n = conn.execute(
            text(
                """
                UPDATE system.pipeline_runs
                SET status = 'FAILED',
                    error_summary = COALESCE(error_summary, '')
                                     || ' [auto-failed: exceeded ' || :stale || ']',
                    ended_at = now()
                WHERE status = 'RUNNING'
                  AND started_at < now() - (:stale)::interval
                """
            ),
            {"stale": stale_after},
        ).rowcount
    return n


def cancel_run(run_pk: int) -> bool:
    """Abort a QUEUED run before it starts (no-op if already RUNNING/terminal)."""
    with engine().begin() as conn:
        res = conn.execute(
            text(
                """
                UPDATE system.pipeline_runs
                SET status = 'CANCELLED', ended_at = now()
                WHERE id = :id AND status = 'QUEUED'
                """
            ),
            {"id": run_pk},
        )
        return res.rowcount == 1


def _gee_credentials_file() -> Path:
    """Default OAuth credentials file from `earthengine authenticate`."""
    return Path(os.path.expanduser("~/.config/earthengine/credentials"))


def gee_configured() -> bool:
    """True when real GEE auth is available: service-account key env var or the
    saved `earthengine authenticate` OAuth credentials."""
    return bool(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        or os.getenv("EARTHENGINE_TOKEN")
        or _gee_credentials_file().exists()
    )


def csv_mtime() -> float | None:
    """Epoch mtime of the raw features CSV, or None if it doesn't exist."""
    try:
        return RAW_CSV.stat().st_mtime
    except FileNotFoundError:
        return None


def csv_age_days() -> float | None:
    m = csv_mtime()
    if m is None:
        return None
    return (datetime.now(timezone.utc).timestamp() - m) / 86400.0


def record_skipped_stage(run_pk: int, run_id: str, stage: str, log_path: str,
                         reason: str) -> None:
    """Record a stage that was intentionally not executed (e.g. no GEE creds)."""
    now = datetime.now(timezone.utc)
    with engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO system.pipeline_run_stages
                    (run_pk, run_id, stage_name, status, started_at, finished_at,
                     records_read, records_written, records_skipped,
                     warning_count, error_count, log_path)
                VALUES (:run_pk, :run_id, :stage, 'SKIPPED', :started, :finished,
                        0, 0, 0, 0, 0, :log)
                ON CONFLICT (run_id, stage_name) DO UPDATE
                    SET status = EXCLUDED.status, finished_at = EXCLUDED.finished_at,
                        log_path = EXCLUDED.log_path
                """
            ),
            {"run_pk": run_pk, "run_id": run_id, "stage": stage,
             "started": now, "finished": now, "log": log_path},
        )
        conn.execute(
            text(
                """
                UPDATE system.pipeline_runs
                SET error_summary = COALESCE(error_summary, '') || :reason || E'\n'
                WHERE id = :id AND status = 'RUNNING'
                """
            ),
            {"reason": f"[{stage}] SKIPPED: {reason}", "id": run_pk},
        )


def record_stage(run_pk: int, run_id: str, stage: str, summary: dict,
                 log_path: str, started: datetime, finished: datetime) -> None:
    with engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO system.pipeline_run_stages
                    (run_pk, run_id, stage_name, status, started_at, finished_at,
                     records_read, records_written, records_skipped,
                     warning_count, error_count, log_path)
                VALUES (:run_pk, :run_id, :stage, :status, :started, :finished,
                        :read, :written, :skipped, :warn, :err, :log)
                ON CONFLICT (run_id, stage_name) DO UPDATE
                    SET status = EXCLUDED.status, finished_at = EXCLUDED.finished_at,
                        records_read = EXCLUDED.records_read,
                        records_written = EXCLUDED.records_written,
                        records_skipped = EXCLUDED.records_skipped,
                        warning_count = EXCLUDED.warning_count,
                        error_count = EXCLUDED.error_count,
                        log_path = EXCLUDED.log_path
                """
            ),
            {"run_pk": run_pk, "run_id": run_id, "stage": stage,
             "status": summary["status"], "started": started, "finished": finished,
             "read": summary["records_read"], "written": summary["records_written"],
             "skipped": summary["records_skipped"], "warn": summary["warning_count"],
             "err": summary["error_count"], "log": log_path},
        )


def run_stage(run_pk: int, run_id: str, stage: str, module: str | None = None,
              env_extra: dict | None = None) -> dict:
    """Run a stage as a subprocess, capture per-run logs, record the stage row."""
    started = datetime.now(timezone.utc)
    log = LOG_DIR / run_id / f"{stage}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", module or f"scripts.{stage}"]
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    print(f"[pipeline:{run_id}] starting stage: {stage}")
    try:
        with log.open("w", encoding="utf-8") as fh:
            proc = subprocess.run(cmd, cwd=str(ML_ROOT), stdout=fh,
                                  stderr=subprocess.STDOUT, text=True,
                                  env=env, timeout=STAGE_TIMEOUT)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code = -1
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"\n[pipeline] stage exceeded {STAGE_TIMEOUT}s timeout\n")
    finished = datetime.now(timezone.utc)

    output = log.read_text(encoding="utf-8", errors="replace")
    summary = _parse_stage(stage, output, code)
    summary["status"] = (
        "FAILED" if code != 0 else
        ("PARTIAL_SUCCESS" if summary["warning_count"] > 0 else "SUCCESS")
    )
    summary["output"] = output
    record_stage(run_pk, run_id, stage, summary, str(log), started, finished)
    return summary


def _parse_stage(stage: str, output: str, code: int) -> dict:
    summary: dict = {
        "status": "SUCCESS" if code == 0 else "FAILED",
        "records_read": 0, "records_written": 0, "records_skipped": 0,
        "warning_count": 0, "error_count": 0,
    }
    pats = {
        "records_read": r"Read (\d+) rows",
        "records_written": {
            "sync_indicators": r"Upserted (\d+) indicator rows",
            "sync_surface_water": r"(\d+) inserted",
            "predict_weekly": r"Wrote (\d+) predictions",
            "run_risk_alerts": r"Wrote (\d+) alerts",
            "gee_fetch": r"Wrote (\d+) rows ->",
        },
        "records_skipped": {"sync_indicators": r"Skipped (\d+) invalid rows"},
        "warning_count": {"sync_indicators": r"PARTIAL \(incomplete\) periods: (\d+)"},
    }
    for key, mapping in pats.items():
        if isinstance(mapping, str):
            m = re.search(mapping, output)
        else:
            m = re.search(mapping.get(stage, r"(?!x)x"), output)
        if m:
            summary[key] = int(m.group(1))
    if code != 0:
        summary["error_count"] = 1
    return summary


def finalize(run_pk: int, run_id: str, stages: list[dict], data_period: str | None,
             warnings: list[str], errors: list[str]) -> None:
    written = sum(s["records_written"] for s in stages)
    skipped = sum(s["records_skipped"] for s in stages)
    read = sum(s["records_read"] for s in stages)
    warn_n = sum(s["warning_count"] for s in stages)
    err_n = sum(s["error_count"] for s in stages)

    if errors:
        status = "FAILED"
    elif warnings or warn_n > 0:
        status = "PARTIAL_SUCCESS"
    else:
        status = "SUCCESS"

    # keep notes appended earlier (e.g. SKIPPED stages) alongside hard errors
    existing = None
    with engine().connect() as conn:
        existing = conn.execute(
            text("SELECT error_summary FROM system.pipeline_runs WHERE id = :id"),
            {"id": run_pk},
        ).scalar()
    parts = [p for p in (existing, "; ".join(errors[:5])) if p]
    error_summary = " | ".join(parts) or None
    update_run(
        run_pk,
        status=status,
        ended_at=datetime.now(timezone.utc),
        data_period=data_period,
        records_read=read,
        records_written=written,
        records_skipped=skipped,
        warning_count=warn_n + len(warnings),
        error_count=err_n,
        error_summary=error_summary,
        log_path=str(LOG_DIR / run_id),
    )
    print(f"[pipeline:{run_id}] final status: {status} "
          f"(written={written} skipped={skipped} warnings={warn_n + len(warnings)} errors={err_n})")


def main() -> None:
    args = [a for a in sys.argv[1:]]
    with_fetch = "--with-fetch" in args
    single = None
    if "--stage" in args:
        single = args[args.index("--stage") + 1]
    trigger = "MANUAL"
    if "--trigger" in args:
        trigger = args[args.index("--trigger") + 1]
    elif os.getenv("PIPELINE_TRIGGER"):
        trigger = os.getenv("PIPELINE_TRIGGER")
    else:
        trigger = "SCHEDULED" if with_fetch else "BOOTSTRAP"

    # self-heal any previous run that got stuck in RUNNING
    stale = sweep_stale_runs()
    if stale:
        print(f"[pipeline] auto-failed {stale} stale RUNNING run(s)")

    # single global lock: refuse to start if another invocation is mid-run
    lock_conn = engine().connect()
    if not acquire_lock(lock_conn):
        print("[pipeline] another run is in progress; aborting this invocation")
        lock_conn.close()
        return

    try:
        run_pk, run_id = create_run(trigger)
    except Exception as exc:  # noqa: BLE001
        print(f"[pipeline] could not create pipeline run: {exc}")
        release_lock(lock_conn)
        lock_conn.close()
        return

    try:
        update_run(run_pk, status="RUNNING", log_path=str(LOG_DIR / run_id))
        print(f"[pipeline:{run_id}] queued -> running ({trigger})")

        stages = [single] if single else (["gee_fetch"] + STAGES if with_fetch else STAGES)
        stage_results: list[dict] = []
        warnings: list[str] = []
        errors: list[str] = []
        data_period: str | None = None
        stale_data = False  # when True, sync marks indicators STALE instead of VALID

        for stage in stages:
            if stage == "gee_fetch":
                log = LOG_DIR / run_id / "gee_fetch.log"
                if not gee_configured():
                    # No credentials: honest SKIPPED (never a silent FAILED+continue).
                    log.parent.mkdir(parents=True, exist_ok=True)
                    age = csv_age_days()
                    if age is None:
                        reason = "no GEE credentials and no cached CSV"
                    else:
                        reason = f"no GEE credentials; using cached CSV (age {age:.1f}d)"
                    log.write_text(f"[gee_fetch] SKIPPED - {reason}\n")
                    warnings.append(f"gee_fetch: {reason}")
                    record_skipped_stage(run_pk, run_id, "gee_fetch", str(log), reason)
                    if age is None or age > MAX_CACHE_DAYS:
                        stale_data = True
                        warnings.append(f"data source STALE (CSV age {age:.1f}d > "
                                        f"{MAX_CACHE_DAYS}d); indicators will be marked STALE")
                    continue

                # Real GEE fetch. If it does not refresh the CSV, treat as stale.
                before = csv_mtime()
                summary = run_stage(run_pk, run_id, "gee_fetch",
                                    module="gee.gee_fetch")
                after = csv_mtime()
                if summary["status"] != "SUCCESS":
                    warnings.append("gee_fetch failed; using cached CSV")
                    summary["error_count"] = 0
                elif after is None or after == before:
                    warnings.append("gee_fetch ran but did not refresh the CSV")
                    summary["error_count"] = 0
                else:
                    stage_results.append(summary)
                continue

            summary = run_stage(
                run_pk, run_id, stage,
                env_extra={"SYNC_DATA_STATUS": "STALE"} if (stage == "sync_indicators" and stale_data) else None,
            )
            stage_results.append(summary)
            if stage == "sync_indicators":
                m = re.search(r"across (\d{4}-\d{2}-\d{2}) \.\. (\d{4}-\d{2}-\d{2})",
                              summary["output"])
                if m:
                    data_period = m.group(2)[:7]
            if summary["status"] == "FAILED":
                errors.append(f"{stage} failed (stage status {summary['status']})")

        finalize(run_pk, run_id, stage_results, data_period, warnings, errors)
    except Exception as exc:  # noqa: BLE001 - any failure must be observable
        print(f"[pipeline] unexpected failure: {exc}")
        try:
            update_run(run_pk, status="FAILED", ended_at=datetime.now(timezone.utc),
                       error_summary=f"unexpected: {exc}")
        except Exception:  # noqa: BLE001 - DB may be down
            pass
    finally:
        release_lock(lock_conn)
        lock_conn.close()


if __name__ == "__main__":
    main()
