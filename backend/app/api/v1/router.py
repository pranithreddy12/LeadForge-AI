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
    settings,
    replies,
    today,
    optout,
    data_export,
    sent,
    notifications,
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
api_router.include_router(settings.router)
api_router.include_router(replies.router)
api_router.include_router(today.router)
api_router.include_router(today.log_router)
api_router.include_router(today.pipeline_router)
api_router.include_router(optout.router)
api_router.include_router(data_export.router)
api_router.include_router(sent.router)
api_router.include_router(notifications.router)
