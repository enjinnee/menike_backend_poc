from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
import uuid


class Tenant(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    api_key: str
    config: Optional[str] = None  # JSON string
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    role: str = Field(default="tenant_admin", index=True)  # super_admin, tenant_admin, user
    is_active: bool = True
    full_name: Optional[str] = None


class Scene(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    name: str
    description: Optional[str] = None
    status: str = "pending"  # pending, processing, completed, failed
    media_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# NEW: Image Library - pre-stored location images (tenant-wise)
# ---------------------------------------------------------------------------
class ImageLibrary(SQLModel, table=True):
    __tablename__ = "image_library"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    name: str                               # e.g. "Galle Fort Sunset"
    tags: str                               # comma-separated: "galle,fort,sunset,heritage"
    location: Optional[str] = None          # e.g. "Galle, Sri Lanka"
    image_url: str                          # S3 URL
    description: Optional[str] = None      # e.g. "A stunning sunset view at the historic Galle Fort"
    type: Optional[str] = None             # e.g. "heritage", "beach", "nature", "adventure"
    reviews: Optional[str] = None          # e.g. "4.8/5 - Highly recommended for photographers"
    approximate: Optional[str] = None      # e.g. "Entry fee: $3, Best time: 5-7pm"
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# NEW: Cinematic Clips - manually uploaded video clips (tenant-wise)
# ---------------------------------------------------------------------------
class CinematicClip(SQLModel, table=True):
    __tablename__ = "cinematic_clip"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    name: str                               # e.g. "Galle Fort Drone Shot"
    tags: str                               # comma-separated: "galle,fort,drone,sunset"
    video_url: str                          # S3 URL of the pre-made clip
    duration: Optional[float] = None        # seconds
    description: Optional[str] = None
    location: Optional[str] = None          # e.g. "Galle, Sri Lanka"
    type: Optional[str] = None             # e.g. "drone", "timelapse", "underwater", "ground"
    reviews: Optional[str] = None          # e.g. "4.9/5 - Perfect for travel reels"
    approximate: Optional[str] = None      # e.g. "Duration: 30s, Resolution: 4K"
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# NEW: Itinerary - generated travel plans
# ---------------------------------------------------------------------------
class Itinerary(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    prompt: str                             # original user prompt / conversation summary
    destination: str
    days: int
    status: str = "generated"               # generated, video_compiled
    rich_itinerary_json: Optional[str] = Field(default=None)  # Full AI-generated JSON
    user_email: Optional[str] = Field(default=None)           # Traveler's email
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# NEW: Itinerary Activities - each day/activity with linked media
# ---------------------------------------------------------------------------
class ItineraryActivity(SQLModel, table=True):
    __tablename__ = "itinerary_activity"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    itinerary_id: str = Field(foreign_key="itinerary.id", index=True)
    day: int
    activity_name: str                      # e.g. "Visit Galle Fort"
    location: Optional[str] = None          # e.g. "Galle"
    keywords: str                           # comma-separated for matching: "galle,fort,heritage"
    image_id: Optional[str] = Field(default=None, foreign_key="image_library.id", index=True)
    image_url: Optional[str] = None         # denormalized for quick access
    cinematic_clip_id: Optional[str] = Field(default=None, foreign_key="cinematic_clip.id", index=True)
    cinematic_clip_url: Optional[str] = None  # denormalized for quick access
    order_index: int = 0                    # for ordering clips in final video


# ---------------------------------------------------------------------------
# NEW: Final Video - compiled cinematic output
# ---------------------------------------------------------------------------
class FinalVideo(SQLModel, table=True):
    __tablename__ = "final_video"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    itinerary_id: str = Field(foreign_key="itinerary.id", index=True, unique=True)
    video_url: str                          # S3 URL of final compiled video
    duration: Optional[float] = None        # total seconds
    status: str = "compiled"                # compiled, failed
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# ChatSession — persisted chat sessions (one per conversation)
# ---------------------------------------------------------------------------
class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_session"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    title: str = Field(default="New Chat")          # set to destination once known
    is_shared: bool = Field(default=False, index=True)
    is_deleted: bool = Field(default=False)          # soft-delete
    requirements_json: Optional[str] = None          # JSON snapshot of user_requirements
    itinerary_id: Optional[str] = Field(default=None, foreign_key="itinerary.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# ChatMessage — individual messages within a session
# ---------------------------------------------------------------------------
class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_message"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="chat_session.id", index=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)  # denorm for isolation
    role: str                                        # "user" or "assistant"
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
