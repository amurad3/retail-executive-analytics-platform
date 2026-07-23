# Data Dictionary

## Star schema

### dim_date
Calendar dimension, one row per day, 2021-01-01 through 2026-12-31 (the extra
year past 2025 supports the forecasting module's horizon).

| Column | Type | Description |
|---|---|---|
| date_id | INT (PK) | `YYYYMMDD` integer surrogate key |
| full_date | DATE | Calendar date |
| year | SMALLINT | Calendar year |
| quarter | SMALLINT | 1-4 |
| month | SMALLINT | 1-12 |
| month_name | VARCHAR | e.g. "January" |
| week_of_year | SMALLINT | ISO-ish week number |
| day_of_month | SMALLINT | 1-31 |
| day_of_week | SMALLINT | ISO: 1=Monday .. 7=Sunday |
| day_name | VARCHAR | e.g. "Monday" |
| is_weekend | BOOLEAN | Saturday or Sunday |
| is_holiday | BOOLEAN | One of the 7 US holidays modeled |
| holiday_name | VARCHAR | New Year's Day / Independence Day / Thanksgiving / Black Friday / Christmas Eve / Christmas Day / New Year's Eve, else NULL |

### dim_store
| Column | Type | Description |
|---|---|---|
| store_id | SERIAL (PK) | Surrogate key |
| store_code | VARCHAR | e.g. `ST0001` |
| store_name | VARCHAR | Generated display name |
| store_type | VARCHAR | Flagship / Standard / Outlet |
| region | VARCHAR | Northeast / Midwest / South / West |
| state | VARCHAR(2) | US state abbreviation |
| city | VARCHAR | Generated city name |
| square_footage | INT | Store size, ranges by store_type |
| open_date | DATE | All stores pre-date the sales window (2015-2020) |

### dim_product
| Column | Type | Description |
|---|---|---|
| product_id | SERIAL (PK) | Surrogate key |
| sku | VARCHAR | e.g. `ELE-00001` |
| product_name | VARCHAR | Generated display name |
| category | VARCHAR | One of 8 categories (Electronics, Apparel, Home & Garden, Grocery, Beauty, Sports & Outdoors, Toys & Games, Office Supplies) |
| subcategory | VARCHAR | Category-specific subcategory |
| brand | VARCHAR | Category-specific brand |
| unit_cost | NUMERIC(10,2) | Wholesale/COGS cost |
| unit_price | NUMERIC(10,2) | List price (cost is 35-65% of price) |
| launch_date | DATE | Product can only sell on or after this date |

### dim_customer
| Column | Type | Description |
|---|---|---|
| customer_id | SERIAL (PK) | Surrogate key |
| customer_name | VARCHAR | Generated name |
| email | VARCHAR | Synthetic (`customer{id}@mailbox.example`) -- clearly not a real address |
| gender | VARCHAR | Female / Male / Other |
| birth_date | DATE | |
| region | VARCHAR | Northeast / Midwest / South / West |
| signup_date | DATE | Customer can only buy on or after this date |
| loyalty_tier | VARCHAR | Bronze / Silver / Gold / Platinum, assigned at signup |

### fact_sales
One row per product line within a transaction (not one row per basket/order --
there's no order/basket ID in this model). Range-partitioned by `date_id`
(yearly partitions `fact_sales_2021` .. `fact_sales_2025`, plus a catch-all
`fact_sales_default`).

| Column | Type | Description |
|---|---|---|
| sale_id | BIGINT (PK, identity) | Surrogate key (composite PK with date_id) |
| date_id | INT (FK -> dim_date) | Transaction date |
| store_id | INT (FK -> dim_store) | Selling store |
| product_id | INT (FK -> dim_product) | Product sold |
| customer_id | INT (FK -> dim_customer) | Purchasing customer |
| quantity | INT | **Signed**: negative when `is_return` is true |
| unit_price | NUMERIC(10,2) | Price at time of sale (= dim_product.unit_price) |
| unit_cost | NUMERIC(10,2) | Cost at time of sale (= dim_product.unit_cost) |
| discount_pct | NUMERIC(5,4) | 0 (85% of normal-day lines), markdown (10-20%), or clearance (30-50%); holiday days skew toward higher discount tiers |
| net_revenue | NUMERIC(12,2) | `quantity * unit_price * (1 - discount_pct)`, negative for returns |
| gross_margin | NUMERIC(12,2) | `net_revenue - quantity * unit_cost` |
| is_return | BOOLEAN | ~3% baseline return rate |

### fact_inventory
One row per store/product/month -- only for combinations that had at least one
sale that month (a store doesn't get an inventory row for a product it never
sold). Derived from actual aggregated `fact_sales` demand.

| Column | Type | Description |
|---|---|---|
| inventory_id | BIGSERIAL (PK) | Surrogate key |
| date_id | INT (FK -> dim_date) | First day of the snapshot month |
| store_id | INT (FK -> dim_store) | |
| product_id | INT (FK -> dim_product) | |
| on_hand_qty | INT | Simulated on-hand units |
| units_sold | INT | Actual units sold that store/product/month |
| reorder_point | INT | **Current** (heuristic, imperfect by design) reorder point |
| safety_stock | INT | **Current** (heuristic) safety stock |
| lead_time_days | INT | Supplier lead time, category-dependent range |

`reorder_point` and `safety_stock` here represent a store's *existing* (somewhat
arbitrary) inventory policy -- see `analytics.inventory_recommendations` below
for what those values *should* be, computed properly from demand statistics.

## Analytics schema (`analytics.*`)

Written by the modules in `analytics/`. Regenerate by re-running each module
after any ETL reload.

### analytics.sales_forecast
One row per category (plus `category = 'ALL'`) per month, covering both history
and a 6-month forward forecast in the same table.

| Column | Description |
|---|---|
| category | Product category, or `ALL` for company-wide |
| month_date | First of month |
| actual_revenue | Populated for historical months, NULL for forecast months |
| forecast_revenue | NULL for historical months, populated for forecast months |
| lower_ci / upper_ci | 90% simulation-based prediction interval (forecast months only) |
| is_forecast | TRUE for the 6 forward-looking rows per category |

### analytics.customer_segments
One row per customer with at least one non-return purchase.

| Column | Description |
|---|---|
| customer_id | |
| recency_days | Days since last purchase, relative to the last date with any sale in the dataset |
| frequency | Count of non-return transactions |
| monetary | Sum of net_revenue on non-return transactions |
| r_score / f_score / m_score | 1-5 quintile scores (5 = best) |
| rfm_score | Sum of the three (3-15) |
| rfm_segment | Champions / Loyal Customers / Potential Loyalist / At Risk / Lost (rule-based on rfm_score) |
| cluster_id | KMeans cluster (k=4) over standardized recency/frequency/monetary |
| cluster_segment | Cluster labeled by its mean monetary value rank: Champions / Loyal Customers / At Risk / Lost / Dormant |

### analytics.profitability_summary
Grain: year x month x category x region.

| Column | Description |
|---|---|
| year, month, category, region | Grain keys |
| net_revenue, gross_margin | Summed |
| margin_pct | `gross_margin / net_revenue * 100` |
| num_transactions | Non-return line count |

### analytics.profitability_by_product
Grain: product.

| Column | Description |
|---|---|
| product_id, sku, product_name, category, brand | |
| net_revenue, gross_margin, margin_pct | |
| units_sold | Non-return units |
| margin_rank | 1 = highest gross margin |

### analytics.inventory_recommendations
Grain: store x product.

| Column | Description |
|---|---|
| store_id, product_id | |
| avg_daily_demand, std_daily_demand | From actual non-return daily sales, full analysis window |
| lead_time_days | Average of fact_inventory's lead_time_days for this pair |
| current_reorder_point, current_safety_stock | From fact_inventory (the store's existing policy) |
| optimal_reorder_point, optimal_safety_stock | Computed: `avg_daily_demand * lead_time + z * std_daily_demand * sqrt(lead_time)`, z=1.645 (~95% service level) |
| eoq | Economic order quantity: `sqrt(2 * annual_demand * 50 / (unit_cost * 0.20))` |
| stock_status | Understocked / Overstocked / Aligned, based on >20% gap between current and optimal reorder point |

### analytics.product_abc_classification
Grain: product.

| Column | Description |
|---|---|
| product_id, sku, product_name, category | |
| total_revenue | Non-return revenue, all-time |
| cumulative_pct | Running % of total revenue, products sorted descending |
| abc_class | A (top 80% of cumulative revenue) / B (next 15%) / C (remaining 5%) |
