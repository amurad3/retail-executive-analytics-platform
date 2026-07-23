"""
Synthetic retail data generator.

Produces the dimension tables (stores, products, customers) and a demand-driven,
date-major simulation of transaction volume for fact_sales. Volume varies by
month (holiday season), day of week (weekend lift), specific holidays
(Black Friday spikes, Christmas Day closures), store size, and a year-over-year
growth trend -- so the aggregate numbers a forecasting model or a Power BI
dashboard sees look like a real retail business rather than uniform noise.

Customers and products each carry a real-world constraint: a customer can't buy
before they sign up, and a product can't sell before it launches. Both dimensions
are generated pre-sorted by that date so eligibility at simulation time is a
single `searchsorted` call instead of a per-row filter.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from faker import Faker

CATEGORIES = {
    "Electronics": {
        "subcategories": ["Phones", "Laptops", "Audio", "Accessories", "Cameras"],
        "brands": ["Zentek", "Voltura", "Nimbus", "Corex", "Pulsewave"],
        "price_range": (25, 1500),
    },
    "Apparel": {
        "subcategories": ["Men's", "Women's", "Kids", "Footwear", "Outerwear"],
        "brands": ["Urban Thread", "Northfield", "Cascade", "Lumen Wear", "Solstice"],
        "price_range": (10, 250),
    },
    "Home & Garden": {
        "subcategories": ["Furniture", "Decor", "Kitchen", "Bedding", "Outdoor"],
        "brands": ["Havenwood", "Meadowcraft", "Brightside", "Cornerstone Home", "Gardenia Co"],
        "price_range": (8, 900),
    },
    "Grocery": {
        "subcategories": ["Beverages", "Snacks", "Produce", "Pantry", "Frozen"],
        "brands": ["Farmstead", "Golden Harvest", "PureNest", "Daily Fresh", "Orchard Row"],
        "price_range": (2, 45),
    },
    "Beauty": {
        "subcategories": ["Skincare", "Haircare", "Makeup", "Fragrance", "Bath & Body"],
        "brands": ["Lumiere", "Bare Essence", "Verdant", "Glow Theory", "Petal & Pine"],
        "price_range": (5, 180),
    },
    "Sports & Outdoors": {
        "subcategories": ["Fitness", "Camping", "Cycling", "Team Sports", "Footwear"],
        "brands": ["Summit Gear", "Ridgeline", "Apex Athletics", "TrailForge", "Momentum"],
        "price_range": (10, 650),
    },
    "Toys & Games": {
        "subcategories": ["Action Figures", "Board Games", "Building Sets", "Puzzles", "Outdoor Play"],
        "brands": ["Playforge", "WonderTales", "BrickWorks", "Funloop", "Tinker Toy Co"],
        "price_range": (5, 120),
    },
    "Office Supplies": {
        "subcategories": ["Paper Products", "Writing", "Storage", "Technology", "Furniture"],
        "brands": ["Clarkston", "Meridian Office", "Penbrook", "OrganizeIt", "DeskWorks"],
        "price_range": (3, 320),
    },
}

REGION_WEIGHTS = {"Northeast": 0.25, "Midwest": 0.20, "South": 0.30, "West": 0.25}
REGION_STATES = {
    "Northeast": ["NY", "MA", "NJ", "PA", "CT"],
    "Midwest": ["IL", "OH", "MI", "WI", "MN"],
    "South": ["TX", "FL", "GA", "NC", "TN"],
    "West": ["CA", "WA", "OR", "AZ", "CO"],
}

STORE_TYPE_DIST = {"Flagship": 0.10, "Standard": 0.65, "Outlet": 0.25}
STORE_TYPE_WEIGHT = {"Flagship": 3.0, "Standard": 1.0, "Outlet": 0.55}
STORE_TYPE_SQFT = {"Flagship": (25000, 45000), "Standard": (12000, 20000), "Outlet": (6000, 10000)}

LOYALTY_DIST = {"Bronze": 0.50, "Silver": 0.30, "Gold": 0.15, "Platinum": 0.05}

MONTH_SEASONALITY = {1: 0.80, 2: 0.82, 3: 0.92, 4: 0.95, 5: 1.00, 6: 1.05,
                     7: 1.05, 8: 1.00, 9: 0.95, 10: 1.05, 11: 1.55, 12: 1.85}
# ISODOW: 1=Monday .. 7=Sunday
DOW_SEASONALITY = {1: 0.90, 2: 0.90, 3: 0.92, 4: 0.95, 5: 1.10, 6: 1.30, 7: 1.15}
HOLIDAY_MULTIPLIER = {
    "Black Friday": 3.5, "Christmas Eve": 1.8, "Christmas Day": 0.2,
    "Thanksgiving": 0.4, "New Year's Eve": 1.2, "New Year's Day": 0.5,
    "Independence Day": 1.3,
}
DEFAULT_HOLIDAY_MULTIPLIER = 1.4
ANNUAL_GROWTH = 0.04
BASE_YEAR = 2021

QTY_VALUES = np.array([1, 2, 3, 4, 5])
QTY_PROBS = np.array([0.65, 0.20, 0.08, 0.04, 0.03])

# (low, high) discount fraction per tier: none / markdown / clearance
DISCOUNT_TIERS = np.array([(0.0, 0.0), (0.10, 0.20), (0.30, 0.50)])
NORMAL_DISCOUNT_PROBS = np.array([0.85, 0.10, 0.05])
HOLIDAY_DISCOUNT_PROBS = np.array([0.50, 0.35, 0.15])

RETURN_RATE = 0.03

LEAD_TIME_RANGE_BY_CATEGORY = {
    "Grocery": (2, 7),
    "Electronics": (10, 30),
    "Apparel": (7, 21),
}
DEFAULT_LEAD_TIME_RANGE = (5, 15)


def weighted_choice(weights: np.ndarray, size: int, rng: np.random.Generator) -> np.ndarray:
    p = weights / weights.sum()
    return rng.choice(len(weights), size=size, p=p)


def generate_stores(n_stores: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    fake = Faker()
    Faker.seed(seed)

    regions = rng.choice(list(REGION_WEIGHTS), size=n_stores, p=list(REGION_WEIGHTS.values()))
    store_types = rng.choice(list(STORE_TYPE_DIST), size=n_stores, p=list(STORE_TYPE_DIST.values()))

    rows = []
    for i in range(n_stores):
        region = regions[i]
        store_type = store_types[i]
        state = rng.choice(REGION_STATES[region])
        city = fake.city()
        lo, hi = STORE_TYPE_SQFT[store_type]
        open_date = fake.date_between(start_date="-10y", end_date="-5y")
        rows.append({
            "store_id": i + 1,
            "store_code": f"ST{i + 1:04d}",
            "store_name": f"RetailCo {city}",
            "store_type": store_type,
            "region": region,
            "state": state,
            "city": city,
            "square_footage": int(rng.integers(lo, hi)),
            "open_date": open_date,
        })
    df = pd.DataFrame(rows)
    df["store_base_rate"] = df["store_type"].map(STORE_TYPE_WEIGHT)
    return df


def generate_products(n_products: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    fake = Faker()
    Faker.seed(seed + 1)

    categories = list(CATEGORIES)
    cat_choices = rng.choice(categories, size=n_products)

    rows = []
    for i, category in enumerate(cat_choices):
        spec = CATEGORIES[category]
        subcategory = rng.choice(spec["subcategories"])
        brand = rng.choice(spec["brands"])
        lo, hi = spec["price_range"]
        unit_price = round(float(rng.uniform(lo, hi)), 2)
        unit_cost = round(unit_price * float(rng.uniform(0.35, 0.65)), 2)
        launch_date = fake.date_between(start_date="-10y", end_date="today")
        rows.append({
            "product_id": i + 1,
            "sku": f"{category[:3].upper()}-{i + 1:05d}",
            "product_name": f"{brand} {subcategory} {fake.word().capitalize()}",
            "category": category,
            "subcategory": subcategory,
            "brand": brand,
            "unit_cost": unit_cost,
            "unit_price": unit_price,
            "launch_date": launch_date,
        })
    df = pd.DataFrame(rows)
    df["popularity_weight"] = rng.exponential(scale=1.0, size=n_products) + 0.05
    df = df.sort_values("launch_date").reset_index(drop=True)
    df["launch_date_id"] = pd.to_datetime(df["launch_date"]).dt.strftime("%Y%m%d").astype(int)
    return df


def generate_customers(n_customers: int, start_date: str, end_date: str, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 2)
    fake = Faker()
    Faker.seed(seed + 2)

    # Weighted toward more recent signups (a growing customer base), skewed by a
    # simple triangular-like draw so acquisition ramps up over the window.
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    span_days = (end - start).days
    signup_offsets = (rng.triangular(0, span_days, span_days, size=n_customers)).astype(int)
    signup_dates = start + pd.to_timedelta(signup_offsets, unit="D")

    genders = rng.choice(["Female", "Male", "Other"], size=n_customers, p=[0.48, 0.48, 0.04])
    regions = rng.choice(list(REGION_WEIGHTS), size=n_customers, p=list(REGION_WEIGHTS.values()))
    loyalty = rng.choice(list(LOYALTY_DIST), size=n_customers, p=list(LOYALTY_DIST.values()))
    birth_years = rng.integers(1950, 2006, size=n_customers)
    birth_dates = pd.to_datetime({"year": birth_years,
                                  "month": rng.integers(1, 13, size=n_customers),
                                  "day": 1})

    names = [fake.name() for _ in range(n_customers)]

    df = pd.DataFrame({
        "customer_name": names,
        "gender": genders,
        "birth_date": birth_dates,
        "region": regions,
        "signup_date": signup_dates,
        "loyalty_tier": loyalty,
    })
    df = df.sort_values("signup_date").reset_index(drop=True)
    df.insert(0, "customer_id", np.arange(1, n_customers + 1))
    df["email"] = df["customer_id"].map(lambda i: f"customer{i}@mailbox.example")
    df["purchase_weight"] = rng.exponential(scale=1.0, size=n_customers) + 0.05
    df["signup_date_id"] = pd.to_datetime(df["signup_date"]).dt.strftime("%Y%m%d").astype(int)
    return df


def _build_day_multiplier(calendar_df: pd.DataFrame) -> np.ndarray:
    month_seas = calendar_df["month"].map(MONTH_SEASONALITY).to_numpy()
    dow_seas = calendar_df["day_of_week"].map(DOW_SEASONALITY).to_numpy()
    holiday_mult = np.where(
        calendar_df["is_holiday"],
        calendar_df["holiday_name"].map(HOLIDAY_MULTIPLIER).fillna(DEFAULT_HOLIDAY_MULTIPLIER).to_numpy(),
        1.0,
    )
    trend = (1 + ANNUAL_GROWTH) ** (calendar_df["year"].to_numpy() - BASE_YEAR)
    return month_seas * dow_seas * holiday_mult * trend


def generate_fact_sales(calendar_df: pd.DataFrame, stores_df: pd.DataFrame,
                         products_df: pd.DataFrame, customers_df: pd.DataFrame,
                         target_rows: int, seed: int):
    """Yields (year, DataFrame) chunks of raw sales rows, one per calendar year."""
    rng = np.random.default_rng(seed + 3)

    calendar_df = calendar_df.sort_values("full_date").reset_index(drop=True)
    day_multiplier = _build_day_multiplier(calendar_df)

    store_ids = stores_df["store_id"].to_numpy()
    store_base_rate = stores_df["store_base_rate"].to_numpy()

    global_base_rate = target_rows / (store_base_rate.sum() * day_multiplier.sum())

    product_ids_sorted = products_df["product_id"].to_numpy()
    product_weight_sorted = products_df["popularity_weight"].to_numpy()
    product_launch_id_sorted = products_df["launch_date_id"].to_numpy()
    product_price_sorted = products_df["unit_price"].to_numpy()
    product_cost_sorted = products_df["unit_cost"].to_numpy()

    customer_ids_sorted = customers_df["customer_id"].to_numpy()
    customer_weight_sorted = customers_df["purchase_weight"].to_numpy()
    customer_signup_id_sorted = customers_df["signup_date_id"].to_numpy()

    calendar_df["_year"] = calendar_df["full_date"].dt.year

    for year, year_df in calendar_df.groupby("_year"):
        year_rows = []
        for i in year_df.index:
            date_id = int(calendar_df.at[i, "date_id"])
            lam = global_base_rate * store_base_rate * day_multiplier[i]
            store_counts = rng.poisson(lam=lam)
            n_rows = int(store_counts.sum())
            if n_rows == 0:
                continue

            store_id_block = np.repeat(store_ids, store_counts)

            k_c = max(int(np.searchsorted(customer_signup_id_sorted, date_id, side="right")), 1)
            k_p = max(int(np.searchsorted(product_launch_id_sorted, date_id, side="right")), 1)

            cust_idx = weighted_choice(customer_weight_sorted[:k_c], n_rows, rng)
            prod_idx = weighted_choice(product_weight_sorted[:k_p], n_rows, rng)

            quantity_block = rng.choice(QTY_VALUES, size=n_rows, p=QTY_PROBS)

            is_holiday = bool(calendar_df.at[i, "is_holiday"])
            discount_probs = HOLIDAY_DISCOUNT_PROBS if is_holiday else NORMAL_DISCOUNT_PROBS
            tier_idx = rng.choice(len(DISCOUNT_TIERS), size=n_rows, p=discount_probs)
            lows = DISCOUNT_TIERS[tier_idx, 0]
            highs = DISCOUNT_TIERS[tier_idx, 1]
            discount_block = np.where(highs > lows, rng.uniform(lows, highs), lows)

            is_return_block = rng.random(n_rows) < RETURN_RATE

            year_rows.append(pd.DataFrame({
                "date_id": date_id,
                "store_id": store_id_block,
                "product_id": product_ids_sorted[prod_idx],
                "customer_id": customer_ids_sorted[cust_idx],
                "quantity": quantity_block,
                "unit_price": product_price_sorted[prod_idx],
                "unit_cost": product_cost_sorted[prod_idx],
                "discount_pct": np.round(discount_block, 4),
                "is_return": is_return_block,
            }))

        yield int(year), pd.concat(year_rows, ignore_index=True)


def generate_fact_inventory(monthly_sales_df: pd.DataFrame, products_df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """
    Builds a monthly on-hand snapshot from actual aggregated demand.
    Reorder point / safety stock are intentionally noisy heuristics representing
    a store's *current* (imperfect) policy -- the inventory optimization module
    later computes what these should be and measures the gap.
    """
    rng = np.random.default_rng(seed + 4)
    df = monthly_sales_df.merge(products_df[["product_id", "category"]], on="product_id", how="left")

    n = len(df)
    lead_time = np.empty(n, dtype=int)
    for category, (lo, hi) in LEAD_TIME_RANGE_BY_CATEGORY.items():
        mask = df["category"] == category
        lead_time[mask.to_numpy()] = rng.integers(lo, hi, size=int(mask.sum()))
    other_mask = ~df["category"].isin(LEAD_TIME_RANGE_BY_CATEGORY).to_numpy()
    lo, hi = DEFAULT_LEAD_TIME_RANGE
    lead_time[other_mask] = rng.integers(lo, hi, size=int(other_mask.sum()))

    avg_daily_sold = df["units_sold"].to_numpy() / 30.0
    reorder_point = np.round(avg_daily_sold * lead_time * rng.uniform(0.8, 1.3, size=n)).astype(int)
    safety_stock = np.round(reorder_point * rng.uniform(0.2, 0.4, size=n)).astype(int)
    on_hand_qty = np.round(avg_daily_sold * rng.uniform(15, 45, size=n) + safety_stock).astype(int)

    return pd.DataFrame({
        "date_id": df["date_id"],
        "store_id": df["store_id"],
        "product_id": df["product_id"],
        "on_hand_qty": on_hand_qty,
        "units_sold": df["units_sold"],
        "reorder_point": reorder_point,
        "safety_stock": safety_stock,
        "lead_time_days": lead_time,
    })
