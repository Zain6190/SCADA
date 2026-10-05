# 03 — Scheduler and Data Pipelines

## 1. Design

The scheduler is a single-process Python program:

* File: `services/aquavision-service/scheduler/main.py`
* Library: the lightweight `schedule` package (`scheduler/main.py:38`) — chosen over
  APScheduler/Celery: no broker, no extra service, trivially inspectable in a defence demo.
* Entry point: `if __name__ == "__main__"` block (`main.py:533`), started inside the
  container as `python -m scheduler.main` (`docker-compose.yml:80`), sharing the API image
  so code and migrations never diverge.
* Main loop (`main.py:590-595`):

```python
while True:
    try:
        schedule.run_pending()
    except Exception as exc:
        logger.exception(...)
    time.sleep(60)
```

Each job is wrapped so a single failure cannot kill the loop.

## 2. Concurrency control

| Mechanism | Where | Purpose |
|-----------|-------|---------|
| Postgres advisory lock | `acquire_pipeline_lock` (`main.py:59-63`), key = `hash(pipeline_type) % 2**31` | prevents duplicate concurrent runs of the same pipeline (API-triggered and scheduled runs share the lock) |
| Release | `release_pipeline_lock` (`main.py:66-69`) | explicit unlock in `finally`-style paths |
| Run ledger | `create_pipeline_run` (`main.py:97`) | every job writes a row to `aquavision.pipeline_runs` (status, duration, error, code version) |
| Heartbeat | `update_heartbeat` (`main.py:72-78`) | upserts `aquavision.scheduler_heartbeats` every 5 minutes |
| Missed-run catch-up | `job_wai_catchup` (`main.py:265-301`) | `schedule` has no misfire handling; after a container restart this job runs the WAI pipeline with `trigger="CATCHUP"` if the last run is stale |

## 3. Job schedule (exact)

Registrations are at `scheduler/main.py:535-575`:

| Time (PKT) | Job | Function (line) | What it does |
|-------------|-----|-----------------|--------------|
| Daily 01:00 | `job_ingest_ffd` | `main.py:169` | scrape FFD/PMD bulletin |
| Daily 01:30 | `job_ingest_irsa` | `main.py:137` | download/parse yesterday's IRSA PDF |
| Daily 02:00 | `job_backfill_inflow` | `main.py:456` | fill missing inflow series |
| Daily 02:30 | `job_run_predictions` | `main.py:498` | run weekly prediction generation |
| Daily 03:00 | `job_compute_accuracy` | `main.py:477` | compare forecasts vs observations |
| Daily 04:15 | `job_wai_catchup` | `main.py:265` | WAI freshness/catch-up after restarts |
| Daily 04:30 | `job_refresh_gee_features` | `main.py:425` | Google Earth Engine feature refresh |
| Every 6 h | `job_refresh_weather` | `main.py:308` | weather forecast refresh |
| Every 5 min | `update_heartbeat` | `main.py:72` | liveness heartbeat |
| Every 5 min | `job_alert_sla_scan` | `main.py:519` | alert SLA escalation scan |
| Sun 03:00 | `job_train_models` | `main.py:199` | train ML models (locked) |
| Sun 03:30 | `job_retrain_all_models` | `main.py:332` | full retraining |
| Sun 03:45 | `job_validate_all_models` | `main.py:363` | validation backtests |
| Sun 03:58 | `job_register_models` | `main.py:394` | register validated models |
| Sun 04:00 | `job_run_wai_pipeline` | `main.py:225` | full WAI pipeline via `subprocess` (locked) |

On startup the scheduler immediately (`main.py:581-588`): writes a heartbeat, runs the
initial IRSA ingestion, then checks WAI freshness.

## 4. Operational behaviour

* Status: `docker ps` shows `ibcp-scheduler` with `(healthy)`; heartbeat rows are written
  every 5 minutes (`scheduler_heartbeats.status = RUNNING`).
* History: every execution appears in `aquavision.pipeline_runs`
  (`pipeline_type, status, started_at, completed_at, duration_seconds`).
* Logs: `docker compose logs -f scheduler` or `.\scripts\Start-Scheduler.ps1 -Logs`.
* Start modes:
  * Container: `.\scripts\Start-Scheduler.ps1` (default, `docker compose up -d scheduler`).
  * Foreground/debug: `.\scripts\Start-Scheduler.ps1 -Mode Local` — loads `DATABASE_URL`
    from `.env` and runs `python -m scheduler.main`.

## 5. Live verification (2026-10-05)

```powershell
.\scripts\Query-DB.ps1 -Query "SELECT pipeline_type, status, started_at, completed_at FROM aquavision.pipeline_runs ORDER BY started_at DESC LIMIT 5;"
.\scripts\Query-DB.ps1 -Query "SELECT service_name, status, last_heartbeat_at FROM aquavision.scheduler_heartbeats ORDER BY last_heartbeat_at DESC LIMIT 3;"
```

Observed: IRSA runs at 00:42/01:21/09:56 and FFD at 01:00 (SUCCESS), heartbeat
`RUNNING` a few seconds old — the scheduler is live and on schedule.
