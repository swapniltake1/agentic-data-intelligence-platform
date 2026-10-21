# Ola Cab Booking — Ride Lifecycle and Status Concepts

## Overview

A ride-booking workflow can involve ride availability and estimation, booking creation, assignment/driver contact, driver arrival at pickup, trip start, completion, and possible cancellation. Exact states and transitions depend on the product/API version and source dataset.

The Ola developer documentation provides booking and tracking endpoints:
- Booking creation: https://developers.olacabs.com/docs/cab-booking
- Tracking a cab ride: https://developers.olacabs.com/docs/cab-track-ride
- Cancellation: https://developers.olacabs.com/docs/ride-cancel

## Example API statuses

The cab-tracking documentation includes example values such as `CALL_DRIVER`, `CLIENT_LOCATED`, `IN_PROGRESS`, and `COMPLETED`. The cancellation documentation includes failure cases associated with `BOOKING_ALREADY_CANCELLED`, `RIDE_IN_PROGRESS`, and `BOOKING_ALREADY_COMPLETED`. Treat these as documented API examples, not as an exhaustive dictionary for every analytics dataset.

## Conceptual stages

1. **Estimate/availability** — available categories, ETA, and fare estimates may be returned for the requested context.
2. **Booking created** — a booking request has been created and is associated with an identifier.
3. **Driver/vehicle assigned or contact available** — assignment and driver details may be returned once available.
4. **Driver at pickup** — tracking data may indicate the driver has reached the pickup location.
5. **Trip in progress** — the ride has started.
6. **Completed** — the ride has reached a completed state in the source system.
7. **Cancelled/failed** — a ride or booking did not proceed; cancellation, request failure, and no-driver outcomes may be different categories in a dataset.

This is a conceptual description. Do not force all records into these stages unless the dataset supports that mapping.

## How to interpret status in an analytics dataset

- Query actual distinct status values before building a status mapping.
- Preserve the original status string in the raw layer.
- Separate terminal statuses from intermediate states.
- Do not equate every non-completed booking with a customer cancellation.
- If the dataset combines statuses, document the mapping and its business rationale.
- Check for duplicate booking identifiers and conflicting status records before counting bookings.

## Frequently asked questions

### Does every dataset use `COMPLETED`?

No universal assumption should be made. Use the actual status values in the source database and any accompanying dataset documentation.

### Does a missing or failed booking mean the customer cancelled?

Not necessarily. It may reflect cancellation, an unsuccessful request, no available driver, missing data, or a source-specific category. Inspect the actual schema and documentation.

### How should I count completed rides?

Use the validated completed status or status mapping for this dataset, ensure booking-level uniqueness, and state the applicable date field and filters.

## Technical integration warning

The public API documentation describes partner integration and uses authorization headers/tokens in example requests. Never copy sample credentials or response personal details into source code, prompts, or this knowledge base. Real API usage requires legitimate access and secure credential handling.
