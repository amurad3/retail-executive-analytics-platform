"""
Sales forecasting: Holt-Winters exponential smoothing per product category
(plus a company-wide series), forecasting 6 months ahead with simulation-based
90% prediction intervals. Writes both history and forecast to
analytics.sales_forecast so Power BI can plot one continuous actual+forecast
line per category.
"""
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from etl.db import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
logger = logging.getLogger("sales_forecast")

FORECAST_HORIZON_MONTHS = 6
N_SIMULATIONS = 300
CI_LOW, CI_HIGH = 0.05, 0.95  # 90% interval
MIN_HISTORY_MONTHS = 24        # need >= 2 full seasonal cycles for seasonal_periods=12

MONTHLY_REVENUE_QUERY = """
    SELECT d.year, d.month, p.category, SUM(f.net_revenue) AS net_revenue
    FROM fact_sales f
    JOIN dim_date d ON d.date_id = f.date_id
    JOIN dim_product p ON p.product_id = f.product_id
    GROUP BY d.year, d.month, p.category
    ORDER BY d.year, d.month
"""


def load_monthly_revenue(engine) -> pd.DataFrame:
    df = pd.read_sql(MONTHLY_REVENUE_QUERY, engine)
    df["month_date"] = pd.to_datetime(dict(year=df.year, month=df.month, day=1))
    return df


def forecast_series(monthly: pd.Series) -> pd.DataFrame:
    model = ExponentialSmoothing(
        monthly, trend="add", seasonal="add", seasonal_periods=12,
        initialization_method="estimated",
    ).fit()

    forecast_index = pd.date_range(
        monthly.index[-1] + pd.DateOffset(months=1), periods=FORECAST_HORIZON_MONTHS, freq="MS"
    )
    point_forecast = model.forecast(FORECAST_HORIZON_MONTHS)

    sims = model.simulate(FORECAST_HORIZON_MONTHS, repetitions=N_SIMULATIONS, error="add")
    lower = sims.quantile(CI_LOW, axis=1)
    upper = sims.quantile(CI_HIGH, axis=1)

    return pd.DataFrame({
        "month_date": forecast_index,
        "forecast_revenue": point_forecast.to_numpy(),
        "lower_ci": lower.to_numpy(),
        "upper_ci": upper.to_numpy(),
    })


def run(engine=None) -> None:
    engine = engine or get_engine()
    df = load_monthly_revenue(engine)

    categories = ["ALL"] + sorted(df["category"].unique())
    all_rows = []

    for category in categories:
        if category == "ALL":
            series = df.groupby("month_date")["net_revenue"].sum().sort_index()
        else:
            series = df[df.category == category].set_index("month_date")["net_revenue"].sort_index()
        series = series.asfreq("MS").interpolate()

        if len(series) < MIN_HISTORY_MONTHS:
            logger.warning("Skipping %s: only %d months of history (need >= %d)",
                            category, len(series), MIN_HISTORY_MONTHS)
            continue

        history_df = pd.DataFrame({
            "category": category,
            "month_date": series.index,
            "actual_revenue": series.to_numpy(),
            "forecast_revenue": np.nan,
            "lower_ci": np.nan,
            "upper_ci": np.nan,
            "is_forecast": False,
        })

        forecast_df = forecast_series(series)
        forecast_df["category"] = category
        forecast_df["actual_revenue"] = np.nan
        forecast_df["is_forecast"] = True

        all_rows.append(pd.concat([history_df, forecast_df], ignore_index=True))
        logger.info("Forecasted %s: next month = $%.0f", category, forecast_df["forecast_revenue"].iloc[0])

    result = pd.concat(all_rows, ignore_index=True)
    result.to_sql("sales_forecast", engine, schema="analytics", if_exists="replace", index=False)
    logger.info("Wrote %d rows to analytics.sales_forecast", len(result))


if __name__ == "__main__":
    run()
