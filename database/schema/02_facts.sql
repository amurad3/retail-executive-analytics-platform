-- ============================================================
-- Retail Executive Analytics Platform
-- Fact tables (star schema)
-- ============================================================

-- fact_sales holds every transaction line (target ~8-10M rows).
-- Range-partitioned by date_id (YYYYMMDD) so each year's data lives in its
-- own partition -- keeps indexes small, lets old years be archived/dropped
-- independently, and mirrors how this would actually be run at scale.
CREATE TABLE fact_sales (
    sale_id         BIGINT GENERATED ALWAYS AS IDENTITY,
    date_id         INT NOT NULL REFERENCES dim_date(date_id),
    store_id        INT NOT NULL REFERENCES dim_store(store_id),
    product_id      INT NOT NULL REFERENCES dim_product(product_id),
    customer_id     INT NOT NULL REFERENCES dim_customer(customer_id),
    quantity        INT NOT NULL CHECK (quantity <> 0),
    unit_price      NUMERIC(10,2) NOT NULL,
    unit_cost       NUMERIC(10,2) NOT NULL,
    discount_pct    NUMERIC(5,4) NOT NULL DEFAULT 0,
    net_revenue     NUMERIC(12,2) NOT NULL,
    gross_margin    NUMERIC(12,2) NOT NULL,
    is_return       BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (date_id, sale_id)
) PARTITION BY RANGE (date_id);

-- fact_inventory holds a monthly on-hand snapshot per store/product
-- (target ~1-3M rows depending on assortment size).
CREATE TABLE fact_inventory (
    inventory_id    BIGSERIAL PRIMARY KEY,
    date_id         INT NOT NULL REFERENCES dim_date(date_id),
    store_id        INT NOT NULL REFERENCES dim_store(store_id),
    product_id      INT NOT NULL REFERENCES dim_product(product_id),
    on_hand_qty     INT NOT NULL,
    units_sold      INT NOT NULL DEFAULT 0,
    reorder_point   INT,
    safety_stock    INT,
    lead_time_days  INT,
    UNIQUE (date_id, store_id, product_id)
);
