-- Question: How does cancellation rate vary by predeclared lead-time band?
WITH banded AS (
    SELECT CASE
               WHEN lead_time < 30 THEN '01: under 30 days'
               WHEN lead_time < 90 THEN '02: 30-89 days'
               ELSE '03: 90+ days'
           END AS lead_time_band,
           is_canceled
    FROM hotel_booking.bookings_clean
)
SELECT lead_time_band, count(*) AS bookings, sum(is_canceled) AS cancellations,
       avg(is_canceled::numeric) AS cancellation_rate
FROM banded
GROUP BY lead_time_band
ORDER BY lead_time_band;

