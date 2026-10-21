# Ola Cab Bookings — KPI Glossary

## Purpose

This glossary standardizes analytical terms. Each KPI should be calculated in SQL from the validated schema, not guessed by the RAG language model. Confirm definitions with project requirements before publishing results.

## Booking count

**Definition:** Number of distinct eligible bookings in the selected scope.

**Suggested formula:** `COUNT(DISTINCT booking_id)` when booking ID uniqueness and grain have been validated.

**Caution:** If one row represents a status event or line item, row count is not booking count.

## Completed bookings / completion rate

**Completed bookings:** Distinct bookings whose validated status is classified as completed.

**Completion rate:** `completed eligible bookings / eligible bookings * 100`.

Define what belongs in the denominator. Exclude test rows and duplicates only with documented rules.

## Cancelled bookings / cancellation rate

**Cancelled bookings:** Distinct bookings whose validated state is classified as cancelled under the project definition.

**Cancellation rate:** `cancelled eligible bookings / eligible bookings * 100`.

Document whether the denominator includes all booking attempts, only created bookings, or another population. Do not count failed requests or no-driver events as cancellations unless the business definition says to.

## Total recorded booking value

**Definition:** Sum of the validated monetary field for rows that meet the stated inclusion rules.

**Caution:** This is not automatically revenue. Identify whether the amount is an estimate, gross fare, final fare, amount collected, or another concept. Define treatment of cancelled rides, discounts, taxes, tolls, refunds, and adjustments.

## Average recorded fare / average booking value

**Definition:** Sum of the chosen amount divided by the number of eligible bookings with a valid amount.

**Caution:** State whether the calculation is based on completed trips only and how missing values are treated. Never silently treat missing amounts as zero.

## Average ride distance

**Definition:** Sum of valid ride distance values divided by the number of eligible records with valid distance values.

**Caution:** Confirm distance units and whether distance is measured or estimated. Consider median and percentiles if the distribution is skewed.

## Average rating

**Definition:** Arithmetic average of a validated rating field over records where a rating is present.

**Caution:** Confirm who gave the rating, scale, valid values, and whether multiple ratings exist per booking. Report sample size with the average.

## Vehicle-type contribution

**Definition:** The count, percentage, or monetary total associated with a vehicle category under explicit inclusion rules.

**Caution:** Keep count share and value share distinct. Vehicle categories may be recorded differently across data versions.

## Peak-hour demand

**Definition:** Number of eligible bookings grouped by a consistently defined hour or time window.

**Caution:** Specify timezone, timestamp field, and window boundaries. Bookings by booking time and trips by trip-start time answer different questions.

## Data-quality KPIs

- **Missing-field rate:** eligible records with a null/blank value divided by eligible records.
- **Duplicate-ID rate:** records participating in a duplicate booking ID under the chosen grain definition; define how duplicates are identified.
- **Invalid-value count:** rows failing documented validation rules, such as a negative distance if negative distance is not allowed by the source definition.

## Required metadata for any KPI answer

Whenever practical, include: metric definition, date range, timezone, table, filters, denominator, row/booking count, treatment of nulls/duplicates, and query or report timestamp.
