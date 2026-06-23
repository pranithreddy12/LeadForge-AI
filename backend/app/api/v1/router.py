from fastapi import APIRouter

from app.api.v1.routes import (
    auth,
    projects,
    icps,
    companies,
    contacts,
    signals,
    scoring,
    opportunities,
    campaigns,
    crm,
    workflows,
    chat,
    dashboard,
    billing,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(icps.router)
api_router.include_router(companies.router)
api_router.include_router(contacts.router)
api_router.include_router(signals.router)
api_router.include_router(scoring.router)
api_router.include_router(opportunities.router)
api_router.include_router(campaigns.router)
api_router.include_router(crm.router)
api_router.include_router(workflows.router)
api_router.include_router(chat.router)
api_router.include_router(dashboard.router)
api_router.include_router(billing.router)
api_router.include_router(webhooks.router)
