from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.release import current_matchlab_readiness


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release" / "store_readiness.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Return a non-zero exit code unless all store-readiness gates are complete.",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    readiness = current_matchlab_readiness()

    print(f"product={manifest['product']}")
    print(f"submission_ready={readiness.ready}")
    print(f"completion_percent={readiness.completion_percent}")

    if readiness.blockers:
        print("blockers:")
        for key, detail in zip(readiness.blockers, readiness.blocker_details):
            print(f"- {key}: {detail}")

    if bool(manifest.get("submission_ready")) != readiness.ready:
        print("manifest_mismatch=true")
        return 2

    if args.require_ready and not readiness.ready:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
