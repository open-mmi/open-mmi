#!/usr/bin/env python3
"""Black-box latency benchmark for the Open MMI web dashboard.

This tool does not modify the dashboard and does not retain response bodies.
It schedules requests at a fixed cadence so a run can reveal latency,
scheduler drift, overlapping requests, failures, and out-of-order completions.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import json
import math
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


REPORT_SCHEMA = 1
DEFAULT_ENDPOINT = "/api/status"
DEFAULT_SAMPLES = 100
DEFAULT_INTERVAL_MS = 200.0
DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_WORKERS = 8
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclasses.dataclass(frozen=True)
class ProbeSample:
    sequence: int
    scheduled_ns: int
    started_ns: int
    finished_ns: int
    ok: bool
    status_code: int | None
    error: str | None

    @property
    def request_ms(self) -> float:
        return (self.finished_ns - self.started_ns) / 1_000_000.0

    @property
    def schedule_lag_ms(self) -> float:
        return max(0.0, (self.started_ns - self.scheduled_ns) / 1_000_000.0)


@dataclasses.dataclass
class ProbeState:
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    in_flight: int = 0
    max_in_flight: int = 0
    completion_order: list[int] = dataclasses.field(default_factory=list)

    def enter(self) -> None:
        with self.lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)

    def leave(self, sequence: int) -> None:
        with self.lock:
            self.in_flight -= 1
            self.completion_order.append(sequence)


def percentile(values: Iterable[float], quantile: float) -> float | None:
    """Return a linearly interpolated percentile for 0 <= quantile <= 1."""
    data = sorted(float(value) for value in values)
    if not data:
        return None
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")
    if len(data) == 1:
        return data[0]
    position = (len(data) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return data[lower]
    fraction = position - lower
    return data[lower] + (data[upper] - data[lower]) * fraction


def describe(values: Iterable[float]) -> dict[str, float | int | None]:
    data = [float(value) for value in values]
    if not data:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "p95": None,
            "p99": None,
            "maximum": None,
        }
    return {
        "count": len(data),
        "mean": round(statistics.fmean(data), 3),
        "median": round(float(statistics.median(data)), 3),
        "p95": round(float(percentile(data, 0.95)), 3),
        "p99": round(float(percentile(data, 0.99)), 3),
        "maximum": round(max(data), 3),
    }


def _read_url(url: str, timeout: float) -> tuple[int, bytes]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "Open-MMI-Dashboard-Benchmark/1",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise RuntimeError("response exceeded benchmark safety limit")
        return int(getattr(response, "status", 200)), body


def _probe_once(
    *,
    sequence: int,
    scheduled_ns: int,
    url: str,
    timeout: float,
    state: ProbeState,
    requester: Callable[[str, float], tuple[int, bytes]],
) -> ProbeSample:
    started_ns = time.perf_counter_ns()
    state.enter()
    ok = False
    status_code: int | None = None
    error: str | None = None
    try:
        status_code, body = requester(url, timeout)
        if not 200 <= status_code < 300:
            raise RuntimeError(f"HTTP {status_code}")
        if body:
            json.loads(body.decode("utf-8"))
        ok = True
    except HTTPError as exc:
        status_code = int(exc.code)
        error = f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
        error = str(exc)
    finally:
        finished_ns = time.perf_counter_ns()
        state.leave(sequence)
    return ProbeSample(
        sequence=sequence,
        scheduled_ns=scheduled_ns,
        started_ns=started_ns,
        finished_ns=finished_ns,
        ok=ok,
        status_code=status_code,
        error=error,
    )


def run_probe(
    *,
    base_url: str,
    endpoint: str = DEFAULT_ENDPOINT,
    samples: int = DEFAULT_SAMPLES,
    interval_ms: float = DEFAULT_INTERVAL_MS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    workers: int = DEFAULT_WORKERS,
    warmup: int = 3,
    requester: Callable[[str, float], tuple[int, bytes]] = _read_url,
) -> dict[str, Any]:
    if samples < 1:
        raise ValueError("samples must be at least 1")
    if interval_ms < 0:
        raise ValueError("interval_ms must not be negative")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if workers < 1:
        raise ValueError("workers must be at least 1")

    base = base_url.rstrip("/") + "/"
    url = urljoin(base, endpoint.lstrip("/"))

    for _ in range(max(0, warmup)):
        try:
            requester(url, timeout)
        except Exception:
            pass

    state = ProbeState()
    started_ns = time.perf_counter_ns()
    futures: list[concurrent.futures.Future[ProbeSample]] = []
    interval_ns = int(interval_ms * 1_000_000.0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for sequence in range(samples):
            scheduled_ns = started_ns + sequence * interval_ns
            remaining_ns = scheduled_ns - time.perf_counter_ns()
            if remaining_ns > 0:
                time.sleep(remaining_ns / 1_000_000_000.0)
            futures.append(
                pool.submit(
                    _probe_once,
                    sequence=sequence,
                    scheduled_ns=scheduled_ns,
                    url=url,
                    timeout=timeout,
                    state=state,
                    requester=requester,
                )
            )
        results = [future.result() for future in futures]

    finished_ns = time.perf_counter_ns()
    results.sort(key=lambda sample: sample.sequence)
    successful = [sample for sample in results if sample.ok]
    failures = [sample for sample in results if not sample.ok]

    start_times = [sample.started_ns for sample in results]
    completion_times = sorted(sample.finished_ns for sample in results)
    start_gaps = [
        (current - previous) / 1_000_000.0
        for previous, current in zip(start_times, start_times[1:])
    ]
    completion_gaps = [
        (current - previous) / 1_000_000.0
        for previous, current in zip(completion_times, completion_times[1:])
    ]

    max_seen = -1
    out_of_order_completions = 0
    for sequence in state.completion_order:
        if sequence < max_seen:
            out_of_order_completions += 1
        max_seen = max(max_seen, sequence)

    elapsed_seconds = (finished_ns - started_ns) / 1_000_000_000.0
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "endpoint": endpoint,
        "configuration": {
            "samples": samples,
            "interval_ms": interval_ms,
            "timeout_seconds": timeout,
            "workers": workers,
            "warmup": max(0, warmup),
        },
        "summary": {
            "successful_requests": len(successful),
            "failed_requests": len(failures),
            "elapsed_seconds": round(elapsed_seconds, 3),
            "effective_request_rate_hz": round(samples / elapsed_seconds, 3)
            if elapsed_seconds > 0
            else None,
            "max_in_flight": state.max_in_flight,
            "out_of_order_completions": out_of_order_completions,
            "request_ms": describe(sample.request_ms for sample in successful),
            "schedule_lag_ms": describe(sample.schedule_lag_ms for sample in results),
            "request_start_gap_ms": describe(start_gaps),
            "completion_gap_ms": describe(completion_gaps),
        },
        "errors": [
            {
                "sequence": sample.sequence,
                "status_code": sample.status_code,
                "error": sample.error,
            }
            for sample in failures[:20]
        ],
    }


def _metric(report: dict[str, Any], group: str, key: str) -> float | None:
    value = report.get("summary", {}).get(group, {}).get(key)
    return float(value) if isinstance(value, (int, float)) else None


def compare_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    max_p95_regression: float = 0.10,
    max_gap_regression: float = 0.20,
) -> list[str]:
    """Return human-readable regression violations."""
    violations: list[str] = []

    candidate_failures = int(candidate.get("summary", {}).get("failed_requests", 0))
    baseline_failures = int(baseline.get("summary", {}).get("failed_requests", 0))
    if candidate_failures > baseline_failures:
        violations.append(
            f"failed requests increased from {baseline_failures} to {candidate_failures}"
        )

    checks = [
        ("request_ms", "p95", max_p95_regression, "request latency p95"),
        ("completion_gap_ms", "p95", max_gap_regression, "completion gap p95"),
        ("schedule_lag_ms", "p95", max_gap_regression, "schedule lag p95"),
    ]
    for group, key, allowed, label in checks:
        old = _metric(baseline, group, key)
        new = _metric(candidate, group, key)
        if old is None or new is None:
            continue
        threshold = max(old * (1.0 + allowed), old + 0.5)
        if new > threshold:
            violations.append(
                f"{label} regressed from {old:.3f} ms to {new:.3f} ms "
                f"(allowed <= {threshold:.3f} ms)"
            )

    return violations


def _git_metadata() -> dict[str, str | None]:
    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip() or None

    return {
        "commit": run("rev-parse", "HEAD"),
        "branch": run("branch", "--show-current"),
        "dirty": "yes" if run("status", "--porcelain") else "no",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure Open MMI dashboard endpoint latency without changing runtime code."
    )
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--interval-ms", type=float, default=DEFAULT_INTERVAL_MS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--label", default="unnamed")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--max-p95-regression", type=float, default=0.10)
    parser.add_argument("--max-gap-regression", type=float, default=0.20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_probe(
            base_url=args.url,
            endpoint=args.endpoint,
            samples=args.samples,
            interval_ms=args.interval_ms,
            timeout=args.timeout,
            workers=args.workers,
            warmup=args.warmup,
        )
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report["label"] = args.label
    report["git"] = _git_metadata()

    violations: list[str] = []
    if args.baseline:
        try:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: could not read baseline: {exc}", file=sys.stderr)
            return 2
        violations = compare_reports(
            baseline,
            report,
            max_p95_regression=args.max_p95_regression,
            max_gap_regression=args.max_gap_regression,
        )
        report["comparison"] = {
            "baseline": str(args.baseline),
            "passed": not violations,
            "violations": violations,
        }

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    if report["summary"]["failed_requests"]:
        return 1
    if violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
