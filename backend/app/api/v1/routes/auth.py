from fastapi import APIRouter, Depends

from app.core.deps import current_org, current_user
from app.models.tenant import Organization, User
from app.schemas.tenant import OrganizationOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@router.get("/org", response_model=OrganizationOut)
def org(org: Organization = Depends(current_org)) -> Organization:
    return org
