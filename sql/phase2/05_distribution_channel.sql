-- Question: How does cancellation rate differ by distribution channel?
SELECT distribution_channel, count(*) AS bookings, sum(is_canceled) AS cancellations,
       avg(is_canceled::numeric) AS cancellation_rate
FROM hotel_booking.bookings_clean
GROUP BY distribution_channel
ORDER BY distribution_channel NULLS LAST;

