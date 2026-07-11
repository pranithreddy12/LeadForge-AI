from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class PlaceCache(Base, UUIDPk, Timestamps):
    """Cache of Google Place Details responses, keyed by (place_id, kind), to cut the
    'GetPlaceRequest per day' quota. Discovery calls one detail lookup per search result
    every run, and dedup means we re-encounter the same place_ids constantly — so the
    same review/detail payload gets re-fetched daily. This caches it with a TTL; callers
    reuse a fresh row instead of paying quota again.

    kind: 'reviews' (review bodies) | 'details' (rating/phone/hours refresh).
    Freshness is judged off updated_at (bumped on every upsert)."""

    __tablename__ = "place_cache"
    __table_args__ = (
        UniqueConstraint("place_id", "kind", name="uq_place_cache_pid_kind"),
    )

    place_id: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="reviews")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
