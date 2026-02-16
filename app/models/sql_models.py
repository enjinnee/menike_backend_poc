from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
import uuid

class Tenant(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    api_key: str
    config: Optional[str] = None # JSON string
    created_at: datetime = Field(default_factory=datetime.utcnow)

class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id")
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = True
    full_name: Optional[str] = None

class Scene(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id")
    name: str
    description: Optional[str] = None
    status: str = "pending" # pending, processing, completed, failed
    media_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
