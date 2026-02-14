from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class Tenant(BaseModel):
    id: str = Field(..., description="Unique identifier for the tenant")
    name: str = Field(..., description="Name of the tenant organization")
    apiKey: str = Field(..., description="API key for authentication")
    email: Optional[str] = None
    contactPerson: Optional[str] = None
    
    # Configuration metadata (JSON)
    config: Dict[str, Any] = Field(default_factory=dict)
    
    # Audit fields
    isActive: bool = True
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True
