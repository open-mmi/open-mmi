# Dashboard performance baselines

Performance changes should be measured before runtime code is modified. The
baseline tools in this repository do not alter dashboard behaviour and use only
the Python standard library.

## What is measured

`tools/dashboard_benchmark.py` schedules HTTP requests at a fixed cadence and
records:

- request latency: median, p95, p99, and maximum;
- scheduler lag;
- gaps between request starts and completions;
- failed requests;
- maximum simultaneous requests;
- out-of-order completions.

The tool discards response bodies after validating that they contain JSON. Its
report stores the endpoint path, test label, timing data, and Git revision. It
does not store dashboard status payloads, telltale values, Jellyfin credentials,
Radio favourites, or radio search terms.

HTTP timing does not fully measure browser rendering. Use the same device,
browser, dashboard page, and scenario when comparing runs, and record a short
manual observation alongside each report.

## Establish the known-good tablet baseline

Start the dashboard normally, then run from another terminal:

```bash
mkdir -p benchmarks

python3 tools/dashboard_benchmark.py \
  --url http://127.0.0.1:8765 \
  --endpoint /api/status \
  --samples 300 \
  --interval-ms 200 \
  --label tablet-idle-known-good \
  --output benchmarks/tablet-idle-known-good.json
```

Repeat under representative conditions:

```text
tablet-idle
tablet-media-page
tablet-jellyfin-browsing
tablet-jellyfin-playing
tablet-radio-browsing
tablet-radio-playing
```

Use a separate JSON file for each scenario. Run each scenario at least twice;
keep the better run only when an interruption is clearly external, otherwise
retain both.

## Compare a candidate change

```bash
python3 tools/dashboard_benchmark.py \
  --url http://127.0.0.1:8765 \
  --endpoint /api/status \
  --samples 300 \
  --interval-ms 200 \
  --label tablet-radio-playing-candidate \
  --baseline benchmarks/tablet-radio-playing-known-good.json \
  --output benchmarks/tablet-radio-playing-candidate.json
```

The default relative budgets are:

- request-latency p95: no more than 10% slower;
- completion-gap p95: no more than 20% slower;
- scheduler-lag p95: no more than 20% slower;
- no increase in failed requests.

These are comparison guards, not universal performance promises. Adjust them
only when a field-tested baseline demonstrates that a different budget is
appropriate.

## Benchmark Radio endpoints separately

Catalogue performance depends on external networks and station providers. Keep
those reports separate from telltale/status reports:

```bash
python3 tools/dashboard_benchmark.py \
  --url http://127.0.0.1:8765 \
  --endpoint '/api/radio/search?filter=popular&limit=30' \
  --samples 20 \
  --interval-ms 1000 \
  --label radio-popular \
  --output benchmarks/radio-popular.json
```

Do not include private search terms in committed benchmark commands or reports.

## Run deterministic contracts

Normal tests check the benchmark calculations and lock the currently approved
telltale polling reference to `setInterval(fetchStatus, 200)`:

```bash
python3 -m unittest discover -s tests -p 'test_dashboard_performance_contracts.py'
```

This test intentionally fails if the status loop is converted to a
completion-delayed `setTimeout(fetchStatus, ...)` loop before a new baseline is
approved.

## Optional live regression test

The live test is skipped by default:

```bash
OPEN_MMI_PERF_BASE_URL=http://127.0.0.1:8765 \
OPEN_MMI_PERF_BASELINE=benchmarks/tablet-idle-known-good.json \
python3 -m unittest discover -s tests -p 'test_dashboard_performance_contracts.py'
```

Useful overrides:

```text
OPEN_MMI_PERF_ENDPOINT
OPEN_MMI_PERF_SAMPLES
OPEN_MMI_PERF_INTERVAL_MS
OPEN_MMI_PERF_TIMEOUT
OPEN_MMI_PERF_WORKERS
OPEN_MMI_PERF_MAX_P95_REGRESSION
OPEN_MMI_PERF_MAX_GAP_REGRESSION
```

## Field note template

Record this beside each report:

```text
Commit:
Device:
Browser:
Scenario:
Network:
Expected behaviour:
Observed telltale delay:
Observed source-switch delay:
Other load:
Relevant log lines:
```

Do not optimise from one isolated number. A candidate should improve its target
scenario without materially worsening telltale freshness in the other
representative scenarios.

<!-- open-mmi-browser-performance-diagnostics-start -->
## In-dashboard automated browser suite

Settings → Diagnostics includes an **Automated browser performance** panel. It
uses the dashboard's existing `/api/status` poll rather than starting another
status loop.

The standard suite automatically exercises:

1. Home/idle rendering;
2. Jellyfin browsing, when Jellyfin is enabled;
3. Internet Radio browsing, when Radio is already enabled and its privacy
   notice has been acknowledged.

Each scenario records source activation separately:

1. one **cold activation** measurement;
2. a ten-poll warm-up after the source is ready;
3. **five warm measured runs of 50 status polls**.

At the approved 200 ms cadence, a complete three-scenario suite takes roughly
three minutes. The runner temporarily switches pages and media sources, then
restores them. It does not start audio. Existing playback may be stopped by
source switching and is not resumed automatically.

The benchmark must remain in the foreground for its entire duration. A `visibilitychange` to hidden or a `pagehide` event immediately invalidates the active suite, records the event timestamp and active scenario/run, and reports the result as inconclusive. Visibility-invalidated reports cannot be saved as baselines. Keep the dashboard tab visible and avoid minimising or navigating away while measurements are running.

### Comparison method

Cold activation and steady-state browser cadence are intentionally separate.
A failed or timed-out activation is reported as an availability failure; it
does not make the rendering benchmark merely "unstable."

For steady-state comparison, each candidate run is checked against the saved
baseline budget. At least **four of five** runs must pass. One outlier is
therefore permitted without making the whole comparison inconclusive.

The acceptance budget is anchored to the baseline's **fourth-best run** (the slowest run that must pass), then the metric tolerance is applied. This makes self-comparison an invariant: every valid baseline passes when compared with itself.

For low-latency metrics, the budget uses the larger of a relative and an absolute tolerance. Status request p95 and response-to-paint p95 allow **10% or 5 ms**, whichever is larger. Paint-gap p95 continues to allow **20%**. This prevents harmless millisecond-scale jitter from being reported as a regression while retaining the four-of-five requirement.

Each measured run accepts at most its configured sample target, so a status poll that begins during shutdown cannot create a 51st sample. Comparator budgets retain their raw values in the report, but run-level pass/fail decisions use **1 ms resolution**. This keeps interpolated p95 values such as 16.1 ms from failing a 16 ms decision boundary while 16.55 ms rounds to 17 ms and remains an outlier.

A comparison can have three outcomes:

- **within baseline** — at least four of five warm runs meet every budget;
- **regression** — fewer than four warm runs meet a budget, or a severe
  correctness failure occurs;
- **inconclusive** — fewer than four runs completed validly, so the result does
  not contain enough evidence.

The suite no longer rejects a report merely because one measured run has a
large spread. Failed requests, incomplete captures, overlapping status
requests, out-of-order completions, and extreme long tasks remain visible.

A baseline must use the same report schema, run count, sample count, warm-up
profile, and four-of-five rule as the candidate. Older baselines remain visible
but must be replaced before comparison.

The report includes:

- cold source activation time and readiness;
- status request latency;
- JSON parsing time;
- render CPU time;
- response-to-next-paint latency;
- request and paint gaps;
- simultaneous and out-of-order status requests;
- browser long tasks when the Long Tasks API is available;
- all five warm runs and the median run-level summaries.

The report contains timing data and scenario names only. It does not retain
`/api/status` payloads, telltale values, Jellyfin credentials, Radio favourites,
or search terms. Reports and the optional comparison baseline remain in browser
local storage until downloaded or cleared.

### Establish a browser baseline

Open Settings → Diagnostics and select **Run robust suite**. Save the result as
a baseline only when every enabled source became ready and at least four of five
warm runs completed validly. Later runs compare against that device- and
environment-specific baseline. Use **Download JSON** to keep local reports;
benchmark directories should remain ignored by Git.

Radio scenarios make the same external Radio Browser requests that ordinary
Radio browsing makes. They run only when Internet Radio is already enabled and
privacy-acknowledged.
<!-- open-mmi-browser-performance-diagnostics-end -->
