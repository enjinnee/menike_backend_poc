from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_tenant_id
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/itinerary", tags=["Itinerary Service"])

class ItineraryRequest(BaseModel):
    destination: str
    days: int
    interests: List[str]

@router.post("/generate")
async def generate_itinerary(
    req: ItineraryRequest,
    tenant_id: str = Depends(get_current_tenant_id)
):
    # This integrates the "Already Built" Itinerary Service logic
    # In a real scenario, this would import from the legacy module
    return {
        "tenant_id": tenant_id,
        "itinerary": {
            "destination": req.destination,
            "days": req.days,
            "activities": [
                {"day": 1, "activity": f"Arrival in {req.destination} and city tour"},
                {"day": 2, "activity": f"Exploring {req.interests[0]} highlights"}
            ],
            "media_enriched": True
        },
        "cinematic_video_plan": {
            "total_scenes": 5,
            "estimated_duration": "60s"
        }
    }
