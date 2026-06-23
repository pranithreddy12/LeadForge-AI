from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ai.openai_client import embed
from app.models.company import Company


def embed_text(s: str) -> list[float]:
    out = embed([s])
    return out[0] if out else []


def company_corpus_for_embedding(c: Company) -> str:
    parts = [
        c.name,
        c.industry or "",
        c.description or "",
        " ".join(c.tech_stack or []),
        c.country or "",
        c.region or "",
    ]
    return " | ".join(p for p in parts if p)


def upsert_company_embedding(db: Session, company: Company) -> None:
    vec = embed_text(company_corpus_for_embedding(company))
    if not vec:
        return
    company.embedding = vec
    company.embedding_pending = False
    db.add(company)


def semantic_company_search(
    db: Session,
    *,
    organization_id: uuid.UUID,
    query: str,
    top_k: int = 20,
) -> list[Company]:
    """Cosine-similarity search over company embeddings inside an org."""
    qvec = embed_text(query)
    if not qvec:
        return []
    sql = text(
        """
        SELECT * FROM companies
        WHERE organization_id = :org_id
          AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:qvec AS vector)
        LIMIT :k
        """
    )
    rows = db.execute(sql, {"org_id": organization_id, "qvec": qvec, "k": top_k}).mappings().all()
    if not rows:
        return []
    # Hydrate full ORM objects (the raw SELECT above gives mappings, easier to map back).
    ids = [r["id"] for r in rows]
    order = {rid: i for i, rid in enumerate(ids)}
    out = db.execute(select(Company).where(Company.id.in_(ids))).scalars().all()
    return sorted(out, key=lambda c: order.get(c.id, 0))
