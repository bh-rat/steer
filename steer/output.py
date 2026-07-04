"""
Output utilities: JSON printing and the skill-script result envelope.

Usage:
    from steer.output import print_envelope

    print_envelope("ok", "Report generated",
                   data={"rows": 120}, artifacts=["out/report.pdf"])
"""

import json as json_module
import sys


def output_json(data, file=None):
    """Write data as formatted JSON.

    Args:
        data: Any JSON-serializable data.
        file: Output file (default: stdout, resolved at call time so
            redirection works).
    """
    print(json_module.dumps(data, indent=2), file=file or sys.stdout)


# Recommended envelope statuses. `status` is a free string; these cover
# the cases agents need to branch on.
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_BLOCKED = "blocked"
STATUS_NEEDS_INPUT = "needs_input"
STATUS_PARTIAL = "partial"


def envelope(status, summary, data=None, artifacts=None, errors=None):
    """Build the standard result envelope for skill scripts.

    Every script in every skill invents its own JSON shape for "here's
    what happened". This is one canonical shape:

        {"status": "ok", "summary": "...", "data": {...},
         "artifacts": ["out/report.pdf"], "errors": [...]}

    Args:
        status: One of the STATUS_* constants (or any short string).
        summary: One human-readable sentence about the outcome.
        data: Optional machine-readable payload.
        artifacts: Optional list of file paths this run produced.
        errors: Optional list of error strings.
    """
    result = {"status": status, "summary": summary}
    if data is not None:
        result["data"] = data
    if artifacts:
        result["artifacts"] = [str(a) for a in artifacts]
    if errors:
        result["errors"] = list(errors)
    return result


def print_envelope(status, summary, data=None, artifacts=None, errors=None,
                   file=None):
    """Print a result envelope as JSON to stdout (agents parse this).

    Returns a sensible process exit code: 0 unless status is "error".
    """
    result = envelope(status, summary, data=data, artifacts=artifacts,
                      errors=errors)
    print(json_module.dumps(result, indent=2), file=file or sys.stdout)
    return 0 if status != STATUS_ERROR else 1
