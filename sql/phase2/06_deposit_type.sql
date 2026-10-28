-- Question: How do deposit arrangements compare in cancellation rate?
SELECT deposit_type, count(*) AS bookings, sum(is_canceled) AS cancellations,
       avg(is_canceled::numeric) AS cancellation_rate
FROM hotel_booking.bookings_clean
GROUP BY deposit_type
ORDER BY deposit_type NULLS LAST;

