# services/airflow/dags/pmd_daily_ingestion.py
# Airflow DAG: Scrape PMD/FFD river gauge + flood data.
# Schedule: Daily at 07:00 PKT (after IRSA).
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "aquavision",
    "retries": 2,
    "retry_delay": timedelta(minutes=15),
    "execution_timeout": timedelta(minutes=20),
}

with DAG(
    dag_id="pmd_daily_ingestion",
    default_args=default_args,
    description="Scrape FFD Lahore river gauge + flood bulletins → store in PostGIS",
    schedule="0 2 * * *",  # 07:00 PKT = 02:00 UTC
    start_date=datetime(2026, 8, 1, tzinfo=None),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "pmd", "ffd", "flood", "daily"],
) as dag:

    def scrape_pmd_task(**context):
        import sys
        sys.path.insert(0, "/opt/airflow/services/aquavision-service")

        from infrastructure.ingestion.pmd_scraper import PMDScraper
        from datetime import date

        scraper = PMDScraper()
        try:
            html = scraper.fetch_flood_bulletin_a()
            obs = scraper.parse_flood_bulletin(html, date.today())

            print(f"Parsed {len(obs)} PMD observations:")
            for o in obs:
                print(f"  {o.station_name} ({o.river}): "
                      f"level={o.gauge_level_ft}, discharge={o.discharge_cusecs}, "
                      f"status={o.flood_status}")

            # TODO: Store in water_observations table
            # For now, just log
            return {"parsed": len(obs), "date": str(date.today())}
        finally:
            scraper.close()

    PythonOperator(
        task_id="scrape_pmd_river_data",
        python_callable=scrape_pmd_task,
    )
