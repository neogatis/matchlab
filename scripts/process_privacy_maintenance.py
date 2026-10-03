from __future__ import annotations

import os

from sqlalchemy.orm import sessionmaker

from app.db.session import make_engine
from app.privacy.service import process_due_deletions, process_retention_cleanup


def main() -> None:
    if not os.environ.get("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL is required")

    engine = make_engine()
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session.begin() as db:
        deletions = process_due_deletions(
            db,
            limit=int(os.environ.get("PRIVACY_DELETE_BATCH_SIZE", "100")),
        )
        retention = process_retention_cleanup(db)

    print(
        "privacy maintenance:",
        f"deletion_processed={deletions['processed']}",
        f"deletion_purged={deletions['purged']}",
        f"retention={retention}",
        flush=True,
    )


if __name__ == "__main__":
    main()
