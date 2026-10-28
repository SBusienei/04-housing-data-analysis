-- Question: How do cancellations vary by scheduled arrival month and hotel?
SELECT date_trunc('month', arrival_date)::date AS arrival_month,
       hotel, count(*) AS bookings, sum(is_canceled) AS cancellations,
       avg(is_canceled::numeric) AS cancellation_rate
FROM hotel_booking.bookings_clean
GROUP BY arrival_month, hotel
ORDER BY arrival_month, hotel;

