-- Run in the AWS Athena console after aws/upload_to_s3.py.
-- Replace YOUR-BUCKET with your bucket name. Set a query result location in Athena settings first.

CREATE DATABASE IF NOT EXISTS cruise;

CREATE EXTERNAL TABLE IF NOT EXISTS cruise.bookings (
  booking_id     BIGINT,
  guest_id       BIGINT,
  sailing_id     BIGINT,
  cabin_category STRING,
  booking_date   TIMESTAMP,
  guests         BIGINT,
  price_paid     DOUBLE,
  promo_code     STRING,
  channel        STRING,
  source_market  STRING,
  status         STRING,
  cancel_date    TIMESTAMP,
  price_imputed  BOOLEAN,
  days_out       BIGINT,
  is_cancelled   BOOLEAN
)
PARTITIONED BY (sail_year INT)
STORED AS PARQUET
LOCATION 's3://YOUR-BUCKET/cruise/bookings/';

-- Load the sail_year=YYYY folders as partitions
MSCK REPAIR TABLE cruise.bookings;

CREATE EXTERNAL TABLE IF NOT EXISTS cruise.sailings (
  sailing_id BIGINT, ship_id BIGINT, sail_date TIMESTAMP, nights BIGINT, itinerary STRING
)
STORED AS PARQUET
LOCATION 's3://YOUR-BUCKET/cruise/sailings/';

CREATE EXTERNAL TABLE IF NOT EXISTS cruise.cabin_inventory (
  sailing_id BIGINT, cabin_category STRING, cabins_available BIGINT
)
STORED AS PARQUET
LOCATION 's3://YOUR-BUCKET/cruise/cabin_inventory/';

-- ---------- Example analysis queries ----------

-- Occupancy by sailing (Athena scans only the 2026 partition)
WITH booked AS (
  SELECT sailing_id, COUNT(*) AS cabins_booked, SUM(price_paid) AS revenue
  FROM cruise.bookings
  WHERE sail_year = 2026 AND status = 'confirmed'
  GROUP BY sailing_id
), cap AS (
  SELECT sailing_id, SUM(cabins_available) AS cabins FROM cruise.cabin_inventory GROUP BY sailing_id
)
SELECT b.sailing_id, s.sail_date, b.cabins_booked, c.cabins,
       ROUND(100.0 * b.cabins_booked / c.cabins, 1) AS occupancy_pct,
       ROUND(b.revenue / c.cabins, 2)              AS revenue_per_available_cabin
FROM booked b
JOIN cap c       ON c.sailing_id = b.sailing_id
JOIN cruise.sailings s ON s.sailing_id = b.sailing_id
ORDER BY occupancy_pct;

-- Average price by booking window
SELECT CASE WHEN days_out >= 180 THEN '180+'
            WHEN days_out >= 90  THEN '90-179'
            WHEN days_out >= 30  THEN '30-89'
            ELSE '0-29' END AS booking_window,
       COUNT(*) AS bookings, ROUND(AVG(price_paid), 2) AS avg_price
FROM cruise.bookings
WHERE status = 'confirmed'
GROUP BY 1
ORDER BY 1;
