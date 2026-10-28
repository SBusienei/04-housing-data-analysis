# Hotel Booking Cancellation Analysis

A SQL-first data analysis and machine-learning project exploring hotel booking
cancellations, booking behavior, and interpretable cancellation-risk prediction.
The project combines PostgreSQL analysis, documented data-quality rules,
behavior-based segmentation, and chronological model evaluation.

**Status:** the workflow and supporting code are implemented as a project
scaffold. Analysis of the real dataset, model findings, and the dashboard are
pending. No measured business impact is claimed.

## Business problem

Hotel cancellations create uncertainty in room availability and operational
planning. A booking platform's operations team needs to understand historical
cancellation patterns and identify bookings that may warrant additional
attention.

This project investigates:

- How cancellation rates vary across booking characteristics and arrival periods.
- Which understandable booking segments have different cancellation patterns.
- Whether interpretable models can identify higher-risk bookings in a later period.
- How analysis outputs can support a dashboard and inform hypotheses for
  operational testing.

The analysis distinguishes **historical association**, **risk prediction**, and
**evidence that an intervention works**. Predicting a cancellation does not prove
that a reminder, deposit change, or other action will prevent it.

## Dataset

The project uses the **Hotel Booking Demand** dataset, available on
[Kaggle](https://www.kaggle.com/datasets/jessemostipak/hotel-booking-demand).
The [original publication](https://doi.org/10.1016/j.dib.2018.11.126) documents
the dataset and field definitions.

- **Unit of analysis:** one booking record.
- **Coverage:** two hotels in Portugal, with data from 2015-2017.
- **Target:** `is_canceled`, indicating whether a booking was canceled.
- **Inputs:** booking characteristics such as lead time, channel, deposit
  arrangement, repeat-guest status, and special requests.

The source CSV is downloaded separately and is not included in the repository.
Cleaning policies, exclusions, date construction, and duplicate handling are
documented in [DATA.md](DATA.md).

## Approach

| Phase | Method and purpose |
|---|---|
| Data quality | Preserve raw records, validate types and dates, audit exclusions and warnings, and expose an eligible-bookings view. |
| SQL analysis | Calculate cancellation rates overall and by hotel type, lead time, market segment, distribution channel, deposit type, customer type, and season. |
| Segmentation | Apply ordered, transparent behavior rules and report segment sizes, shares, and cancellation rates. No clustering is used. |
| Risk modeling | Compare logistic regression with one shallow decision tree and a constant training-rate baseline using chronological partitions. |
| Dashboard preparation | Export aggregate trend, segment, and risk tables with source provenance and population definitions. |
| Interpretation | Document verified findings, limitations, and reproducibility; maintain a separate recommendation template. |

### Data-quality principles

Raw records remain unchanged. Confirmed zero-guest bookings are excluded from
the analytical population, while missing children counts remain unknown rather
than becoming zero. Identical records are retained because identical attributes
do not establish duplicate bookings without a reliable identifier.

Each record retains its exclusion reasons and review warnings. Raw, retained,
and excluded populations must reconcile before downstream analysis.

### Model evaluation

Models train on earlier arrivals, use an intermediate validation period to
choose alert thresholds, and are evaluated on a later final-test period.
Preprocessing is fitted on training data only.

`reservation_status` and `reservation_status_date` are explicitly removed from
model inputs because they reveal outcome information. An explicit feature
allowlist limits the remaining inputs.

Final-test reporting includes **precision, recall, ROC-AUC, Brier score,
confusion counts, and calibration-bin counts and rates**. Logistic regression
is the prespecified primary model, rather than a winner selected from final-test
scores.

The split uses scheduled arrival dates. It is an exploratory later-arrival
holdout, **not a verified booking-time deployment backtest**. Final-extract
feature timing and historical label availability remain important limitations.

## Outputs

| Output | Contents |
|---|---|
| PostgreSQL quality layers | Raw records, typed records with audit flags, a clean view, and snapshot provenance. |
| SQL analysis summaries | Booking counts, cancellation counts, and rates for each analysis question. |
| Segment summary | Mutually exclusive behavior segments with population shares and cancellation rates. |
| Model evaluation bundle | Test metrics, calibration tables, primary-model predictions, feature coefficients/importances, and run metadata. |
| `cancellation_trends.csv` | All eligible historical bookings summarized by scheduled arrival month and hotel. |
| `segment_comparison.csv` | All eligible historical bookings summarized by behavior segment. |
| `risk_distribution.csv` | Final-test later-arrival bookings summarized by predicted-risk band. |

The dashboard CSVs have different grains and populations; they should not be
joined in a way that duplicates records. Power BI or Tableau can consume these
files, but a completed dashboard is not included at this stage.

Generated files remain local and are excluded from version control by default.
The dashboard exporter rejects predictions from a mismatched source snapshot.

## Results

Real-data results are pending. The entries below are placeholders, not estimates.

| Measure | Result |
|---|---|
| Eligible booking records | [RESULT: retained booking count] |
| Overall cancellation rate | [RESULT: overall cancellation rate] |
| Largest behavior segment | [RESULT: largest segment and size] |
| Logistic regression test precision | [RESULT: logistic test precision] |
| Logistic regression test recall | [RESULT: logistic test recall] |
| Logistic regression test ROC-AUC | [RESULT: logistic test ROC-AUC] |
| Decision tree test ROC-AUC | [RESULT: tree test ROC-AUC] |
| Test calibration interpretation | [RESULT: test calibration interpretation] |

The [recommendation template](recommendation.md) contains headings only until
verified findings are available for interpretation. Fictional examples in
documentation and tests are not dataset findings.

## Technology

| Component | Role |
|---|---|
| PostgreSQL | Data storage, cleaning, analytical queries, and summary aggregation. |
| Python and psycopg | CSV ingestion, database access, and phase orchestration. |
| pandas, NumPy, and scikit-learn | Model inputs, preprocessing, classification, and evaluation. |
| pytest | Input-validation, data-quality, model, and PostgreSQL integration checks. |
| DBeaver | Optional interface for inspecting PostgreSQL tables and executing SQL files. |
| Power BI or Tableau | External dashboard tools for the exported summaries. |

DBeaver is not required by the Python workflow; any suitable PostgreSQL client
can be used. Direct Python dependencies are pinned in `requirements.txt`.

## Repository structure

```text
data\raw\                 Locally downloaded source CSV
data\processed\           Generated SQL summaries and model bundles
data\exports\             Generated dashboard CSV bundles
sql\phase1\               Schema, cleaning, and quality reconciliation
sql\phase2\               One commented query per analysis question
sql\phase3\               Behavior segments and segment summary
sql\phase4\               Model inputs and date-coverage inspection
sql\phase5\               Dashboard aggregation queries
src\                      Separately executable Python phase modules
tests\                    Fictional unit and database integration tests
DATA.md                   Data definitions and cleaning decisions
recommendation.md         Headings-only recommendation template
```

## Reproducibility

### Requirements and setup

Python 3.12+ and a running PostgreSQL server are required. The scaffold has been
exercised with Python 3.14 and PostgreSQL 17 using fictional test data.
The dependency file pins direct packages, not a complete transitive environment.

Create a dedicated database such as `hotel_bookings` using an account authorized
to create a schema. Place the original CSV at
`data\raw\hotel_bookings.csv`, retaining its original headers.

Example setup in Windows PowerShell, from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Configure `.env` with the database host, port, name, username, password, and SSL
mode. Existing process environment variables override `.env`. Credentials and
raw data must not be committed. Use verified TLS for remote database connections.

### Execution

Each phase runs independently and should be reviewed before proceeding:

```powershell
.\.venv\Scripts\python.exe -m src.load_data
.\.venv\Scripts\python.exe -m src.analyze --phase 2
.\.venv\Scripts\python.exe -m src.analyze --phase 3
```

Inspect date coverage before choosing temporal boundaries. The following
modeling dates are illustrative, not validated recommendations:

```powershell
.\.venv\Scripts\python.exe -m src.model `
  --validation-start 2017-04-01 `
  --test-start 2017-07-01 `
  --acknowledge-snapshot-limitations

.\.venv\Scripts\python.exe -m src.export_dashboard
```

An existing imported snapshot requires explicit `--replace`. Later-phase output
folders are not overwritten; a new `--output` path is required for a rerun.
Repeated use of the same final-test period does not create independent evidence.
Output definitions are summarized above, with worked examples in the
[learning guide](hotel-booking-learning-guide.html).

### Checks

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not integration"
```

PostgreSQL integration checks are opt-in through `HOTEL_TEST_DATABASE_URL`.
They require a separate disposable database with a name beginning
`hotel_booking_test_` and no existing `hotel_booking` schema. They use fictional
records in rollback-only transactions; without the variable, they are skipped.
After creating that disposable database, configure the test connection locally:

```powershell
# Replace placeholders locally; do not save credentials in the repository.
$env:HOTEL_TEST_DATABASE_URL = "host=localhost port=5432 dbname=hotel_booking_test_local user=<database-user> password='<database-password>'"
.\.venv\Scripts\python.exe -m pytest
Remove-Item Env:\HOTEL_TEST_DATABASE_URL
```

## Limitations

- **Two hotels in one country:** findings may not represent other properties,
  platforms, or travel markets.
- **Data from 2015-2017:** historical behavior and booking policies may not
  reflect current conditions.
- **No external-market validation:** the model is not validated on other markets.
- **Timing uncertainty:** final-extract values may include post-booking updates,
  and training outcomes may not have been known at a simulated deployment cutoff.
- **Partial-year coverage and small groups:** seasonal comparisons and segment
  rates require careful interpretation.
- **No causal or operational-impact claim:** the project does not establish that
  an intervention reduces cancellations or improves revenue.

## Further documentation

- [Data and cleaning decisions](DATA.md)
- [Practical HTML learning guide](hotel-booking-learning-guide.html)
- [PDF learning guide](hotel-booking-learning-guide.pdf)
- [Recommendation template](recommendation.md)
