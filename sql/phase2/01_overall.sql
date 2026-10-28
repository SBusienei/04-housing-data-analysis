-- Question: What share of all eligible booking records canceled?
SELECT count(*) AS bookings,
       sum(is_canceled) AS cancellations,
       avg(is_canceled::numeric) AS cancellation_rate
FROM hotel_booking.bookings_clean;

