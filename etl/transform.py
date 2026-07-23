"""Transform step: enrichment, business-rule derivations, and validation
applied to the raw generated data before it is loaded into the warehouse."""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def transform_stores(df: pd.DataFrame) -> pd.DataFrame:
    return df[["store_id", "store_code", "store_name", "store_type", "region",
               "state", "city", "square_footage", "open_date"]].copy()


def transform_products(df: pd.DataFrame) -> pd.DataFrame:
    return df[["product_id", "sku", "product_name", "category", "subcategory",
               "brand", "unit_cost", "unit_price", "launch_date"]].copy()


def transform_customers(df: pd.DataFrame) -> pd.DataFrame:
    return df[["customer_id", "customer_name", "email", "gender", "birth_date",
               "region", "signup_date", "loyalty_tier"]].copy()


def transform_sales(df: pd.DataFrame) -> pd.DataFrame:
    """Applies the return sign convention and derives net_revenue / gross_margin.

    The generator only outputs the raw economics (quantity, unit_price,
    unit_cost, discount_pct, is_return) -- this is where a return becomes a
    negative-quantity line and where revenue/margin are actually computed,
    matching how the source system's raw feed and the analytics-ready fact
    table intentionally differ.
    """
    before = len(df)
    df = df.dropna(subset=["date_id", "store_id", "product_id", "customer_id"]).copy()
    if len(df) != before:
        logger.warning("Dropped %d sales rows with null keys", before - len(df))

    signed_quantity = np.where(df["is_return"], -df["quantity"], df["quantity"])
    df["quantity"] = signed_quantity
    df["net_revenue"] = (df["quantity"] * df["unit_price"] * (1 - df["discount_pct"])).round(2)
    df["gross_margin"] = (df["net_revenue"] - df["quantity"] * df["unit_cost"]).round(2)

    return df[["date_id", "store_id", "product_id", "customer_id", "quantity",
               "unit_price", "unit_cost", "discount_pct", "net_revenue",
               "gross_margin", "is_return"]]


def transform_inventory(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df.dropna(subset=["date_id", "store_id", "product_id"]).copy()
    if len(df) != before:
        logger.warning("Dropped %d inventory rows with null keys", before - len(df))
    df["on_hand_qty"] = df["on_hand_qty"].clip(lower=0)
    return df[["date_id", "store_id", "product_id", "on_hand_qty", "units_sold",
               "reorder_point", "safety_stock", "lead_time_days"]]
