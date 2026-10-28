-- Question: How does cancellation rate differ by hotel type?
SELECT hotel, count(*) AS bookings, sum(is_canceled) AS cancellations,
       avg(is_canceled::numeric) AS cancellation_rate
FROM hotel_booking.bookings_clean
GROUP BY hotel
ORDER BY hotel;

