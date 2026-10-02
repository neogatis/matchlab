from pathlib import Path
import hashlib
import py_compile

EXPECTED_SHA256 = "c133d8944158e42dcff32feb9ea9fa43e77cacb6582fe61cd618c8bd2eb1544d"
EXPECTED_SIZE = 82720
SOURCE = Path(__file__).resolve().parents[1] / "app" / "legacy" / "matchlab_v7.py"

raw = SOURCE.read_bytes()
actual = hashlib.sha256(raw).hexdigest()
assert len(raw) == EXPECTED_SIZE, (len(raw), EXPECTED_SIZE)
assert actual == EXPECTED_SHA256, (actual, EXPECTED_SHA256)
py_compile.compile(str(SOURCE), doraise=True)
print(f"OK: exact MatchLab v7 baseline, {len(raw)} bytes, sha256={actual}")
