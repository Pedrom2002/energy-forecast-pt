"""Scheduled drift + coverage check.

Designed to run on a cron from GitHub Actions (see
``.github/workflows/drift-check.yml``). Hits the live API's
``/model/coverage`` endpoint, compares empirical CI coverage against the
nominal target (90%), and exits non-zero when coverage drops below the
alert threshold so the workflow can open an issue / alert on failure.

Env:
    API_URL          Base URL of the API (required).
    API_KEY          X-API-Key header value (optional; only needed if
                     the target API has auth enabled).
    COVERAGE_MIN     Floor below which we consider drift detected. Defaults
                     to 0.80 (matches backend COVERAGE_ALERT_THRESHOLD).

Exit codes:
    0  Coverage healthy OR tracker not yet populated (no observations).
    1  Transport/HTTP error talking to the API.
    2  Coverage below threshold — drift detected.

The script is dependency-free (stdlib only) so the workflow doesn't have
to install the project's heavy requirements just to curl a URL.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _get_json(url: str, api_key: str | None) -> dict:
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("X-API-Key", api_key)
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — controlled URL
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    api_url = os.environ.get("API_URL")
    if not api_url:
        print("ERROR: API_URL env var is required.", file=sys.stderr)
        return 1
    api_key = os.environ.get("API_KEY") or None
    floor = float(os.environ.get("COVERAGE_MIN", "0.80"))

    endpoint = api_url.rstrip("/") + "/model/coverage"
    print(f"Checking coverage at {endpoint} (floor={floor:.2%})")

    try:
        payload = _get_json(endpoint, api_key)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print(f"ERROR: could not reach API: {exc}", file=sys.stderr)
        return 1

    if not payload.get("available"):
        print("Coverage tracker not available / not populated yet — exit 0.")
        print(json.dumps(payload, indent=2))
        return 0

    coverage = payload.get("coverage")
    n_obs = payload.get("n_observations", 0)
    alert = bool(payload.get("alert"))

    print(
        f"Empirical coverage = {coverage!r} (n={n_obs}, alert={alert}, floor={floor:.2%})"
    )

    # Only fail if we have a meaningful sample AND coverage is below the floor.
    # Tiny n leads to noisy empirical coverage; don't spam issues for that.
    if n_obs < 20:
        print("n_observations < 20 — too few samples to act, exit 0.")
        return 0

    if coverage is None:
        print("Coverage is None despite available=true — investigating needed, exit 2.")
        return 2

    if float(coverage) < floor or alert:
        print(
            f"DRIFT DETECTED: coverage {coverage:.3f} below floor {floor:.2f} "
            f"(or alert flag set). Exit 2."
        )
        return 2

    print("OK — coverage healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
