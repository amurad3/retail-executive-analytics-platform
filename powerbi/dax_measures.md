# DAX Measures

Create these in a dedicated measure table (New Table -> name it `_Measures`, or
attach them to `fact_sales`) rather than as calculated columns -- measures
recompute per filter context, which is what every one of these needs.

Note: `fact_sales[quantity]` is signed (negative for returns), so `net_revenue`
and `gross_margin` are already return-adjusted at the row level -- most measures
below can just `SUM` them directly.

## Core sales measures

```dax
Total Revenue = SUM(fact_sales[net_revenue])

Total Transactions =
CALCULATE(COUNTROWS(fact_sales), fact_sales[is_return] = FALSE)

Total Returns =
CALCULATE(COUNTROWS(fact_sales), fact_sales[is_return] = TRUE)

Return Rate % =
DIVIDE([Total Returns], [Total Returns] + [Total Transactions])

Total Units Sold =
CALCULATE(SUM(fact_sales[quantity]), fact_sales[is_return] = FALSE)

Avg Revenue per Line =
DIVIDE([Total Revenue], [Total Transactions])
```
(Each `fact_sales` row is one product line within a transaction, not a full
basket -- there's no order/basket ID in the model, so this is "per line item,"
not "per order.")

## Margin

```dax
Gross Margin = SUM(fact_sales[gross_margin])

Gross Margin % = DIVIDE([Gross Margin], [Total Revenue])
```

## Time intelligence (requires dim_date marked as the Date Table)

```dax
Revenue LY =
CALCULATE([Total Revenue], SAMEPERIODLASTYEAR(dim_date[full_date]))

YoY Revenue Growth % =
DIVIDE([Total Revenue] - [Revenue LY], [Revenue LY])

Revenue MTD =
TOTALMTD([Total Revenue], dim_date[full_date])
```

## Customer segmentation (from analytics.customer_segments)

```dax
Champion Customers =
CALCULATE(
    DISTINCTCOUNT(customer_segments[customer_id]),
    customer_segments[rfm_segment] = "Champions"
)

At Risk Customers =
CALCULATE(
    DISTINCTCOUNT(customer_segments[customer_id]),
    customer_segments[rfm_segment] = "At Risk"
)

Avg Customer Monetary Value = AVERAGE(customer_segments[monetary])
```

## Inventory (from analytics.inventory_recommendations / product_abc_classification)

```dax
Understocked SKUs =
CALCULATE(
    COUNTROWS(inventory_recommendations),
    inventory_recommendations[stock_status] = "Understocked (raise reorder point)"
)

Overstocked SKUs =
CALCULATE(
    COUNTROWS(inventory_recommendations),
    inventory_recommendations[stock_status] = "Overstocked (lower reorder point)"
)

Class A SKU Count =
CALCULATE(
    COUNTROWS(product_abc_classification),
    product_abc_classification[abc_class] = "A"
)

Approx Inventory Turnover =
DIVIDE(SUM(fact_inventory[units_sold]), AVERAGE(fact_inventory[on_hand_qty]))
```
`Approx Inventory Turnover` is a simplified monthly turns figure (units sold /
average on-hand within the current filter context) -- good enough for an
executive-level "is this category moving" signal, not a precise financial
turnover ratio (which would need COGS and average inventory *value* over a
full fiscal year).

## Forecast (from analytics.sales_forecast -- plain columns, not measures)

`analytics.sales_forecast` already contains `actual_revenue`, `forecast_revenue`,
`lower_ci`, and `upper_ci` as pre-computed columns (one row per category per
month) -- plot them directly in a line/area chart rather than wrapping them in
DAX measures; there's no additional aggregation needed since the table is
already at the exact grain the chart needs.
