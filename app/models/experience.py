from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, Field, UUID4
from enum import Enum

class ExperienceType(str, Enum):
    HIKING = "hiking"
    CULTURAL = "cultural"
    ADVENTURE = "adventure"
    FOOD = "food"
    WELLNESS = "wellness"
    # Add more as needed

class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

class Season(str, Enum):
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"
    ALL_YEAR = "all_year"

class Location(BaseModel):
    latitude: float
    longitude: float
    address: str
    city: str
    country: str

class Price(BaseModel):
    currency: str = Field(..., pattern="^[A-Z]{3}$")
    basePrice: float
    minPrice: Optional[float] = None
    maxPrice: Optional[float] = None
    pricePerPerson: bool = True

class Duration(BaseModel):
    minutes: int
    displayText: Optional[str] = None

class Media(BaseModel):
    url: str
    type: str  # 'image' or 'video'
    thumbnailUrl: Optional[str] = None

class CachedVideo(BaseModel):
    id: str
    url: str
    duration: float
    createdAt: datetime

class Review(BaseModel):
    user: str
    rating: float
    comment: str
    date: datetime

class ReviewAggregate(BaseModel):
    averageRating: float
    totalReviews: int

class AvailabilityWindow(BaseModel):
    startDate: datetime
    endDate: datetime
    isAvailable: bool = True

class EmbeddingMetadata(BaseModel):
    model: str
    dimensions: int
    version: str

class Experience(BaseModel):
    # Core identifiers
    id: str # UUID
    tenantId: str
    
    # Basic info
    name: str
    description: str
    shortDescription: str = Field(..., max_length=200)
    
    # Categorization
    type: List[ExperienceType]
    specialNeeds: List[str] = [] # e.g., 'wheelchair-accessible', 'pet-friendly'
    
    # Location
    location: Location
    
    # Pricing & Duration
    price: Price
    duration: Duration
    
    # Difficulty & Seasons
    difficulty: DifficultyLevel
    bestSeasons: List[Season]
    groupSize: dict = Field(default_factory=lambda: {"minimum": 1, "maximum": 10})
    
    # Media
    media: List[Media] = []
    
    # Video content (Manike.AI generated)
    cachedVideos: List[CachedVideo] = []
    
    # Reviews
    reviews: List[Review] = []
    reviewAggregate: ReviewAggregate
    
    # Availability
    availability: List[AvailabilityWindow] = []
    
    # Additional metadata
    additionalInfo: Optional[str] = None
    tags: List[str] = []
    inclusions: List[str] = []
    exclusions: List[str] = []
    cancellationPolicy: Optional[str] = None
    
    # SEO & Engagement
    slug: str
    viewCount: int = 0
    bookingCount: int = 0
    favoriteCount: int = 0
    
    # Vector embedding
    embedding: List[float] # 768-dimensional Gemini embedding
    embeddingMetadata: EmbeddingMetadata
    
    # Audit fields
    isActive: bool = True
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    deletedAt: Optional[datetime] = None
    createdBy: str
    updatedBy: str

    class Config:
        from_attributes = True
