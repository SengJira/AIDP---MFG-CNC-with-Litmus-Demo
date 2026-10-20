#!/usr/bin/env python3
"""Restore the v1 demo state from the committed v1 data pack and the v1 loader scripts."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
V1_REF = "master"


def redact(cmd):
    out = []
    skip = False
    for c in cmd:
        if skip:
            out.append("<redacted>")
            skip = False
            continue
        if c == "-H" and len(cmd) > cmd.index(c) + 1 and "Authorization" in cmd[cmd.index(c) + 1]:
            out.append(c)
            out.append("<redacted>")
            skip = True
            continue
        out.append(c)
    return out


def run(cmd, cwd=REPO, dry=False):
    display = redact(cmd)
    if dry:
        print(f"DRY-RUN: {' '.join(display)}")
        return 0
    print(f"Running: {' '.join(display)}")
    return subprocess.run(cmd, cwd=cwd).returncode


def checkout_and_run(path, dry=False):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as t:
        subprocess.run(["git", "show", f"{V1_REF}:{path}"], cwd=REPO, stdout=t, check=True)
        tmp = t.name
    try:
        return run([sys.executable, tmp], dry=dry)
    finally:
        if not dry:
            os.unlink(tmp)


def reset_logbook(dry=False):
    # load_multisource.py from v1 already re-indexes cnc-demo-shift-logbook.
    # For a clean v1 state, also remove the v2-only cnc-demo-supplier-docs index.
    elastic = os.environ.get("ELASTIC_ENDPOINT")
    key = os.environ.get("ELASTIC_API_KEY")
    if not elastic or not key:
        print("ELASTIC_ENDPOINT or ELASTIC_API_KEY not set; skipping supplier-docs cleanup.")
        return 0
    cmd = [
        "curl", "-s", "-k", "-H", f"Authorization: ApiKey {key}",
        "-X", "DELETE", f"{elastic}/cnc-demo-supplier-docs"
    ]
    return run(cmd, dry=dry)


def main():
    parser = argparse.ArgumentParser(description="Rollback the Spindle to Customer demo to v1.")
    parser.add_argument("--dry-run", action="store_true", help="Print the commands instead of running them.")
    args = parser.parse_args()

    print("Rolling back source tables and analytics to v1...")
    if checkout_and_run("scripts/load_multisource.py", dry=args.dry_run) != 0:
        print("load_multisource.py v1 failed", file=sys.stderr)
        return 1
    if checkout_and_run("scripts/create_analytics_views.py", dry=args.dry_run) != 0:
        print("create_analytics_views.py v1 failed", file=sys.stderr)
        return 1
    if reset_logbook(dry=args.dry_run) != 0:
        print("warning: supplier-docs cleanup returned an error, continuing", file=sys.stderr)
    print("v1 rollback complete." if not args.dry_run else "v1 rollback dry-run complete.")


if __name__ == "__main__":
    main()
