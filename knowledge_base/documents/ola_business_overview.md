# Ola Cab Booking — Business and Domain Overview

## Purpose

Ola is a ride-booking service. A booking-data analytics project can examine demand, fulfillment, vehicle categories, ride distance, fare amounts, payment records, customer ratings, and cancellation patterns where those fields exist in the dataset.

Ola's developer documentation describes workflows for ride availability and estimates, creating bookings, tracking a ride, and cancelling bookings. The developer platform's published access description says API integration is invite-only/partner-based; public documentation does not mean that a project has credentials or permission to call the live API.

Primary references:
- Developer API overview: https://developers.olacabs.com/docs/overview
- Ride estimate and availability: https://developers.olacabs.com/docs/ride-estimate
- Cab booking: https://developers.olacabs.com/docs/cab-booking
- Cab ride tracking: https://developers.olacabs.com/docs/cab-track-ride
- Cancellation: https://developers.olacabs.com/docs/ride-cancel

## Common concepts

- **Booking**: A record that identifies a request for a ride. In an analytics dataset it may be identified by a booking ID.
- **Booking status**: A recorded state of the booking. Exact labels depend on the source and the dataset's transformations. Use actual distinct values from the database rather than assuming that every dataset uses the same status vocabulary.
- **Vehicle or ride category**: A type/category selected or recorded for the ride. Category names vary across services, markets, and data versions.
- **Pickup and drop locations**: Locations associated with the journey. A dataset may store human-readable place names, coordinates, zones, or anonymized labels.
- **Ride distance and duration**: Journey measurements. Always confirm units and whether a field is estimated or actual.
- **Booking value / fare**: A monetary amount recorded in a particular stage of the booking or trip. A field named `Booking_Value` must not automatically be treated as realized revenue.
- **Cancellation**: A booking that did not proceed or was cancelled. The actor, timing, reason, and financial consequence should be analyzed separately when those fields exist.
- **Customer rating**: A recorded rating, if present. Confirm the scale and whether it is a driver rating, customer rating, or trip rating.

## What this knowledge base can and cannot answer

This document can explain domain terminology and point to official technical documentation. It cannot tell the current live fare for a location, confirm a specific booking, look up a customer's account, or establish the result of a query on the project's SQL database.

Ask SQL for data-specific values, for example:
- Which vehicle type has the largest total booking value?
- How many bookings were completed in a particular month?
- Which locations have the highest cancellation rate?

Ask RAG for documented concepts, for example:
- What does a booking lifecycle mean?
- Which fields should be checked before calculating a cancellation rate?
- What is the difference between an estimate and a recorded fare?

## Analytical caution

Observed correlation is not proof of cause. A concentration of cancellations in one location does not, on its own, prove that driver availability, price, weather, or any other factor caused them. State only what the data supports, and label hypotheses as hypotheses.
