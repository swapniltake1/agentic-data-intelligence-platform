# Ola Cab Bookings — Verified Analysis Insights

## Status: Template, not a findings report

No dataset-specific conclusions have been pre-filled because the live SQL schema and query results were not provided. Keep this document unindexed or index it only as a template until verified findings are added. Never invent totals, rankings, cancellation causes, or trends.

## How to add an insight

For each insight, record:

- **Title:** One sentence describing what the query directly showed.
- **Observation period:** Start/end dates and timezone.
- **Population and filters:** Statuses, cities/zones, vehicle types, and exclusions.
- **Metric definition:** Include denominator and treatment of duplicates/nulls.
- **Result:** Exact value, unit, and sample size.
- **SQL source:** Saved query, view, or commit reference.
- **Extracted at:** Timestamp when the query ran.
- **Limitations:** Missing fields, incomplete periods, sampling, or other caveats.
- **Interpretation:** Separate observed pattern from possible explanation.

## Insight template

### [Replace with a validated observation]

- **Observation period:** `[YYYY-MM-DD to YYYY-MM-DD, timezone]`
- **Table/view:** `[actual table or view]`
- **Metric:** `[metric and exact formula]`
- **Filters:** `[filters used]`
- **Result:** `[query result with units and sample size]`
- **SQL reference:** `[file path / query ID / commit]`
- **Extracted at:** `[timestamp]`
- **Limitations:** `[limitations]`
- **Interpretation:** `[what the result establishes; do not infer unsupported causation]`

## Example of careful wording (structure only)

> In the selected date range, `[vehicle category]` had the largest `[defined metric]` among categories with at least `[defined threshold]` eligible bookings. The query used `[date field]` and included `[status filters]`. This result describes the observed dataset; it does not by itself explain why the difference occurred.

Replace all bracketed values with SQL-verified results before indexing. Do not index this example as an actual finding.

## Good analytical questions to investigate

- How does completed-booking volume change by month?
- Which vehicle types have the highest cancellation rate under the approved denominator?
- Which pickup zones have the highest booking counts?
- How do average recorded booking values compare across vehicle categories?
- What share of records have missing distance, payment method, or rating?
- Are there duplicate booking IDs or conflicting statuses?

These are hypotheses/questions for analysis, not findings.
