import uuid

from app.services.dashboard import _GRADE_ORDER
from app.services.scoring import latest_score_ids_select


def test_grade_order_complete():
    # the distribution must always present every grade bucket in canonical order
    assert _GRADE_ORDER == ["A+", "A", "B", "C", "D", "F"]
    assert len(set(_GRADE_ORDER)) == 6


def test_latest_score_ids_uses_distinct_on_with_tiebreak():
    """The latest-score selector must be deterministic (DISTINCT ON + id tie-break)
    so it returns exactly one score per company even on timestamp ties."""
    from sqlalchemy.dialects import postgresql
    stmt = latest_score_ids_select(uuid.uuid4())
    compiled = str(stmt.compile(dialect=postgresql.dialect())).lower()
    assert "distinct on" in compiled
    # tie-break on id desc so duplicate created_at can't yield two rows
    assert "created_at desc" in compiled and "id desc" in compiled
