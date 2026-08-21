# services/airflow/dags/irsa_daily_ingestion.py
# Airflow DAG: Download + parse + ingest IRSA daily water situation PDF.
# Schedule: Daily at 06:30 PKT (IRSA publishes around 06:00-07:00 PKT).
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

PKT_OFFSET = timedelta(hours=5)

default_args = {
    "owner": "aquavision",
    "retries": 3,
    "retry_delay": timedelta(minutes=15),
    "execution_timeout": timedelta(minutes=30),
    "email_on_failure": False,
}

with DAG(
    dag_id="irsa_daily_ingestion",
    default_args=default_args,
    description="Fetch IRSA daily water situation PDF → parse → store in PostGIS",
    schedule="30 1 * * *",  # 06:30 PKT = 01:30 UTC
    start_date=datetime(2026, 8, 1, tzinfo=None),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "irsa", "water", "daily"],
) as dag:

    def ingest_task(**context):
        import sys
        sys.path.insert(0, "/opt/airflow/services/aquavision-service")

        from infrastructure.ingestion.irsa_downloader import auto_ingest_irsa
        from datetime import date, timedelta

        # Ingest yesterday's report (IRSA publishes next-day data)
        target = date.today() - timedelta(days=1)
        result = auto_ingest_irsa(target)

        if "error" in result:
            raise Exception(f"Ingestion failed: {result['error']}")

        print(f"IRSA ingestion result: {result}")
        return result

    PythonOperator(
        task_id="fetch_parse_store_irsa",
        python_callable=ingest_task,
    )
