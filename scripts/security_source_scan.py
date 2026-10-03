from __future__ import annotations

import re
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"app"

SECRET_ASSIGNMENT=re.compile(
    r"""(?ix)
    \b(password|secret|api[_-]?key|access[_-]?token|private[_-]?key)
    \s*=\s*
    [\"'][^\"']{8,}[\"']
    """
)
URL_SECRET=re.compile(r"""(?i)[?&](key|token|secret|password)=""")
INSECURE_COOKIE=re.compile(r"""(?i)Set-Cookie.*(?:ml_session|session).*$""")

ALLOW_LITERAL={
    "Password must contain at least 10 characters",
    "Password is too long",
}


def scan_file(path: Path) -> list[str]:
    text=path.read_text(encoding="utf-8")
    issues=[]
    for line_no,line in enumerate(text.splitlines(),start=1):
        if any(part in {"legacy","__pycache__"} for part in path.parts):
            continue
        match=SECRET_ASSIGNMENT.search(line)
        if match and not any(value in line for value in ALLOW_LITERAL):
            issues.append(f"{path.relative_to(ROOT)}:{line_no}: possible hardcoded secret")
        if URL_SECRET.search(line):
            issues.append(f"{path.relative_to(ROOT)}:{line_no}: secret-like value in URL/query")
        if INSECURE_COOKIE.search(line):
            lowered=line.lower()
            if "secure" not in lowered or "httponly" not in lowered:
                issues.append(f"{path.relative_to(ROOT)}:{line_no}: session cookie may be insecure")
    return issues


def main() -> int:
    issues=[]
    for path in sorted(APP.rglob("*.py")):
        issues.extend(scan_file(path))
    if issues:
        print("Security source scan failed:")
        for issue in issues:
            print(issue)
        return 1
    print("Security source scan passed.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
