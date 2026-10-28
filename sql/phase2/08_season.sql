-- Question: How do arrival-season cancellation rates compare within each year?
-- Calendar convention, not a learned definition of hotel demand seasons.
WITH seasonal AS (
    SELECT extract(year FROM arrival_date)::integer AS arrival_year,
           CASE
               WHEN extract(month FROM arrival_date) IN (12, 1, 2) THEN '01: Winter'
               WHEN extract(month FROM arrival_date) IN (3, 4, 5) THEN '02: Spring'
               WHEN extract(month FROM arrival_date) IN (6, 7, 8) THEN '03: Summer'
               ELSE '04: Autumn'
           END AS season,
           is_canceled
    FROM hotel_booking.bookings_clean
)
SELECT arrival_year, season, count(*) AS bookings, sum(is_canceled) AS cancellations,
       avg(is_canceled::numeric) AS cancellation_rate
FROM seasonal
GROUP BY arrival_year, season
ORDER BY arrival_year, season;

