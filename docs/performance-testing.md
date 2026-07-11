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
uses the dashboard's existing `/api/status` poll rather than starting a second
status loop. One run automatically exercises:

1. Home/idle rendering;
2. Jellyfin browsing, when Jellyfin is enabled;
3. Internet Radio browsing, when Radio is already enabled and its privacy
   notice has been acknowledged.

The runner temporarily switches pages and active media sources, then restores
them. It does not start audio. Existing playback may be stopped by source
switching and is not resumed automatically.

Each scenario collects 50 normal status polls, approximately ten seconds at the
known-good 200 ms cadence. The report includes:

- status request latency;
- JSON parsing time;
- render CPU time;
- response-to-next-paint latency;
- request and paint gaps;
- simultaneous and out-of-order status requests;
- browser long tasks when the Long Tasks API is available;
- source activation-to-ready time.

The report contains timing data and scenario names only. It does not retain
`/api/status` payloads, telltale values, Jellyfin credentials, Radio favourites,
or search terms. Reports and the optional comparison baseline remain in browser
local storage until downloaded or cleared.

### Establish a browser baseline

Open Settings → Diagnostics and select **Run automated suite**. Once the result
looks representative, select **Save as baseline**. Later runs compare their p95
status, response-to-paint, and paint-gap measurements with that saved baseline.
Use **Download JSON** to archive a result alongside the command-line benchmark
reports.

Radio scenarios make the same external Radio Browser requests that ordinary
Radio browsing makes. They run only when Internet Radio is already enabled and
privacy-acknowledged.
<!-- open-mmi-browser-performance-diagnostics-end -->
