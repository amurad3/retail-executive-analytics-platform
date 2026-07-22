-- ============================================================
-- Retail Executive Analytics Platform
-- fact_sales partitions + indexes
-- ============================================================

CREATE TABLE fact_sales_2021 PARTITION OF fact_sales FOR VALUES FROM (20210101) TO (20220101);
CREATE TABLE fact_sales_2022 PARTITION OF fact_sales FOR VALUES FROM (20220101) TO (20230101);
CREATE TABLE fact_sales_2023 PARTITION OF fact_sales FOR VALUES FROM (20230101) TO (20240101);
CREATE TABLE fact_sales_2024 PARTITION OF fact_sales FOR VALUES FROM (20240101) TO (20250101);
CREATE TABLE fact_sales_2025 PARTITION OF fact_sales FOR VALUES FROM (20250101) TO (20260101);
CREATE TABLE fact_sales_default PARTITION OF fact_sales DEFAULT;

-- Indexes are declared once on the partitioned parent; Postgres creates and
-- maintains a matching index on every partition automatically.
CREATE INDEX idx_fact_sales_store    ON fact_sales (store_id);
CREATE INDEX idx_fact_sales_product  ON fact_sales (product_id);
CREATE INDEX idx_fact_sales_customer ON fact_sales (customer_id);
CREATE INDEX idx_fact_sales_date_brin ON fact_sales USING BRIN (date_id);

CREATE INDEX idx_fact_inventory_store   ON fact_inventory (store_id);
CREATE INDEX idx_fact_inventory_product ON fact_inventory (product_id);
CREATE INDEX idx_fact_inventory_date    ON fact_inventory (date_id);

CREATE INDEX idx_dim_product_category ON dim_product (category, subcategory);
CREATE INDEX idx_dim_customer_region  ON dim_customer (region);
CREATE INDEX idx_dim_store_region     ON dim_store (region);
