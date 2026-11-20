-- Do early bookers pay less? Price by booking window and season.
--
-- Raw averages are misleading here (Simpson's paradox): suites and 7-night cruises book
-- earliest AND cost the most, so "early" looks expensive. To compare like with like, each
-- booking's price is divided by the average for its own sailing and cabin category
-- (price_index = 1.00 means average for that sailing and cabin).
WITH x AS (
  SELECT b.price_paid,
         b.days_out,
         b.price_paid / AVG(b.price_paid) OVER (PARTITION BY b.sailing_id, b.cabin_category) AS price_index,
         CASE WHEN EXTRACT(month FROM s.sail_date) IN (3, 6, 7, 12) THEN 'peak'
              WHEN EXTRACT(month FROM s.sail_date) IN (9, 10)       THEN 'low'
              ELSE 'shoulder' END AS season
  FROM bookings b
  JOIN sailings s ON s.sailing_id = b.sailing_id
  WHERE b.status = 'confirmed'
)
SELECT season,
       CASE WHEN days_out >= 180 THEN '1) 180+ days'
            WHEN days_out >= 90  THEN '2) 90-179 days'
            WHEN days_out >= 30  THEN '3) 30-89 days'
            ELSE '4) 0-29 days' END AS booking_window,
       COUNT(*)                     AS bookings,
       ROUND(AVG(price_paid), 2)    AS raw_avg_price,
       ROUND(AVG(price_index), 3)   AS price_index_vs_same_sailing_cabin
FROM x
GROUP BY season, booking_window
ORDER BY season, booking_window;
