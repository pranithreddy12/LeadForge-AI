from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.crm import CRMActivity, PipelineStage

ALL_STAGES = [s.value for s in PipelineStage]


def move_stage(db: Session, company: Company, new_stage: str, *,
               user_id: uuid.UUID | None = None) -> Company:
    if new_stage not in ALL_STAGES:
        raise ValueError(f"invalid stage {new_stage}")
    old = company.pipeline_stage
    company.pipeline_stage = new_stage
    db.add(CRMActivity(
        organization_id=company.organization_id,
        company_id=company.id,
        user_id=user_id,
        kind="stage_change",
        body=f"{old} → {new_stage}",
        payload={"from": old, "to": new_stage},
    ))
    db.commit()
    db.refresh(company)
    return company


def pipeline_summary(db: Session, organization_id: uuid.UUID) -> list[dict]:
    rows = db.execute(
        select(Company.pipeline_stage, func.count(Company.id))
        .where(Company.organization_id == organization_id)
        .group_by(Company.pipeline_stage)
    ).all()
    by_stage = dict(rows)
    return [
        {"stage": stage, "count": int(by_stage.get(stage, 0))}
        for stage in ALL_STAGES
    ]
