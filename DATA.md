# Data and cleaning decisions - Phase 1

## Source, unit, and scope

Download Kaggle's **Hotel Booking Demand** `hotel_bookings.csv` yourself and put
the unchanged file in `data\raw\`. The loader expects the original column names
and order listed in `src\csv_source.py`. A row is a booking record, not a person,
room night, or guaranteed completed stay.

The original dataset covers two hotels in one country (Portugal), with data from
2015-2017. Verify field definitions against the
[original dataset publication](https://doi.org/10.1016/j.dib.2018.11.126).
This repository has not yet analyzed your downloaded data.

**Policy version:** `phase1-v1`. These are explicit starting decisions for your
Phase 1 review, not conclusions about issues observed in your file.

## Layers in PostgreSQL

| Object in `hotel_booking` | Purpose |
|---|---|
| `bookings_raw` | Original parsed cell strings, including whitespace, empty strings, and literal `NULL` tokens. |
| `bookings_quality` | One typed row per raw record with exclusion reasons and review warnings. Includes excluded records. |
| `bookings_clean` | A SQL **view**, not a second stored copy. Includes only quality rows with an empty `exclusion_reasons` array. Warnings remain visible. |
| `load_audit` | Latest successful snapshot's source filename, SHA-256, server version, policy version, load time, and reconciled counts. |

`source_record_number` is a synthetic reference back to the CSV: the header is
record 1 and the first data record is 2. Quoted cells may span physical lines, so
this is a CSV record number, not a guaranteed text-editor line number. It is not
a verified booking identifier.

## Parsing and missing values

- Read UTF-8, accepting an optional UTF-8 BOM. Require the exact original headers
  and number of fields. Reject malformed CSV, invalid encoding, NUL characters,
  and empty datasets with an explicit error before committing anything.
- Keep original strings in the raw layer. In typed fields only, trim surrounding
  spaces and map empty strings and case-insensitive `NULL` to SQL NULL.
  Do not treat other strings, including `NA`, `Undefined`, or `Unknown`, as missing
  without a later documented decision.
- Keep missing country, agent, company, and analysis categories as NULL; do not
  guess them. Missing categories remain eligible and receive a warning.
  Agent/company are identifiers kept as text, not numerical measures.
- Keep missing `children` as NULL, flag `unknown_guest_count`, and retain the
  booking if it passes other rules. This does **not** establish zero children.
- Required integer fields: cancellation label, lead time, arrival year/week/day,
  weekend/weekday nights, adults, babies, repeat flag, previous cancellations,
  previous non-canceled bookings, booking changes, waiting-list days, parking
  spaces, and special requests. Missing or invalid values exclude the row.
- Accept exact integral numeric forms such as `0`, `0.0`, and `2.0`.
  Fractional counts, non-finite numeric values, and values outside the PostgreSQL
  integer range are invalid. Never round fractional counts.
- Missing ADR remains NULL with a warning. A nonmissing value that cannot be
  parsed as a finite numeric value excludes the row.

No statistical imputation is fitted in Phase 1. Any future model imputation must
learn its parameters on training data only.

## Impossible, invalid, and unusual values

| Condition | Decision | Why |
|---|---|---|
| Cancellation or repeat flag is not 0/1 | Exclude; preserve reason. | Invalid binary label/input. |
| Negative lead time, guest count, night count, prior booking count, booking changes, waiting days, parking count, or request count | Exclude. | Violates the nonnegative count definition. |
| Adults, children, and babies are all known zero | Exclude as `zero_guests`. | Outside a guest-booking analytical population. |
| Adults and babies are zero, children missing | Retain with unknown-guest warning if otherwise valid. | Unknown is not confirmed zero. |
| Adults zero but children/babies positive | Retain if otherwise valid. | Not a zero-guest booking; no extra minimum-adult rule is assumed. |
| Hotel missing | Exclude. | Cannot attribute the record to a hotel. |
| Hotel label differs from the original categories | Retain with warning for review. | Unusual category is not automatically an invalid booking. |
| Arrival week outside 1-53 | Exclude. | Invalid supplied week number. |
| ADR negative | Retain with `negative_adr_review`. | Could reflect an adjustment or source issue; do not invent a correction. |
| ADR unusually high | No arbitrary cap/filter. | A defensible outlier threshold requires inspecting actual values. |
| Total nights zero | Retain with `zero_nights_review`. | Could be an unusual administrative/day-use record; review rather than silently delete. |

These policies define the analysis population. Review exclusions before trusting
later rates. Reassess ambiguous warnings with actual source evidence, version the
policy if it changes, and rerun the snapshot.

## Dates

- Construct `arrival_date` using the integer year/day and an explicit English
  month-name map, case-insensitive. Require year 1-9999 and an actual calendar
  date. Impossible dates, missing pieces, and unknown months yield NULL in the
  quality table and an explicit `invalid_arrival_date` exclusion.
- Preserve the supplied week number separately. Do not silently replace it with
  an ISO-week calculation; these definitions may differ.
- Arrival years outside 2015-2017 trigger a coverage warning, not automatic
  deletion. The loader does not silently restrict the file to expected years.
- Parse `reservation_status_date` only as ISO `YYYY-MM-DD`. Invalid nonmissing
  values become NULL with `invalid_status_date`; retain the booking if otherwise
  eligible. This field is for historical auditing, not a prediction input.
- Scheduled arrival date is **not** booking creation date or cancellation date.
  Future chronological modeling must document its chosen date and label
  availability. A later-arrival holdout is not a perfect booking-time backtest.

## Duplicates

Retain identical records: the source has no trusted unique booking ID and
different bookings may share all recorded attributes.

`duplicate_group_size` compares all original raw cells, excluding the synthetic
record number. Consequently `0` and `0.0`, or strings with different surrounding
whitespace, are not exact raw duplicates. Each group member is flagged
`exact_duplicate_member`. `duplicate_excess_rows` is the number of records beyond
the first in every identical group, **not** the number of flagged members.
These records are not removed.

## Reconciliation and review counts

The loader checks `raw_rows = retained_rows + excluded_rows`.
Exclusions and warnings are arrays: one record can have multiple issues.
Do not sum overlapping issue counts to get excluded rows. Warning counts include
both retained and excluded records.

| Measure | Dataset finding |
|---|---|
| Raw booking records | [RESULT: raw booking count] |
| Eligible booking records | [RESULT: retained booking count] |
| Excluded booking records | [RESULT: excluded booking count] |
| Confirmed zero-guest records | [RESULT: zero-guest count] |
| Unknown-children records | [RESULT: unknown-guest count] |
| Invalid arrival dates | [RESULT: invalid-date count] |
| Exact duplicate excess | [RESULT: duplicate excess count] |

Read actual counts from `hotel_booking.load_audit` after importing your file.
No values from fictional tests or the learning guide belong in this table.

## Model leakage and generalization

Phase 1 retains status fields for auditing. When Phase 4 is approved,
**explicitly exclude `reservation_status` and `reservation_status_date` from model
inputs** because they describe the outcome/future information. Audit all other
feature timestamps; dropping these two alone does not establish a safe
booking-time feature set. Use an explicit feature allowlist.

No model has been fitted or validated on the real dataset, including on other
markets. Any future model remains limited by two hotels in one country, data
from 2015-2017, and lack of external-market validation.

## Prepared model-only preprocessing (run later)

The Phase 4 starter does not modify any database cleaning decisions or replace
missing values in `bookings_clean`. Its in-memory pipeline learns numeric
medians and scaling only from the training partition. Entirely missing numeric
training features cause an explicit error because no median can be learned.
Missing model categories use an explicit `Unknown` category; later unseen
categories are handled by the training-fitted one-hot encoder.

The candidate input allowlist is defined in `src\model.py`; snapshot limitations
are described in README.md.
Status/status-date are explicitly dropped before the allowlist is selected.
Special requests, deposit arrangement, and other final-extract values still need
a timing audit. The command requires acknowledgment that the later-arrival
holdout is exploratory, not a reconstruction of booking-time deployment.

No feature threshold, imputation parameter, or decision threshold is learned from
final-test labels. Alert thresholds use earlier validation F1 on a declared
fixed grid; results and counted calibration checks use final-test data only.
Generated output manifests record source snapshot and prediction checksums.

## Reloads and provenance

The original CSV is never rewritten. Each successful load is one current
snapshot; the audit table is not a history of all runs. The loader requires
`--replace` when a snapshot exists and replaces only its three managed tables
atomically, without `CASCADE`. Related downstream foreign keys can block a
replacement rather than silently deleting their data. Failures roll back the
new snapshot; an existing committed snapshot stays intact.

The loader compares source checksums before validation, after validation, and
after streaming the import. Keep the source file stable during execution.
