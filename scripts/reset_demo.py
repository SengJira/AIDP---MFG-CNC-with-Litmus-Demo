#!/usr/bin/env python3
"""Reset the demo to its pre-seeded state."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"


def main():
    for p in PROCESSED.glob("dashboard_*"):
        if p.is_dir():
            for f in p.iterdir():
                f.unlink()
            p.rmdir()
    for f in ["session_labels.json", "session_label_bank.json"]:
        path = PROCESSED / f
        if path.exists():
            path.unlink()
    subprocess.run([sys.executable, "scripts/seed_label_bank.py"], cwd=str(ROOT), check=True)
    print("Demo reset complete.")


if __name__ == "__main__":
    main()
