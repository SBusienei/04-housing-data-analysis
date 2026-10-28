-- Question: Which transparent behavior segment contains each eligible booking?
-- First match wins. Missing channel/deposit cannot satisfy the advance rule.
CREATE OR REPLACE VIEW hotel_booking.booking_segments AS
SELECT source_record_number, arrival_date, hotel, is_canceled,
       CASE
           WHEN is_repeated_guest = 1 THEN 'Returning guest'
           WHEN lead_time >= 90 AND distribution_channel = 'TA/TO'
                AND deposit_type = 'No Deposit'
               THEN 'Advance agency, no deposit'
           WHEN total_of_special_requests >= 1 THEN 'Other with requests'
           ELSE 'Other bookings'
       END AS segment
FROM hotel_booking.bookings_clean;

