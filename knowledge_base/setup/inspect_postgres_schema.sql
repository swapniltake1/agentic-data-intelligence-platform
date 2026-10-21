-- PostgreSQL schema-discovery helper for the Ola booking database.
-- Run with a role that has read access. Review results before updating the RAG data dictionary.
-- Replace public if your tables live in another schema.

-- 1) List base tables/views in the public schema.
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- 2) Show columns and SQL data types. Replace 'bookings' with your actual table name.
SELECT table_schema, table_name, ordinal_position, column_name, data_type,
       is_nullable, character_maximum_length, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'bookings'
ORDER BY ordinal_position;

-- 3) Check total rows and duplicate/null booking IDs. Adjust names first.
SELECT COUNT(*) AS row_count,
       COUNT(booking_id) AS non_null_booking_id_rows,
       COUNT(DISTINCT booking_id) AS distinct_booking_ids,
       COUNT(*) - COUNT(booking_id) AS null_booking_id_rows
FROM public.bookings;

-- 4) Inspect actual statuses; use the real status column and table name.
SELECT booking_status, COUNT(*) AS rows
FROM public.bookings
GROUP BY booking_status
ORDER BY rows DESC;

-- 5) Inspect payment method values, if such a column exists.
SELECT payment_method, COUNT(*) AS rows
FROM public.bookings
GROUP BY payment_method
ORDER BY rows DESC;

-- 6) Basic null profile for candidate columns. Remove columns that don't exist.
SELECT
  COUNT(*) AS total_rows,
  COUNT(*) FILTER (WHERE booking_status IS NULL) AS null_status_rows,
  COUNT(*) FILTER (WHERE vehicle_type IS NULL) AS null_vehicle_type_rows,
  COUNT(*) FILTER (WHERE booking_value IS NULL) AS null_booking_value_rows,
  COUNT(*) FILTER (WHERE ride_distance IS NULL) AS null_ride_distance_rows
FROM public.bookings;

-- NOTE: PostgreSQL names are case-sensitive only when created with quoted identifiers.
-- If the imported dataset uses quoted mixed-case names, use the exact quoted spelling.
