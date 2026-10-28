-- Question: Which eligible rows and audited candidate inputs feed the model?
-- Status fields are fetched ONLY so Python explicitly removes them. Both
-- reservation_status and reservation_status_date reveal future/outcome data.
-- Other fields come from a final extract; this is not a certified booking snapshot.
SELECT source_record_number, arrival_date, is_canceled,
       lead_time, is_repeated_guest, total_of_special_requests,
       adults, children, babies, hotel, market_segment, distribution_channel,
       deposit_type, customer_type, reservation_status, reservation_status_date
FROM hotel_booking.bookings_clean
ORDER BY arrival_date, source_record_number;

