# Ola Booking Cancellations — FAQ

## Documented API behavior

The published Ola cab-cancellation API documentation describes cancellation requests for rides before the ride has started. A cancellation request includes a booking identifier and a reason selected from acceptable options. The documentation shows failure cases for a booking that is already cancelled, a ride that is in progress, or a booking that is already completed.

The documentation also states that accepted cancellation reasons can differ by category and pickup location. It describes a cancellation-policy object in the response, meaning cancellation charges and timing should be checked from the applicable response rather than assumed to be universal.

Official reference: https://developers.olacabs.com/docs/ride-cancel

## Frequently asked questions

### Can an in-progress ride be cancelled through the documented cancellation endpoint?

The published endpoint documentation shows an in-progress ride as a cancellation failure case. For a real customer issue, use the current official support flow rather than relying only on this technical reference.

### Are cancellation reasons the same for every ride?

Not necessarily. The documentation says available reasons can vary by ride category and pickup location. Rental cancellation reasons may depend on the sub-category.

### Is there one fixed cancellation fee for every Ola ride?

This knowledge base does not assert a universal fee. The API documentation's examples are location/category-specific example payloads; actual charges must be verified from a current applicable policy or authorized response.

### How should cancellation rate be calculated?

Choose and document a clear definition, for example:

`cancellation_rate = cancelled_bookings / eligible_bookings * 100`

Define exactly which statuses count as cancelled, what the denominator includes, and whether no-driver/failed booking attempts are included. Do not divide cancelled rides by completed rides alone and label the result as cancellation rate.

### Which cancellation reasons are most common?

Use SQL over the actual cancellation-reason column and only include rows with a defined cancellation status. The answer should include the date range and missing/unknown reason handling. RAG should not invent the most common reason.

### Can cancellation reason explain why cancellations happen?

A recorded reason describes the value stored in the data. It may be self-reported or standardized, and it does not always prove the underlying cause. Avoid converting a reason category into a stronger causal claim without corroborating evidence.

## Recommended analytics dimensions

Where available, compare cancellation counts and rates by booking date, pickup zone, vehicle category, booking hour, customer/driver cancellation actor, and recorded cancellation reason. Use a clearly stated denominator and compare like-for-like periods.

## Source boundary

This page summarizes the publicly accessible developer API documentation. It is not a guarantee of current consumer policy or any customer's cancellation-charge outcome. Official support: https://help.olacabs.com/support
