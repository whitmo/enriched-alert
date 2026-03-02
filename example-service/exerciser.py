#!/usr/bin/env python3
"""Exerciser script to drive traffic against the example service.

Modes:
  normal          - Sends requests to /api (healthy traffic)
  latency         - Sends requests to /latency with high delay_ms values
  errors          - Sends requests to /error with 5xx codes
  both            - Alternates between latency and error requests
  cascade         - Sends requests to /cascade-failure with high failure probability
  memory-pressure - Sends requests to /resource-exhaustion to allocate memory
"""

import argparse
import random
import sys
import time
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def send_request(url: str) -> int:
    """Send a GET request, return status code."""
    try:
        req = Request(url)
        with urlopen(req, timeout=10) as resp:
            return resp.status
    except HTTPError as e:
        return e.code
    except URLError as e:
        print(f"  Connection error: {e.reason}", file=sys.stderr)
        return 0


def run(target: str, mode: str, duration: float, rps: float):
    """Run the exerciser loop."""
    interval = 1.0 / rps if rps > 0 else 1.0
    end_time = time.time() + duration
    count = 0
    errors = 0

    print(f"Exerciser: target={target} mode={mode} duration={duration}s rps={rps}")

    while time.time() < end_time:
        start = time.time()

        if mode == "normal":
            url = f"{target}/api"
        elif mode == "latency":
            delay = random.randint(800, 3000)
            url = f"{target}/latency?delay_ms={delay}"
        elif mode == "errors":
            code = random.choice([500, 502, 503])
            url = f"{target}/error?code={code}"
        elif mode == "both":
            if count % 2 == 0:
                delay = random.randint(800, 3000)
                url = f"{target}/latency?delay_ms={delay}"
            else:
                code = random.choice([500, 502, 503])
                url = f"{target}/error?code={code}"
        elif mode == "cascade":
            depth = random.randint(3, 8)
            prob = round(random.uniform(0.5, 0.9), 2)
            url = f"{target}/cascade-failure?depth={depth}&failure_prob={prob}"
        elif mode == "memory-pressure":
            mb = random.choice([5, 10, 20, 50])
            hold = random.randint(10, 60)
            url = f"{target}/resource-exhaustion?mb={mb}&hold_seconds={hold}"
        else:
            print(f"Unknown mode: {mode}", file=sys.stderr)
            sys.exit(1)

        status = send_request(url)
        count += 1
        if status >= 500 or status == 0:
            errors += 1

        elapsed = time.time() - start
        sleep_time = interval - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    print(f"Done: {count} requests, {errors} errors ({100*errors/max(count,1):.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Example service exerciser")
    parser.add_argument(
        "--target",
        default="http://localhost:8080",
        help="Base URL of the example service (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--mode",
        choices=["normal", "latency", "errors", "both", "cascade", "memory-pressure"],
        default="normal",
        help="Traffic mode (default: normal)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=60,
        help="Duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--rps",
        type=float,
        default=10,
        help="Requests per second (default: 10)",
    )
    args = parser.parse_args()
    run(args.target, args.mode, args.duration, args.rps)


if __name__ == "__main__":
    main()
