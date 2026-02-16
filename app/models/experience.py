from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class Location(BaseModel):
    latitude: float
    longitude: float
    address: str
    city: str
    country: str

class Price(BaseModel):
    currency: str
    basePrice: float
    minPrice: Optional[float] = None
    maxPrice: Optional[float] = None
    pricePerPerson: bool = True

class Duration(BaseModel):
    minutes: int
    displayText: str

class GroupSizeRange(BaseModel):
    minimum: int
    maximum: int

class GroupSize(BaseModel):
    default: GroupSizeRange

class Media(BaseModel):
    url: str
    type: str

class CachedVideo(BaseModel):
    id: str
    url: str
    duration: float
    createdAt: datetime

class Review(BaseModel):
    user: str
    comment: str
    rating: float
    date: datetime

class ReviewAggregate(BaseModel):
    averageRating: float
    totalReviews: int

class Availability(BaseModel):
    startDate: datetime
    endDate: datetime

class EmbeddingMetadata(BaseModel):
    model: str
    dimensions: int
    version: str

class Experience(BaseModel):
    id: str
    tenantId: str
    name: str
    description: str
    shortDescription: str
    type: List[str]
    specialNeeds: List[str] = []
    location: Location
    price: Price
    duration: Duration
    difficulty: str
    bestSeasons: List[str]
    groupSize: GroupSize
    media: List[Media] = []
    cachedVideos: List[CachedVideo] = []
    reviews: List[Review] = []
    reviewAggregate: ReviewAggregate
    availability: List[Availability] = []
    additionalInfo: Optional[str] = None
    tags: List[str] = []
    inclusions: List[str] = []
    exclusions: List[str] = []
    cancellationPolicy: Optional[str] = None
    slug: str
    viewCount: int = 0
    bookingCount: int = 0
    favoriteCount: int = 0
    embedding: List[float]
    embeddingMetadata: EmbeddingMetadata
    isActive: bool = True
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    deletedAt: Optional[datetime] = None
    createdBy: str
    updatedBy: str

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
