# Power BI dashboard: build guide

Power BI Desktop is free (Windows). This takes about 1–2 hours the first time. Save the file as `powerbi/cruise_revenue.pbix`.

## 1. Load the data
Run `python -m src.pipeline` first. Then go to **Home → Get data → Text/CSV** and load every file in `outputs/powerbi/`:

| File | Role |
|---|---|
| `fact_bookings.csv` | Fact: one row per booking |
| `fact_cabin_inventory.csv` | Fact: cabins available per sailing and category |
| `dim_sailing.csv` | Dimension: sailing, ship, date, itinerary |
| `dim_ship.csv` | Dimension: ship |
| `dim_date.csv` | Date table |
| `forecast_open_sailings.csv` | Forecast + recommendation for the next 180 days |
| `pace_curves.csv` | Cumulative bookings by weeks before sailing |
| `backtest_by_horizon.csv`, `backtest_predictions.csv` | Forecast accuracy |
| `experiment_sailings.csv` | A/B test results by sailing |

In **Power Query**, check the column types: dates are Date, prices are Decimal, and IDs are Whole Number.

## 2. Model (star schema)
In **Model view**, create these relationships, all many-to-one, single direction:
- `fact_bookings[sailing_id]` → `dim_sailing[sailing_id]`
- `fact_cabin_inventory[sailing_id]` → `dim_sailing[sailing_id]`
- `forecast_open_sailings[sailing_id]` → `dim_sailing[sailing_id]`
- `pace_curves[sailing_id]` → `dim_sailing[sailing_id]`
- `dim_sailing[ship_id]` → `dim_ship[ship_id]`
- `dim_sailing[sail_date]` → `dim_date[date]`

Then mark `dim_date` as the date table: **Table tools → Mark as date table**.

## 3. Measures
Copy them from `MEASURES.md`.

## 4. Pages
1. **Revenue overview**
   - KPI cards: Total Revenue, Occupancy %, Avg Price, Revenue YoY %, Cancellation Rate
   - Line chart: revenue by `dim_date[year_month]`
   - Bar chart: occupancy by month, which shows the seasonality
   - Slicers: ship, cabin category, year
2. **Booking pace**
   - Line chart: `pace_curves[weeks_out]` (x-axis reversed) against cumulative occupancy, with a slicer for sailing
   - Table: sailings behind last year's pace
3. **Forecast & recommendations**
   - Table from `forecast_open_sailings`: sail date, ship, category, on-the-books, forecast occupancy, recommendation
   - Conditional formatting: green for *Raise price*, orange for *Promote / discount*
   - Card: count of sailings per recommendation
4. **Model accuracy**
   - Clustered bar: `backtest_by_horizon` model vs baseline MAPE by horizon
   - Scatter: actual vs predicted from `backtest_predictions`
5. **Pricing A/B test**
   - Cards: lift, 95% CI and decision (type them from `outputs/experiment_results.json`)
   - Box plot or bar chart: RevPAC by arm from `experiment_sailings`
   - Note on the page: "simulated demand response, method demo"

## 5. Publish (optional)
Save the `.pbix`, then take screenshots of each page for the README (`outputs/figures/powerbi_*.png`). If you have a Power BI account, you can also publish to the service.
