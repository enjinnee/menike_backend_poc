import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.auth import get_current_super_admin, get_password_hash
from app.core.database import get_session
from app.core.milvus_client import milvus_client
from app.models.sql_models import Tenant, User

router = APIRouter(prefix="/admin", tags=["Admin"])


class TenantAdminCreateRequest(BaseModel):
    tenant_name: str
    tenant_id: Optional[str] = None
    api_key: Optional[str] = None
    config: Optional[str] = None
    admin_email: str
    admin_password: str
    admin_full_name: Optional[str] = None


class TenantAdminCreateResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    admin_user_id: str
    admin_email: str
    admin_role: str


@router.post("/tenants", response_model=TenantAdminCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant_with_admin(
    payload: TenantAdminCreateRequest,
    _: User = Depends(get_current_super_admin),
    session: Session = Depends(get_session),
):
    # Keep IDs deterministic if FE provides them; otherwise generate.
    tenant_id = payload.tenant_id or f"tenant-{uuid.uuid4().hex[:12]}"
    tenant_api_key = payload.api_key or f"manike-{uuid.uuid4().hex}"

    existing_tenant = session.get(Tenant, tenant_id)
    if existing_tenant:
        raise HTTPException(status_code=409, detail="Tenant ID already exists")

    existing_user = session.exec(
        select(User).where(User.email == payload.admin_email)
    ).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Admin email already exists")

    tenant = Tenant(
        id=tenant_id,
        name=payload.tenant_name,
        api_key=tenant_api_key,
        config=payload.config,
    )
    admin_user = User(
        tenant_id=tenant_id,
        email=payload.admin_email,
        hashed_password=get_password_hash(payload.admin_password),
        role="tenant_admin",
        full_name=payload.admin_full_name,
    )

    session.add(tenant)
    session.add(admin_user)
    session.commit()
    session.refresh(admin_user)

    # Best-effort mirror in Milvus tenant collection.
    try:
        milvus_client.insert_tenant(
            [
                [tenant.id],
                [tenant.name],
                [tenant.api_key],
                [{"config": tenant.config or ""}],
                [[0.0, 0.0]],
            ]
        )
    except Exception:
        pass

    return TenantAdminCreateResponse(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        admin_role=admin_user.role,
    )
