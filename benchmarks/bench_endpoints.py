#!/usr/bin/env python3
"""
Benchmark script for Claude Karma API endpoints.

Measures latency of SQLite-optimized endpoints.

Usage:
    python3 benchmarks/bench_endpoints.py
    python3 benchmarks/bench_endpoints.py --iterations 20
    python3 benchmarks/bench_endpoints.py --base-url http://localhost:8001
"""

import argparse
import statistics
import time

import httpx

ENDPOINTS = [
    ("/health", "Health check"),
    ("/projects", "Project listing"),
    ("/analytics/dashboard", "Dashboard stats"),
    ("/agents/usage", "Agent usage"),
    ("/skills/usage", "Skill usage"),
]


def wait_for_ready(client: httpx.Client, timeout: float = 30.0) -> bool:
    """Wait for SQLite index to be ready via /health endpoint."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = client.get("/health")
            if resp.status_code == 200:
                data = resp.json()
                sqlite = data.get("sqlite", {})
                if sqlite.get("ready", False):
                    return True
        except httpx.ConnectError:
            pass
        time.sleep(0.5)
    return False


def benchmark_endpoint(client: httpx.Client, path: str, iterations: int) -> dict:
    """Benchmark a single endpoint, returning timing stats."""
    timings = []
    errors = 0
    for _ in range(iterations):
        start = time.time()
        try:
            resp = client.get(path)
            elapsed = time.time() - start
            if resp.status_code == 200:
                timings.append(elapsed * 1000)  # Convert to ms
            else:
                errors += 1
        except Exception:
            errors += 1

    if not timings:
        return {"error": f"All {iterations} requests failed"}

    sorted_timings = sorted(timings)
    p95_idx = int(len(sorted_timings) * 0.95)

    return {
        "min_ms": round(sorted_timings[0], 1),
        "median_ms": round(statistics.median(sorted_timings), 1),
        "p95_ms": round(sorted_timings[min(p95_idx, len(sorted_timings) - 1)], 1),
        "max_ms": round(sorted_timings[-1], 1),
        "avg_ms": round(statistics.mean(sorted_timings), 1),
        "errors": errors,
        "samples": len(timings),
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark Claude Karma API endpoints")
    parser.add_argument("--iterations", "-n", type=int, default=10, help="Requests per endpoint")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--timeout", type=float, default=30.0, help="Request timeout in seconds")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url, timeout=args.timeout)

    print(f"Benchmarking {args.base_url} ({args.iterations} iterations per endpoint)")
    print()

    # Wait for SQLite ready
    print("Waiting for SQLite index to be ready...", end=" ", flush=True)
    if not wait_for_ready(client):
        print("TIMEOUT - proceeding anyway")
    else:
        print("OK")
    print()

    # Header
    print(f"{'Endpoint':<35} {'Min':>8} {'Median':>8} {'P95':>8} {'Max':>8} {'Avg':>8} {'Err':>5}")
    print("-" * 90)

    for path, label in ENDPOINTS:
        stats = benchmark_endpoint(client, path, args.iterations)
        if "error" in stats:
            print(f"{label:<35} {stats['error']}")
        else:
            print(
                f"{label:<35} "
                f"{stats['min_ms']:>7.1f}ms "
                f"{stats['median_ms']:>7.1f}ms "
                f"{stats['p95_ms']:>7.1f}ms "
                f"{stats['max_ms']:>7.1f}ms "
                f"{stats['avg_ms']:>7.1f}ms "
                f"{stats['errors']:>4}",
            )

    print()
    client.close()


if __name__ == "__main__":
    main()
