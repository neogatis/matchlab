from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
SKIP_PARTS = {"legacy", "__pycache__"}
PATTERNS = {
    "TODO": re.compile(r"\bTODO\b", re.IGNORECASE),
    "FIXME": re.compile(r"\bFIXME\b", re.IGNORECASE),
    "XXX": re.compile(r"\bXXX\b"),
    "NotImplementedError": re.compile(r"\bNotImplementedError\b"),
}


def main() -> int:
    problems: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                problems.append(f"{path.relative_to(ROOT)}:{line}: {label}")

    if problems:
        print("Production placeholder scan failed:")
        for item in problems:
            print(item)
        return 1

    print("Production placeholder scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
