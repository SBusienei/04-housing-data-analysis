-- Question: Which source records are eligible, and why is each flagged?
-- Temporary conversion functions live only in this connection's session.
CREATE OR REPLACE FUNCTION pg_temp.normalized(value text)
RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT CASE WHEN upper(btrim(value)) IN ('', 'NULL')
                THEN NULL ELSE btrim(value) END
$$;

CREATE OR REPLACE FUNCTION pg_temp.try_numeric(value text)
RETURNS numeric LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE parsed numeric;
BEGIN
    parsed := pg_temp.normalized(value)::numeric;
    IF parsed::text IN ('NaN', 'Infinity', '-Infinity') THEN
        RETURN NULL;
    END IF;
    RETURN parsed;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
    RETURN NULL;
END
$$;

CREATE OR REPLACE FUNCTION pg_temp.try_integer(value text)
RETURNS integer LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE parsed numeric;
BEGIN
    parsed := pg_temp.try_numeric(value);
    IF parsed IS NULL OR parsed <> trunc(parsed)
       OR parsed NOT BETWEEN -2147483648 AND 2147483647 THEN
        RETURN NULL;
    END IF;
    RETURN parsed::integer;
END
$$;

CREATE OR REPLACE FUNCTION pg_temp.safe_arrival(y integer, m integer, d integer)
RETURNS date LANGUAGE plpgsql IMMUTABLE STRICT AS $$
BEGIN
    IF y NOT BETWEEN 1 AND 9999 THEN
        RETURN NULL;
    END IF;
    RETURN make_date(y, m, d);
EXCEPTION WHEN datetime_field_overflow THEN
    RETURN NULL;
END
$$;

CREATE OR REPLACE FUNCTION pg_temp.try_iso_date(value text)
RETURNS date LANGUAGE plpgsql IMMUTABLE STRICT AS $$
BEGIN
    IF pg_temp.normalized(value) !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
        RETURN NULL;
    END IF;
    RETURN pg_temp.normalized(value)::date;
EXCEPTION WHEN datetime_field_overflow OR invalid_datetime_format THEN
    RETURN NULL;
END
$$;

WITH typed AS (
    SELECT
        r.source_record_number,
        pg_temp.normalized(r.hotel) AS hotel,
        pg_temp.try_integer(r.is_canceled) AS is_canceled,
        pg_temp.try_integer(r.lead_time) AS lead_time,
        pg_temp.try_integer(r.arrival_date_year) AS arrival_date_year,
        pg_temp.normalized(r.arrival_date_month) AS arrival_date_month,
        pg_temp.try_integer(r.arrival_date_week_number) AS arrival_date_week_number,
        pg_temp.try_integer(r.arrival_date_day_of_month) AS arrival_date_day_of_month,
        pg_temp.try_integer(r.stays_in_weekend_nights) AS stays_in_weekend_nights,
        pg_temp.try_integer(r.stays_in_week_nights) AS stays_in_week_nights,
        pg_temp.try_integer(r.adults) AS adults,
        pg_temp.try_integer(r.children) AS children,
        pg_temp.try_integer(r.babies) AS babies,
        pg_temp.normalized(r.meal) AS meal,
        pg_temp.normalized(r.country) AS country,
        pg_temp.normalized(r.market_segment) AS market_segment,
        pg_temp.normalized(r.distribution_channel) AS distribution_channel,
        pg_temp.try_integer(r.is_repeated_guest) AS is_repeated_guest,
        pg_temp.try_integer(r.previous_cancellations) AS previous_cancellations,
        pg_temp.try_integer(r.previous_bookings_not_canceled)
            AS previous_bookings_not_canceled,
        pg_temp.normalized(r.reserved_room_type) AS reserved_room_type,
        pg_temp.normalized(r.assigned_room_type) AS assigned_room_type,
        pg_temp.try_integer(r.booking_changes) AS booking_changes,
        pg_temp.normalized(r.deposit_type) AS deposit_type,
        pg_temp.normalized(r.agent) AS agent,
        pg_temp.normalized(r.company) AS company,
        pg_temp.try_integer(r.days_in_waiting_list) AS days_in_waiting_list,
        pg_temp.normalized(r.customer_type) AS customer_type,
        pg_temp.try_numeric(r.adr) AS adr,
        pg_temp.try_integer(r.required_car_parking_spaces)
            AS required_car_parking_spaces,
        pg_temp.try_integer(r.total_of_special_requests)
            AS total_of_special_requests,
        pg_temp.normalized(r.reservation_status) AS reservation_status,
        pg_temp.try_iso_date(r.reservation_status_date) AS reservation_status_date,
        pg_temp.safe_arrival(
            pg_temp.try_integer(r.arrival_date_year),
            array_position(
                ARRAY['january', 'february', 'march', 'april', 'may', 'june',
                      'july', 'august', 'september', 'october', 'november', 'december'],
                lower(pg_temp.normalized(r.arrival_date_month))
            ),
            pg_temp.try_integer(r.arrival_date_day_of_month)
        ) AS arrival_date,
        count(*) OVER (
            PARTITION BY to_jsonb(r) - 'source_record_number'
        ) AS duplicate_group_size
    FROM hotel_booking.bookings_raw AS r
), flagged AS (
    SELECT t.*,
        ARRAY(
            SELECT 'invalid_or_missing_integer:' || field_name
            FROM unnest(ARRAY[
                'is_canceled', 'lead_time', 'arrival_date_year',
                'arrival_date_week_number', 'arrival_date_day_of_month',
                'stays_in_weekend_nights', 'stays_in_week_nights',
                'adults', 'babies', 'is_repeated_guest',
                'previous_cancellations', 'previous_bookings_not_canceled',
                'booking_changes', 'days_in_waiting_list',
                'required_car_parking_spaces', 'total_of_special_requests'
            ]) AS fields(field_name)
            WHERE to_jsonb(t) ->> field_name IS NULL
        )
        || ARRAY(
            SELECT 'negative_count:' || field_name
            FROM unnest(ARRAY[
                'lead_time', 'stays_in_weekend_nights', 'stays_in_week_nights',
                'adults', 'children', 'babies', 'previous_cancellations',
                'previous_bookings_not_canceled', 'booking_changes',
                'days_in_waiting_list', 'required_car_parking_spaces',
                'total_of_special_requests'
            ]) AS fields(field_name)
            WHERE (to_jsonb(t) ->> field_name)::bigint < 0
        )
        || array_remove(ARRAY[
            CASE WHEN t.hotel IS NULL THEN 'missing_hotel' END,
            CASE WHEN t.is_canceled NOT IN (0, 1) THEN 'invalid_cancellation_label' END,
            CASE WHEN t.is_repeated_guest NOT IN (0, 1) THEN 'invalid_repeat_label' END,
            CASE WHEN t.arrival_date_week_number NOT BETWEEN 1 AND 53
                 THEN 'invalid_arrival_week' END,
            CASE WHEN t.arrival_date IS NULL THEN 'invalid_arrival_date' END,
            CASE WHEN t.children IS NULL
                      AND pg_temp.normalized(r.children) IS NOT NULL
                 THEN 'invalid_children' END,
            CASE WHEN t.adr IS NULL AND pg_temp.normalized(r.adr) IS NOT NULL
                 THEN 'invalid_adr' END,
            CASE WHEN t.adults = 0 AND t.children = 0 AND t.babies = 0
                 THEN 'zero_guests' END
        ], NULL) AS exclusion_reasons,
        array_remove(ARRAY[
            CASE WHEN pg_temp.normalized(r.children) IS NULL
                 THEN 'unknown_guest_count' END,
            CASE WHEN t.country IS NULL THEN 'missing_country' END,
            CASE WHEN t.agent IS NULL THEN 'missing_agent' END,
            CASE WHEN t.company IS NULL THEN 'missing_company' END,
            CASE WHEN t.market_segment IS NULL OR t.distribution_channel IS NULL
                      OR t.deposit_type IS NULL OR t.customer_type IS NULL
                 THEN 'missing_analysis_category' END,
            CASE WHEN t.adr IS NULL AND pg_temp.normalized(r.adr) IS NULL
                 THEN 'missing_adr' END,
            CASE WHEN t.adr < 0 THEN 'negative_adr_review' END,
            CASE WHEN t.stays_in_weekend_nights = 0 AND t.stays_in_week_nights = 0
                 THEN 'zero_nights_review' END,
            CASE WHEN t.hotel NOT IN ('City Hotel', 'Resort Hotel')
                 THEN 'unexpected_hotel_category' END,
            CASE WHEN t.arrival_date_year NOT BETWEEN 2015 AND 2017
                 THEN 'outside_original_year_coverage' END,
            CASE WHEN t.reservation_status_date IS NULL
                      AND pg_temp.normalized(r.reservation_status_date) IS NOT NULL
                 THEN 'invalid_status_date' END,
            CASE WHEN t.duplicate_group_size > 1 THEN 'exact_duplicate_member' END
        ], NULL) AS quality_warnings
    FROM typed AS t
    JOIN hotel_booking.bookings_raw AS r USING (source_record_number)
)
INSERT INTO hotel_booking.bookings_quality
SELECT * FROM flagged;

