# Ola Cab Bookings — Data Dictionary (Validation Required)

## Critical note

This is a **candidate data dictionary**, not a verified description of the project's live SQL schema. The project database schema has not been supplied with this document request. Before indexing, inspect the actual database, replace/confirm table and column names, data types, units, distinct values, and business meanings, and remove fields that do not exist.

A common public Ola ride-bookings analytics dataset may include fields with names similar to those below. Names and meanings differ by dataset version.

## Candidate fields

| Candidate field | Possible meaning | Validation required |
|---|---|---|
| `Booking_ID` | Identifier for a booking | Confirm uniqueness, nullability, and whether repeated rows represent updates or duplicates. |
| `Booking_Status` | Recorded booking state | Query distinct values; document exactly which count as completed, cancelled, failed, or pending. |
| `Customer_ID` | Identifier for a customer | Confirm if present; treat as sensitive and avoid putting individual identifiers into RAG. |
| `Vehicle_Type` | Vehicle category recorded for the booking | Query distinct values; do not assume category labels are universal. |
| `Pickup_Location` | Pickup location or zone label | Confirm whether it is a human-readable place, anonymized zone, or coordinate. |
| `Drop_Location` | Drop location or zone label | Confirm meaning and any privacy restrictions. |
| `Booking_Value` | Monetary amount associated with a booking | Confirm currency, whether estimate or final value, and how cancellations/discounts are represented. |
| `Ride_Distance` | Recorded journey distance | Confirm unit (e.g. km or miles), actual versus estimated, and handling of zero/null values. |
| `Driver_Ratings` / `Customer_Rating` | Rating field | Confirm who rates whom, scale, timing, and valid range. Do not combine different rating directions. |
| `Payment_Method` | Payment label recorded on the booking | Confirm whether it reflects selection, request, or completed settlement. Query distinct values. |
| `Booking_Date` | Date of booking | Confirm type, timezone, and whether date-only or timestamp. |
| `Time` / `Booking_Time` | Booking time or time component | Confirm how it relates to booking timestamp and timezone. |
| `Cancelled_Rides` / cancellation flag | Cancellation marker or derived field | Confirm whether it is a native column or a prior transformation. Avoid counting both status and flag twice. |
| `Cancellation_Reason` | Recorded reason for cancellation | Confirm which actor supplied it and whether blanks mean unknown, not applicable, or missing. |

## Schema verification checklist

1. Inspect the database schema and exact table/column names.
2. Record data types, null rates, distinct categorical values, and min/max timestamps.
3. Confirm the grain: one row per booking, one row per event, or a mixture.
4. Check whether booking IDs repeat and identify any update/event semantics.
5. Verify currency and distance/time units.
6. Document the definition of completed, cancelled, unsuccessful, and pending statuses.
7. Confirm the correct date/timestamp to use for monthly analysis.
8. Document how missing, duplicate, refunded, cancelled, and incomplete records are handled.

## Questions this document must answer after validation

- What is the real table name?
- Is one row exactly one booking?
- Which status values exist in production data?
- Which monetary field should be used for a fare or revenue calculation?
- Which distance unit is used?
- What does each date/time column represent?
- Are cancellations recorded in status, a separate flag, or a related table?

Do not let the RAG assistant present candidate fields as facts about the live database until this document is validated.
