#!/usr/bin/env python3
"""Post the report summary to the user's webhook.

The webhook URL is a credential: it lives in steer's secrets store
(via the bundled runtime next to this script), never in this skill
directory. Missing secret → a "needs_input" envelope whose message
tells the agent exactly what to ask the human to run.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SKILL = "repo-health"
KEY = "REPO_HEALTH_WEBHOOK"


def _envelope(status, summary, data=None, errors=None):
    try:
        from steer.output import print_envelope
        return print_envelope(status, summary, data=data, errors=errors)
    except ImportError:
        result = {"status": status, "summary": summary}
        if data is not None:
            result["data"] = data
        if errors:
            result["errors"] = errors
        print(json.dumps(result, indent=2))
        return 0 if status != "error" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the payload size instead of posting")
    args = parser.parse_args()

    runtime = Path(__file__).resolve().with_name("steer.py")
    report = Path("out/health/REPORT.md")
    if not report.is_file():
        return _envelope("error", "No report to share",
                         errors=[f"Run the flow first: python3 {runtime} "
                                 f"flow status"])

    try:
        from steer import Secrets
    except ImportError:
        return _envelope("error", "The skill's bundled runtime is missing",
                         errors=[f"Expected {runtime}; regenerate it: "
                                 f"steer bundle"])

    url = Secrets(SKILL).get(KEY)
    if url is None:
        return _envelope(
            "needs_input",
            f"{KEY} is not set",
            errors=[f"Ask the user to run: python3 {runtime} "
                    f"secrets set {KEY}"],
        )

    summary = report.read_text(encoding="utf-8").split("## Inventory")[0]
    payload = json.dumps({"text": summary}).encode("utf-8")
    if args.dry_run:
        return _envelope("ok", "Dry run; payload not posted",
                         data={"bytes": len(payload), "destination": KEY})

    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            code = response.status
    except (urllib.error.URLError, OSError) as exc:
        return _envelope("error", "Webhook post failed", errors=[str(exc)])
    return _envelope("ok", f"Posted summary (HTTP {code})")


if __name__ == "__main__":
    sys.exit(main())
