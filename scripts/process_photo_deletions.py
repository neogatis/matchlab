from __future__ import annotations

import os

from sqlalchemy.orm import sessionmaker

from app.db.session import make_engine
from app.photos.service import process_deletion_outbox
from app.photos.storage import S3PhotoStorage


def main() -> None:
    if not os.environ.get("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL is required")

    engine = make_engine()
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    storage = S3PhotoStorage.from_env()

    with Session.begin() as db:
        result = process_deletion_outbox(
            db,
            storage=storage,
            limit=int(os.environ.get("PHOTO_DELETE_BATCH_SIZE", "100")),
        )

    print(
        "photo deletion outbox:",
        f"processed={result['processed']}",
        f"done={result['done']}",
        f"failed={result['failed']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
