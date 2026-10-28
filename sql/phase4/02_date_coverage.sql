-- Question: Which arrival months have enough examples of each outcome for a split?
-- Inspect coverage before choosing dates; do not optimize cutoffs for model scores.
SELECT date_trunc('month', arrival_date)::date AS arrival_month,
       count(*) FILTER (WHERE is_canceled = 0) AS noncanceled_bookings,
       count(*) FILTER (WHERE is_canceled = 1) AS canceled_bookings
FROM hotel_booking.bookings_clean
GROUP BY arrival_month
ORDER BY arrival_month;

