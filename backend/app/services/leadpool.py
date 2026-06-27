"""The scored lead pool = BUYER-classified companies only.

P1 #9: the gate may classify a company as vendor/competitor/investor_vc/etc. Those
must never surface as scored leads or opportunities, regardless of how high they
score on firmographics (a funded in-band vendor scores like a great buyer). This is
the single source of truth for "is this company allowed in the lead pool."
"""
from __future__ import annotations

from sqlalchemy import or_

from app.models.company import Company

# Legacy rows (pre-classification) carry NULL and are treated as buyers.
BUYER_CLASSIFICATIONS = ("buyer",)


def buyer_only():
    """SQLAlchemy predicate: keep only buyer-classified (or legacy-NULL) companies."""
    return or_(
        Company.classification_status.in_(BUYER_CLASSIFICATIONS),
        Company.classification_status.is_(None),
    )


def is_buyer(company: Company) -> bool:
    return company.classification_status in (None, *BUYER_CLASSIFICATIONS)
