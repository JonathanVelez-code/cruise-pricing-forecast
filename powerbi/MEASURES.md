# DAX measures

Create these in `fact_bookings` (**Home → New measure**). Format % measures as Percentage.

```DAX
Total Revenue =
CALCULATE ( SUM ( fact_bookings[price_paid] ), fact_bookings[status] = "confirmed" )

Cabins Booked =
CALCULATE ( COUNTROWS ( fact_bookings ), fact_bookings[status] = "confirmed" )

Cabins Available =
SUM ( fact_cabin_inventory[cabins_available] )

Occupancy % =
DIVIDE ( [Cabins Booked], [Cabins Available] )

Avg Price =
DIVIDE ( [Total Revenue], [Cabins Booked] )

Revenue per Available Cabin =
DIVIDE ( [Total Revenue], [Cabins Available] )

Cancellation Rate =
DIVIDE (
    CALCULATE ( COUNTROWS ( fact_bookings ), fact_bookings[status] = "cancelled" ),
    COUNTROWS ( fact_bookings )
)

Revenue LY =
CALCULATE ( [Total Revenue], SAMEPERIODLASTYEAR ( dim_date[date] ) )

Revenue YoY % =
DIVIDE ( [Total Revenue] - [Revenue LY], [Revenue LY] )

Forecast Occupancy % =
DIVIDE (
    SUM ( forecast_open_sailings[forecast_final] ),
    SUM ( forecast_open_sailings[cabins_available] )
)

On The Books % =
DIVIDE (
    SUM ( forecast_open_sailings[otb] ),
    SUM ( forecast_open_sailings[cabins_available] )
)
```

**Notes:**
- `DIVIDE` returns blank instead of an error when the denominator is 0.
- `SAMEPERIODLASTYEAR` needs `dim_date` marked as a date table and related to `dim_sailing[sail_date]`, so revenue here is measured by **sail date**.
