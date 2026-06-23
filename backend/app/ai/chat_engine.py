from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.ai.openai_client import client, complete_text
from app.ai.prompts import CHAT_SYSTEM
from app.ai.rag import semantic_company_search
from app.core.config import settings
from app.models.company import Company
from app.services.search import tavily_search


def _company_block(c: Company) -> str:
    return (
        f"- {c.name} ({c.domain or 'no domain'}) — {c.industry or '?'}, "
        f"{c.employee_count or '?'} employees, {c.country or '?'}"
        f" [id={c.id}]"
    )


def answer(
    db: Session,
    *,
    organization_id: uuid.UUID,
    user_query: str,
    use_web: bool = True,
    history: list[dict] | None = None,
) -> dict:
    """Run a tool-augmented response over CRM + (optional) web search."""
    # 1. Semantic search over org companies.
    hits = semantic_company_search(
        db, organization_id=organization_id, query=user_query, top_k=10
    )
    crm_context = "\n".join(_company_block(c) for c in hits) or "(no CRM matches)"

    # 2. Optional Tavily web search.
    web_blocks = []
    sources = []
    if use_web:
        for r in tavily_search(user_query, max_results=5):
            web_blocks.append(f"- {r['title']}: {r['content'][:300]}\n  {r['url']}")
            sources.append({"title": r["title"], "url": r["url"]})
    web_context = "\n".join(web_blocks) or "(web search disabled or empty)"

    messages: list[dict] = [{"role": "system", "content": CHAT_SYSTEM}]
    for m in (history or []):
        messages.append(m)
    messages.append({
        "role": "user",
        "content": (
            f"User question: {user_query}\n\n"
            f"=== CRM matches ===\n{crm_context}\n\n"
            f"=== Web search ===\n{web_context}\n\n"
            "Answer concisely. Cite CRM matches by [id=<uuid>] when relevant."
        ),
    })

    response = client().chat.completions.create(
        model=settings.openai_model_reasoning,
        temperature=0.2,
        messages=messages,
    )
    answer_text = response.choices[0].message.content or ""

    return {
        "answer": answer_text,
        "companies": [
            {
                "id": c.id,
                "name": c.name,
                "domain": c.domain,
                "industry": c.industry,
                "score": None,
                "reasoning": None,
            }
            for c in hits
        ],
        "sources": sources,
    }
