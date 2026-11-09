"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException

from civiclens.db.connection import Db2Session, Db2UnavailableError, connect


def get_db() -> Iterator[Db2Session]:
    try:
        db = connect()
    except (Db2UnavailableError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from None
    try:
        yield db
    finally:
        db.close()
