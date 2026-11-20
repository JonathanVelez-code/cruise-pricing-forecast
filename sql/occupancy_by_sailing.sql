-- Occupancy, revenue and RevPAC for every sailing (open sailings show what's booked so far)
WITH booked AS (
  SELECT sailing_id,
         COUNT(*)        AS cabins_booked,
         SUM(price_paid) AS revenue
  FROM bookings
  WHERE status = 'confirmed'
  GROUP BY sailing_id
), capacity AS (
  SELECT sailing_id, SUM(cabins_available) AS cabins
  FROM cabin_inventory
  GROUP BY sailing_id
)
SELECT s.sailing_id,
       sh.ship_name,
       s.sail_date,
       s.nights,
       c.cabins,
       COALESCE(b.cabins_booked, 0)                                   AS cabins_booked,
       ROUND(100.0 * COALESCE(b.cabins_booked, 0) / c.cabins, 1)      AS occupancy_pct,
       ROUND(COALESCE(b.revenue, 0), 2)                               AS revenue,
       ROUND(COALESCE(b.revenue, 0) / c.cabins, 2)                    AS revenue_per_available_cabin
FROM sailings s
JOIN ships sh     ON sh.ship_id = s.ship_id
JOIN capacity c   ON c.sailing_id = s.sailing_id
LEFT JOIN booked b ON b.sailing_id = s.sailing_id
ORDER BY s.sail_date, sh.ship_name;
