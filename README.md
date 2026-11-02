# Checkout Redesign Experiment: SQL Data Modelling and A/B Test Analysis

An end-to-end analytics project: raw event exports are cleaned and modelled in SQL
(staging, intermediate and mart layers, dbt-style, with data-quality tests), and the
resulting analysis table is used to read out an A/B test with proper statistics.

> **Data note:** the dataset is **simulated** by `data/generate.py` (200,000 users, no
> real customers). It deliberately includes common raw-data problems: duplicate rows and
> events, missing device values, inconsistent country codes, internal test accounts and
> zero/negative order values.

## What it shows

| Area | Implementation |
|---|---|
| SQL data modelling | 9 SQL models in `sql/` (staging, intermediate, marts), with window functions for de-duplication, conditional aggregation and pre/post-assignment windows |
| Data quality | dbt-style tests in `pipeline.py`: unique, not_null, accepted_values, positive and relationships |
| Orchestration | `pipeline.py` resolves model dependencies (topological sort) and builds a SQLite warehouse |
| Experimentation stats | `analysis/stats.py`: sample-ratio-mismatch check, two-proportion z-test, Welch t-test, bootstrap CI, CUPED variance reduction, Holm correction, power and MDE |
| Reporting | `reports/experiment_report.html`: a self-contained readout with KPI tiles, charts and a segment table |
| Testing and CI | 9 unit tests in `tests/`; a GitHub Actions workflow runs tests, pipeline and analysis |

## Results (from `reports/results.json`)

- **Randomisation healthy:** 99,373 control vs 99,818 treatment users after removing
  internal accounts; SRM p = 0.32.
- **Conversion:** 4.18% → 4.40%, a **+5.2% relative lift** (95% CI +0.04 to +0.40
  percentage points, p = 0.016).
- **Revenue per user:** €3.04 → €3.22, **+5.7%** (Welch p = 0.021; bootstrap 95% CI
  €0.03 to €0.32).
- **CUPED** with pre-period revenue cut variance by only 1.6%. Purchases are sparse, so
  pre-period spend is a weak covariate here, and the readout says so.
- **Segments:** the lift is directionally positive on desktop and mobile, but no device
  segment is significant after Holm correction. Segment results should not be
  over-read.
- **Power:** at about 99k users per arm the minimum detectable relative lift is about
  6%, so the observed 5% effect was close to the limit of what this test could reliably
  detect.

**Recommendation:** ship the redesign, monitor conversion for novelty decay, and if
mobile-specific changes are planned, run a follow-up powered for that segment.

## Run it

```bash
pip install -r requirements.txt
python data/generate.py          # simulate raw exports into data/raw/
python pipeline.py               # build warehouse + run data tests
python analysis/analyze.py       # stats + reports/experiment_report.html
python -m unittest discover tests -v
```

## Project layout

```
data/generate.py        simulated raw exports (users, assignments, orders, checkout events)
sql/staging/            cleaning: types, trimming, de-duplication, filters
sql/intermediate/       experiment population, pre/post order windows
sql/marts/              analysis-ready fact table and summaries
pipeline.py             loader, dependency-ordered model runner, data tests
analysis/stats.py       statistical functions
analysis/analyze.py     experiment readout, results.json and HTML report
tests/test_stats.py     unit tests for the statistics
```
