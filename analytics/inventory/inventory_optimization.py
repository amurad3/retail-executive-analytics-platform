"""
Inventory optimization: computes proper reorder points, safety stock
(service-level based), and EOQ from actual demand statistics, then compares
against the store's current (heuristic) settings in fact_inventory to surface
over/under-stock gaps. Also produces a classic ABC revenue classification at
the product level.

Demand variance is computed without densifying every store/product/day
combination: since zero-sale days contribute 0 to a sum of squares, summing
squared daily units over only the days with actual sales is mathematically
equivalent to summing over the full calendar window, so
Var = sum_sq/N - mean**2 works with N = the full window length.
"""
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from etl.db import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
logger = logging.getLogger("inventory_optimization")

SERVICE_LEVEL_Z = 1.645          # ~95% service level
ANNUAL_HOLDING_COST_RATE = 0.20  # 20% of unit cost per year
ORDERING_COST_PER_ORDER = 50.0   # flat cost assumption per replenishment order
STOCK_GAP_THRESHOLD = 0.20       # flag >20% gap between current and optimal reorder point

DEMAND_STATS_QUERY = """
    WITH daily AS (
        SELECT f.store_id, f.product_id, d.full_date, SUM(f.quantity) AS daily_units
        FROM fact_sales f
        JOIN dim_date d ON d.date_id = f.date_id
        WHERE NOT f.is_return
        GROUP BY f.store_id, f.product_id, d.full_date
    )
    SELECT store_id, product_id,
           SUM(daily_units) AS total_units,
           SUM(POWER(daily_units::numeric, 2)) AS sum_sq
    FROM daily
    GROUP BY store_id, product_id
"""

CURRENT_SETTINGS_QUERY = """
    SELECT store_id, product_id,
           AVG(reorder_point) AS current_reorder_point,
           AVG(safety_stock) AS current_safety_stock,
           AVG(lead_time_days) AS lead_time_days
    FROM fact_inventory
    GROUP BY store_id, product_id
"""

ANALYSIS_WINDOW_QUERY = """
    SELECT COUNT(*) AS n_days
    FROM dim_date
    WHERE full_date BETWEEN (SELECT min(d.full_date) FROM fact_sales f JOIN dim_date d ON d.date_id = f.date_id)
                         AND (SELECT max(d.full_date) FROM fact_sales f JOIN dim_date d ON d.date_id = f.date_id)
"""

PRODUCT_REVENUE_QUERY = """
    SELECT p.product_id, p.sku, p.product_name, p.category,
           SUM(f.net_revenue) AS total_revenue
    FROM fact_sales f
    JOIN dim_product p ON p.product_id = f.product_id
    WHERE NOT f.is_return
    GROUP BY p.product_id, p.sku, p.product_name, p.category
"""


def build_recommendations(engine) -> pd.DataFrame:
    n_days = pd.read_sql(ANALYSIS_WINDOW_QUERY, engine)["n_days"].iloc[0]

    demand = pd.read_sql(DEMAND_STATS_QUERY, engine)
    demand["avg_daily_demand"] = demand["total_units"] / n_days
    variance = demand["sum_sq"] / n_days - demand["avg_daily_demand"] ** 2
    demand["std_daily_demand"] = np.sqrt(variance.clip(lower=0))

    current = pd.read_sql(CURRENT_SETTINGS_QUERY, engine)
    unit_cost = pd.read_sql("SELECT product_id, unit_cost FROM dim_product", engine)

    df = demand.merge(current, on=["store_id", "product_id"], how="inner")
    df = df.merge(unit_cost, on="product_id", how="left")
    df["lead_time_days"] = df["lead_time_days"].fillna(df["lead_time_days"].median())

    df["optimal_safety_stock"] = np.round(
        SERVICE_LEVEL_Z * df["std_daily_demand"] * np.sqrt(df["lead_time_days"])
    )
    df["optimal_reorder_point"] = np.round(
        df["avg_daily_demand"] * df["lead_time_days"] + df["optimal_safety_stock"]
    )

    annual_demand = df["avg_daily_demand"] * 365
    holding_cost = (df["unit_cost"] * ANNUAL_HOLDING_COST_RATE).clip(lower=0.01)
    df["eoq"] = np.round(np.sqrt(2 * annual_demand * ORDERING_COST_PER_ORDER / holding_cost))

    gap = (df["optimal_reorder_point"] - df["current_reorder_point"]) / df["current_reorder_point"].replace(0, np.nan)
    df["stock_status"] = np.select(
        [gap > STOCK_GAP_THRESHOLD, gap < -STOCK_GAP_THRESHOLD],
        ["Understocked (raise reorder point)", "Overstocked (lower reorder point)"],
        default="Aligned",
    )

    return df[["store_id", "product_id", "avg_daily_demand", "std_daily_demand",
               "lead_time_days", "current_reorder_point", "current_safety_stock",
               "optimal_reorder_point", "optimal_safety_stock", "eoq", "stock_status"]]


def build_abc_classification(engine) -> pd.DataFrame:
    df = pd.read_sql(PRODUCT_REVENUE_QUERY, engine).sort_values("total_revenue", ascending=False)
    df["cumulative_pct"] = df["total_revenue"].cumsum() / df["total_revenue"].sum() * 100
    df["abc_class"] = np.select(
        [df["cumulative_pct"] <= 80, df["cumulative_pct"] <= 95],
        ["A", "B"],
        default="C",
    )
    return df


def run(engine=None) -> None:
    engine = engine or get_engine()

    recs = build_recommendations(engine)
    recs.to_sql("inventory_recommendations", engine, schema="analytics", if_exists="replace", index=False)
    logger.info("Wrote %d rows to analytics.inventory_recommendations", len(recs))
    logger.info("Stock status breakdown:\n%s", recs["stock_status"].value_counts())

    abc = build_abc_classification(engine)
    abc.to_sql("product_abc_classification", engine, schema="analytics", if_exists="replace", index=False)
    logger.info("Wrote %d rows to analytics.product_abc_classification", len(abc))
    logger.info("ABC breakdown:\n%s", abc["abc_class"].value_counts())


if __name__ == "__main__":
    run()
