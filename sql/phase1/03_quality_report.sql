-- Question: Do raw, eligible, and excluded bookings reconcile after cleaning?
SELECT
    count(*) AS raw_rows,
    count(*) FILTER (WHERE cardinality(exclusion_reasons) = 0) AS retained_rows,
    count(*) FILTER (WHERE cardinality(exclusion_reasons) > 0) AS excluded_rows,
    count(*) FILTER (WHERE cardinality(quality_warnings) > 0) AS warning_rows,
    count(*) FILTER (WHERE 'zero_guests' = ANY(exclusion_reasons)) AS zero_guest_rows,
    count(*) FILTER (
        WHERE 'unknown_guest_count' = ANY(quality_warnings)
    ) AS unknown_guest_rows,
    count(*) FILTER (
        WHERE 'invalid_arrival_date' = ANY(exclusion_reasons)
    ) AS invalid_date_rows,
    (
        SELECT count(*) - count(DISTINCT (to_jsonb(r) - 'source_record_number'))
        FROM hotel_booking.bookings_raw AS r
    ) AS duplicate_excess_rows
FROM hotel_booking.bookings_quality;

