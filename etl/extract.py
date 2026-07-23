"""Extract step: pulls the reference calendar from Postgres and generates the
synthetic source data (stores, products, customers, and raw sales/inventory
facts) that stands in for an upstream retail source system."""
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
from data_generation import generate_synthetic_data as gen


def extract_calendar(engine, start_date: str, end_date: str) -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT date_id, full_date, year, month, day_of_week, is_holiday, holiday_name FROM dim_date",
        engine,
    )
    df["full_date"] = pd.to_datetime(df["full_date"])
    mask = (df["full_date"] >= start_date) & (df["full_date"] <= end_date)
    return df.loc[mask].reset_index(drop=True)


def extract_stores(n_stores: int, seed: int) -> pd.DataFrame:
    return gen.generate_stores(n_stores, seed)


def extract_products(n_products: int, seed: int) -> pd.DataFrame:
    return gen.generate_products(n_products, seed)


def extract_customers(n_customers: int, start_date: str, end_date: str, seed: int) -> pd.DataFrame:
    return gen.generate_customers(n_customers, start_date, end_date, seed)


def extract_sales(calendar_df, stores_df, products_df, customers_df, target_rows: int, seed: int):
    return gen.generate_fact_sales(calendar_df, stores_df, products_df, customers_df, target_rows, seed)


def extract_inventory(monthly_sales_df, products_df, seed: int) -> pd.DataFrame:
    return gen.generate_fact_inventory(monthly_sales_df, products_df, seed)
