-- Question: How does cancellation rate vary by recorded customer type?
SELECT customer_type, count(*) AS bookings, sum(is_canceled) AS cancellations,
       avg(is_canceled::numeric) AS cancellation_rate
FROM hotel_booking.bookings_clean
GROUP BY customer_type
ORDER BY customer_type NULLS LAST;

