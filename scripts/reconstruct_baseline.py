from pathlib import Path
import base64
import gzip
import hashlib

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "app" / "legacy" / "encoded"
TARGET = ROOT / "app" / "legacy" / "matchlab_v7.py"
EXPECTED_SHA256 = "c133d8944158e42dcff32feb9ea9fa43e77cacb6582fe61cd618c8bd2eb1544d"
EXPECTED_SIZE = 82720

encoded = "".join(
    (PARTS / f"part{i:02d}.b64").read_text(encoding="utf-8").strip()
    for i in range(1, 11)
)
encoded += "=" * ((4 - len(encoded) % 4) % 4)
raw = gzip.decompress(base64.urlsafe_b64decode(encoded))
actual = hashlib.sha256(raw).hexdigest()
if len(raw) != EXPECTED_SIZE or actual != EXPECTED_SHA256:
    raise SystemExit(
        f"baseline mismatch: size={len(raw)} sha256={actual}"
    )
TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_bytes(raw)
print(f"materialized {TARGET}: {len(raw)} bytes sha256={actual}")
