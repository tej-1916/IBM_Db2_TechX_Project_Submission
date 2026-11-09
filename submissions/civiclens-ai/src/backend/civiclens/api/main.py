"""CivicLens AI HTTP API (Phase 00 skeleton)."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from civiclens import __version__
from civiclens.api.deps import get_db
from civiclens.config import get_settings
from civiclens.db import repository as repo
from civiclens.db.connection import Db2Session
from civiclens.domain.models import (
    Category,
    Complaint,
    ComplaintCreate,
    ComplaintCreated,
    ComplaintStatus,
    Hotspot,
)

logger = logging.getLogger("civiclens")
DB = Annotated[Db2Session, Depends(get_db)]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CivicLens AI",
        version=__version__,
        description="Urban infrastructure intelligence backed by IBM Db2.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, str]:
        """Liveness only; does not touch the database."""
        return {"status": "ok", "version": __version__}

    @app.get("/api/health/db", tags=["health"])
    def health_db(db: DB) -> dict[str, object]:
        """Runs a real query against IBM Db2."""
        row = db.fetch_one("SELECT CURRENT TIMESTAMP AS NOW FROM SYSIBM.SYSDUMMY1")
        return {"status": "ok", "server": db.server_info(), "db_time": str(row["now"]) if row else None}

    @app.post("/api/complaints", response_model=ComplaintCreated, status_code=201, tags=["complaints"])
    def create_complaint(body: ComplaintCreate, db: DB) -> ComplaintCreated:
        complaint_id = repo.insert_complaint(db, body)
        complaint = repo.get_complaint(db, complaint_id)
        assert complaint is not None
        candidates = repo.find_duplicate_candidates(
            db,
            category=complaint.category,
            title=complaint.title,
            description=complaint.description,
            latitude=complaint.latitude,
            longitude=complaint.longitude,
            reported_at=complaint.reported_at,
            exclude_id=complaint_id,
        )
        repo.write_audit(
            db,
            actor_type="USER",
            actor_id="api",
            action="COMPLAINT_CREATED",
            input_payload={"complaint_id": complaint_id, "category": complaint.category.value},
            output_summary=f"{len(candidates)} duplicate candidates",
        )
        return ComplaintCreated(complaint=complaint, duplicate_candidates=candidates)

    @app.get("/api/complaints", response_model=list[Complaint], tags=["complaints"])
    def list_complaints(
        db: DB,
        category: Category | None = None,
        status: ComplaintStatus | None = None,
        ward: Annotated[str | None, Query(max_length=64)] = None,
        synthetic: bool | None = None,
        limit: Annotated[int, Query(ge=1, le=repo.MAX_LIST_LIMIT)] = 50,
    ) -> list[Complaint]:
        return repo.list_complaints(
            db, category=category, status=status, ward=ward, synthetic=synthetic, limit=limit
        )

    @app.get("/api/complaints/{complaint_id}", response_model=Complaint, tags=["complaints"])
    def get_complaint(complaint_id: int, db: DB) -> Complaint:
        complaint = repo.get_complaint(db, complaint_id)
        if complaint is None:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return complaint

    @app.get("/api/hotspots", response_model=list[Hotspot], tags=["analysis"])
    def get_hotspots(
        db: DB,
        days: Annotated[int, Query(ge=1, le=365)] = 30,
        category: Category | None = None,
        min_count: Annotated[int, Query(ge=2, le=1000)] = 3,
        limit: Annotated[int, Query(ge=1, le=repo.MAX_HOTSPOT_LIMIT)] = 20,
    ) -> list[Hotspot]:
        return repo.hotspots(
            db,
            since=repo.utcnow() - timedelta(days=days),
            category=category,
            min_count=min_count,
            limit=limit,
        )

    return app


app = create_app()
