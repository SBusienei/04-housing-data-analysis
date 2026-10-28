-- Question: How do recorded market segments compare in cancellation rate?
SELECT market_segment, count(*) AS bookings, sum(is_canceled) AS cancellations,
       avg(is_canceled::numeric) AS cancellation_rate
FROM hotel_booking.bookings_clean
GROUP BY market_segment
ORDER BY market_segment NULLS LAST;

