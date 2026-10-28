-- Question: How do booking volume and cancellation rate compare across segments?
SELECT segment, count(*) AS bookings, sum(is_canceled) AS cancellations,
       count(*)::numeric / sum(count(*)) OVER () AS booking_share,
       avg(is_canceled::numeric) AS cancellation_rate
FROM hotel_booking.booking_segments
GROUP BY segment
ORDER BY bookings DESC, segment;

