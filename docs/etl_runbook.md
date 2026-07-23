# ETL Runbook

## Prerequisites

- Python 3.11+, PostgreSQL 16+ (developed against 18) running and reachable.
- `pip install -r requirements.txt`
- A `.env` file (copy from `.env.example`) with your Postgres connection info.
- The database itself must already exist:
  ```bash
  psql -U postgres -h localhost -c "CREATE DATABASE retail_analytics;"
  ```

## 1. Apply the schema

Run once, in order, against an empty database:

```bash
psql -U postgres -h localhost -d retail_analytics -v ON_ERROR_STOP=1 -f database/schema/01_dimensions.sql
psql -U postgres -h localhost -d retail_analytics -v ON_ERROR_STOP=1 -f database/schema/02_facts.sql
psql -U postgres -h localhost -d retail_analytics -v ON_ERROR_STOP=1 -f database/schema/03_indexes_partitions.sql
psql -U postgres -h localhost -d retail_analytics -v ON_ERROR_STOP=1 -f database/schema/04_analytics_schema.sql
```
`01_dimensions.sql` also populates `dim_date` (2021-2026) as part of running it --
no separate step needed.

## 2. Run the ETL pipeline

```bash
# Quick smoke test first (~50k sales rows, finishes in seconds):
python -m etl.run_pipeline --sample

# Full run (defaults: 75 stores, 3,000 products, 300k customers, ~9M sales rows):
python -m etl.run_pipeline
```

**This truncates and reloads every table** (`fact_inventory`, `fact_sales`,
`dim_customer`, `dim_store`, `dim_product`) every time it runs -- it's a full
refresh, not an incremental load. That's intentional for a project whose "source
system" is a generator: there's no meaningful concept of an incremental diff
against synthetic data.

At full scale, expect roughly:
- Dimensions (stores/products/customers): ~1-2 minutes (customer name generation via Faker is the slow part)
- `fact_sales` (~9M rows, generated + loaded year by year): ~15-20 minutes
- `fact_inventory` (~4M rows, derived from the sales aggregation): ~5-7 minutes
- Total: ~20-25 minutes on typical hardware

Useful flags:
| Flag | Default | Purpose |
|---|---|---|
| `--sample` | off | Overrides scale to 10 stores / 200 products / 5k customers / 50k sales rows |
| `--sales-rows N` | 9,000,000 | Target row count (actual will vary slightly -- it's Poisson-distributed demand, not a hard cutoff) |
| `--customers N` | 300,000 | |
| `--products N` | 3,000 | |
| `--stores N` | 75 | |
| `--start-date` / `--end-date` | 2021-01-01 / 2025-12-31 | Sales generation window (must stay within dim_date's populated range) |
| `--seed N` | 42 | Reproducibility -- same seed, same data |

The pipeline ends with a data-quality check pass: row counts per table, a null-key
check on `fact_sales`, and the loaded date range. Check the log output for these
before trusting a run.

## 3. Run the analytics modules

Each is independent and reads only from the star schema (run in any order, after
step 2):

```bash
python -m analytics.forecasting.sales_forecast
python -m analytics.segmentation.customer_segmentation
python -m analytics.profitability.profitability_analysis
python -m analytics.inventory.inventory_optimization
```

Each writes (via `if_exists="replace"`) to one or two tables under the
`analytics` Postgres schema -- safe to re-run any of them any time after a new
ETL load; each run fully replaces its own output tables.

## Troubleshooting

- **`relation "fact_sales" does not exist`** -- schema wasn't applied, or you're
  pointed at the wrong database. Check `.env`.
- **COPY errors mentioning a foreign key violation** -- shouldn't happen since
  the generator only ever samples IDs that exist in the dimensions it just
  generated in the same run; if you see this, it usually means dimensions were
  loaded from a different run/seed than the fact data (e.g. you ran
  `etl.run_pipeline` partially, or generated dims separately). Re-run the full
  pipeline from scratch.
- **statsmodels `ValueError` about insufficient seasonal periods** in the
  forecasting module -- means fewer than 24 months of sales history are loaded.
  Check `--start-date`/`--end-date` weren't narrowed too far.
- **Pipeline is much slower than the estimates above** -- Postgres FK constraint
  checks during `COPY` do real index lookups; make sure the indexes from
  `03_indexes_partitions.sql` were actually applied (`\d fact_sales` in psql
  should show `idx_fact_sales_*` indexes).
