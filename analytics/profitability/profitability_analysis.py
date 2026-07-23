"""
Profitability analysis: SQL-driven margin roll-ups by category/region/month
plus a product-level ranking, so Power BI can show margin trends and call out
top/bottom performers without re-aggregating 8-10M raw rows itself.
"""
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from etl.db import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
logger = logging.getLogger("profitability_analysis")

SUMMARY_QUERY = """
    SELECT
        d.year, d.month, p.category, s.region,
        SUM(f.net_revenue) AS net_revenue,
        SUM(f.gross_margin) AS gross_margin,
        ROUND(SUM(f.gross_margin) / NULLIF(SUM(f.net_revenue), 0) * 100, 2) AS margin_pct,
        COUNT(*) FILTER (WHERE NOT f.is_return) AS num_transactions
    FROM fact_sales f
    JOIN dim_date d ON d.date_id = f.date_id
    JOIN dim_product p ON p.product_id = f.product_id
    JOIN dim_store s ON s.store_id = f.store_id
    GROUP BY d.year, d.month, p.category, s.region
    ORDER BY d.year, d.month, p.category, s.region
"""

PRODUCT_QUERY = """
    SELECT
        p.product_id, p.sku, p.product_name, p.category, p.brand,
        SUM(f.net_revenue) AS net_revenue,
        SUM(f.gross_margin) AS gross_margin,
        ROUND(SUM(f.gross_margin) / NULLIF(SUM(f.net_revenue), 0) * 100, 2) AS margin_pct,
        SUM(f.quantity) FILTER (WHERE NOT f.is_return) AS units_sold
    FROM fact_sales f
    JOIN dim_product p ON p.product_id = f.product_id
    GROUP BY p.product_id, p.sku, p.product_name, p.category, p.brand
"""


def run(engine=None) -> None:
    engine = engine or get_engine()

    summary_df = pd.read_sql(SUMMARY_QUERY, engine)
    summary_df.to_sql("profitability_summary", engine, schema="analytics", if_exists="replace", index=False)
    logger.info("Wrote %d rows to analytics.profitability_summary", len(summary_df))

    product_df = pd.read_sql(PRODUCT_QUERY, engine)
    product_df["margin_rank"] = product_df["gross_margin"].rank(ascending=False, method="min").astype(int)
    product_df.to_sql("profitability_by_product", engine, schema="analytics", if_exists="replace", index=False)
    logger.info("Wrote %d rows to analytics.profitability_by_product", len(product_df))

    top5 = product_df.nsmallest(5, "margin_rank")[["product_name", "gross_margin"]]
    bottom5 = product_df.nlargest(5, "margin_rank")[["product_name", "gross_margin"]]
    logger.info("Top 5 products by margin:\n%s", top5.to_string(index=False))
    logger.info("Bottom 5 products by margin:\n%s", bottom5.to_string(index=False))


if __name__ == "__main__":
    run()
