"""Database connection helpers shared by the ETL pipeline and analytics modules."""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()


def get_conn_params() -> dict:
    return dict(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "retail_analytics"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
    )


def get_engine():
    p = get_conn_params()
    url = f"postgresql+psycopg2://{p['user']}:{p['password']}@{p['host']}:{p['port']}/{p['dbname']}"
    return create_engine(url)


def get_psycopg2_conn():
    import psycopg2

    return psycopg2.connect(**get_conn_params())
