-- Question: What raw, audited, and clean structures does Phase 1 own?
CREATE SCHEMA IF NOT EXISTS hotel_booking;

CREATE TABLE IF NOT EXISTS hotel_booking.bookings_raw (
    source_record_number bigint PRIMARY KEY,
    hotel text,
    is_canceled text,
    lead_time text,
    arrival_date_year text,
    arrival_date_month text,
    arrival_date_week_number text,
    arrival_date_day_of_month text,
    stays_in_weekend_nights text,
    stays_in_week_nights text,
    adults text,
    children text,
    babies text,
    meal text,
    country text,
    market_segment text,
    distribution_channel text,
    is_repeated_guest text,
    previous_cancellations text,
    previous_bookings_not_canceled text,
    reserved_room_type text,
    assigned_room_type text,
    booking_changes text,
    deposit_type text,
    agent text,
    company text,
    days_in_waiting_list text,
    customer_type text,
    adr text,
    required_car_parking_spaces text,
    total_of_special_requests text,
    reservation_status text,
    reservation_status_date text
);

CREATE TABLE IF NOT EXISTS hotel_booking.bookings_quality (
    source_record_number bigint PRIMARY KEY
        REFERENCES hotel_booking.bookings_raw (source_record_number),
    hotel text,
    is_canceled integer,
    lead_time integer,
    arrival_date_year integer,
    arrival_date_month text,
    arrival_date_week_number integer,
    arrival_date_day_of_month integer,
    stays_in_weekend_nights integer,
    stays_in_week_nights integer,
    adults integer,
    children integer,
    babies integer,
    meal text,
    country text,
    market_segment text,
    distribution_channel text,
    is_repeated_guest integer,
    previous_cancellations integer,
    previous_bookings_not_canceled integer,
    reserved_room_type text,
    assigned_room_type text,
    booking_changes integer,
    deposit_type text,
    agent text,
    company text,
    days_in_waiting_list integer,
    customer_type text,
    adr numeric,
    required_car_parking_spaces integer,
    total_of_special_requests integer,
    reservation_status text,
    reservation_status_date date,
    arrival_date date,
    duplicate_group_size bigint NOT NULL CHECK (duplicate_group_size >= 1),
    exclusion_reasons text[] NOT NULL,
    quality_warnings text[] NOT NULL
);

CREATE OR REPLACE VIEW hotel_booking.bookings_clean AS
SELECT *
FROM hotel_booking.bookings_quality
WHERE cardinality(exclusion_reasons) = 0;

CREATE TABLE IF NOT EXISTS hotel_booking.load_audit (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    loaded_at timestamptz NOT NULL DEFAULT current_timestamp,
    source_filename text NOT NULL,
    source_sha256 text NOT NULL CHECK (length(source_sha256) = 64),
    cleaning_policy_version text NOT NULL DEFAULT 'phase1-v1',
    server_version text NOT NULL DEFAULT current_setting('server_version'),
    summary jsonb NOT NULL
);

