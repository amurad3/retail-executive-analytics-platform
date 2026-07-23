"""
ETL pipeline orchestrator.

Usage:
    python -m etl.run_pipeline --sample                      # quick smoke test (~50k sales rows)
    python -m etl.run_pipeline                                # full run (~9M sales rows, defaults)
    python -m etl.run_pipeline --sales-rows 10000000 --customers 350000

Runs extract -> transform -> load for dimensions, fact_sales (year by year,
so peak memory stays bounded), and fact_inventory (derived from the sales
just loaded), then prints a data-quality summary.
"""
import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
from etl import extract, transform, load
from etl.db import get_engine, get_psycopg2_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
logger = logging.getLogger("run_pipeline")


def parse_args():
    p = argparse.ArgumentParser(description="Retail Executive Analytics Platform ETL pipeline")
    p.add_argument("--stores", type=int, default=75)
    p.add_argument("--products", type=int, default=3000)
    p.add_argument("--customers", type=int, default=300_000)
    p.add_argument("--sales-rows", type=int, default=9_000_000)
    p.add_argument("--start-date", type=str, default="2021-01-01")
    p.add_argument("--end-date", type=str, default="2025-12-31")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--sample", action="store_true",
                    help="Small-scale smoke test: 10 stores, 200 products, 5k customers, 50k sales rows")
    return p.parse_args()


def main():
    args = parse_args()
    if args.sample:
        args.stores, args.products, args.customers, args.sales_rows = 10, 200, 5_000, 50_000
        logger.info("Sample mode: stores=%d products=%d customers=%d sales_rows=%d",
                    args.stores, args.products, args.customers, args.sales_rows)

    t0 = time.time()
    engine = get_engine()
    conn = get_psycopg2_conn()

    try:
        logger.info("Truncating existing data...")
        load.truncate_tables(conn, ["fact_inventory", "fact_sales", "dim_customer", "dim_store", "dim_product"])

        logger.info("Extracting calendar (dim_date) for %s .. %s", args.start_date, args.end_date)
        calendar_df = extract.extract_calendar(engine, args.start_date, args.end_date)
        logger.info("Calendar: %d days", len(calendar_df))

        logger.info("Generating %d stores...", args.stores)
        stores_df = extract.extract_stores(args.stores, args.seed)
        n = load.copy_dataframe(conn, transform.transform_stores(stores_df), "dim_store")
        logger.info("Loaded %d rows into dim_store", n)

        logger.info("Generating %d products...", args.products)
        products_df = extract.extract_products(args.products, args.seed)
        n = load.copy_dataframe(conn, transform.transform_products(products_df), "dim_product")
        logger.info("Loaded %d rows into dim_product", n)

        logger.info("Generating %d customers...", args.customers)
        customers_df = extract.extract_customers(args.customers, args.start_date, args.end_date, args.seed)
        n = load.copy_dataframe(conn, transform.transform_customers(customers_df), "dim_customer")
        logger.info("Loaded %d rows into dim_customer", n)

        logger.info("Generating & loading fact_sales (target ~%d rows, by year)...", args.sales_rows)
        total_sales_rows = 0
        for year, raw_year_df in extract.extract_sales(
            calendar_df, stores_df, products_df, customers_df, args.sales_rows, args.seed
        ):
            year_t0 = time.time()
            clean_df = transform.transform_sales(raw_year_df)
            n = load.copy_dataframe(conn, clean_df, "fact_sales")
            total_sales_rows += n
            logger.info("  %d: loaded %d rows in %.1fs", year, n, time.time() - year_t0)
        logger.info("fact_sales total: %d rows", total_sales_rows)

        logger.info("Aggregating monthly demand for fact_inventory...")
        monthly_sales_df = pd.read_sql(
            """
            SELECT (date_trunc('month', d.full_date)::date) AS month_start,
                   TO_CHAR(date_trunc('month', d.full_date), 'YYYYMM') || '01' AS date_id_text,
                   f.store_id,
                   f.product_id,
                   SUM(f.quantity) AS units_sold
            FROM fact_sales f
            JOIN dim_date d ON d.date_id = f.date_id
            WHERE NOT f.is_return
            GROUP BY 1, 2, f.store_id, f.product_id
            HAVING SUM(f.quantity) > 0
            """,
            conn,
        )
        monthly_sales_df["date_id"] = monthly_sales_df["date_id_text"].astype(int)
        monthly_sales_df = monthly_sales_df.drop(columns=["month_start", "date_id_text"])
        logger.info("Monthly demand rows: %d", len(monthly_sales_df))

        logger.info("Generating & loading fact_inventory...")
        inventory_raw_df = extract.extract_inventory(monthly_sales_df, products_df, args.seed)
        inventory_clean_df = transform.transform_inventory(inventory_raw_df)
        n = load.copy_dataframe(conn, inventory_clean_df, "fact_inventory")
        logger.info("Loaded %d rows into fact_inventory", n)

        run_quality_checks(conn)

    finally:
        conn.close()

    logger.info("Pipeline finished in %.1f minutes", (time.time() - t0) / 60)


def run_quality_checks(conn) -> None:
    logger.info("Running data quality checks...")
    checks = {
        "dim_store": "SELECT count(*) FROM dim_store",
        "dim_product": "SELECT count(*) FROM dim_product",
        "dim_customer": "SELECT count(*) FROM dim_customer",
        "fact_sales": "SELECT count(*) FROM fact_sales",
        "fact_inventory": "SELECT count(*) FROM fact_inventory",
        "fact_sales null keys": """
            SELECT count(*) FROM fact_sales
            WHERE date_id IS NULL OR store_id IS NULL OR product_id IS NULL OR customer_id IS NULL
        """,
        "fact_sales date range": "SELECT min(date_id), max(date_id) FROM fact_sales",
    }
    with conn.cursor() as cur:
        for label, sql in checks.items():
            cur.execute(sql)
            logger.info("  %-24s -> %s", label, cur.fetchone())


if __name__ == "__main__":
    main()
