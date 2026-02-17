from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class Tenant(BaseModel):
    id: str = Field(..., description="Unique identifier for the tenant")
    name: str = Field(..., description="Name of the tenant organization")
    api_key: str = Field(..., alias="apiKey", description="API key for authentication")
    email: Optional[str] = None
    contact_person: Optional[str] = Field(default=None, alias="contactPerson")
    
    # Configuration metadata (JSON)
    config: Dict[str, Any] = Field(default_factory=dict)
    
    # Audit fields
    is_active: bool = Field(default=True, alias="isActive")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )
