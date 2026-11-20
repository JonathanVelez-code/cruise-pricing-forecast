-- Customer acquisition by booking year, channel and source market:
-- bookings, first-time vs repeat guests, revenue, average price and cancellation rate.
WITH b AS (
  SELECT *,
         EXTRACT(year FROM booking_date) AS booking_year,
         ROW_NUMBER() OVER (PARTITION BY guest_id ORDER BY booking_date, booking_id) AS guest_booking_number
  FROM bookings
)
SELECT booking_year,
       channel,
       source_market,
       COUNT(*)                                                         AS bookings,
       SUM(CASE WHEN guest_booking_number = 1 THEN 1 ELSE 0 END)        AS new_guests,
       SUM(CASE WHEN guest_booking_number > 1 THEN 1 ELSE 0 END)        AS repeat_bookings,
       ROUND(SUM(CASE WHEN status = 'confirmed' THEN price_paid ELSE 0 END), 2) AS confirmed_revenue,
       ROUND(AVG(CASE WHEN status = 'confirmed' THEN price_paid END), 2)        AS avg_price,
       ROUND(100.0 * AVG(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END), 1)  AS cancel_rate_pct
FROM b
GROUP BY booking_year, channel, source_market
ORDER BY booking_year, confirmed_revenue DESC;
