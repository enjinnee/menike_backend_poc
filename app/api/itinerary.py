from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_tenant_id, get_current_user
from app.core.database import get_session
from app.models.sql_models import (
    Itinerary, ItineraryActivity, ImageLibrary, CinematicClip, FinalVideo, User
)
from app.services.generators import ItineraryGenerator
from app.services.matcher import match_image, match_clip
from app.services.media_processor import MediaProcessor
from app.services.storage import storage_service
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/itinerary", tags=["Itinerary Service"])

itinerary_gen = ItineraryGenerator()
media_processor = MediaProcessor()


class ItineraryRequest(BaseModel):
    prompt: str             # e.g. "3-day trip to Galle and Ella"
    destination: str        # e.g. "Sri Lanka"
    days: int               # e.g. 3


class ActivityResponse(BaseModel):
    id: str
    day: int
    activity_name: str
    location: Optional[str]
    keywords: str
    image_id: Optional[str]
    image_url: Optional[str]
    cinematic_clip_id: Optional[str]
    cinematic_clip_url: Optional[str]
    order_index: int


class ItineraryResponse(BaseModel):
    id: str
    tenant_id: str
    prompt: str
    destination: str
    days: int
    status: str
    activities: List[ActivityResponse]
    final_video_url: Optional[str] = None
    created_at: str


# ---------------------------------------------------------------------------
# POST /itinerary/generate - The core flow
# ---------------------------------------------------------------------------
@router.post("/generate", response_model=ItineraryResponse)
async def generate_itinerary(
    req: ItineraryRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session)
):
    """
    Full flow:
    1. Generate activities from the prompt
    2. Match each activity to an image from the tenant's library
    3. Tag each activity to a pre-uploaded cinematic clip
    4. Save everything to PostgreSQL
    """
    # Step 1: Generate activities
    raw_activities = itinerary_gen.generate(req.prompt, req.destination, req.days)

    # Step 2: Save the itinerary
    itinerary = Itinerary(
        tenant_id=tenant_id,
        prompt=req.prompt,
        destination=req.destination,
        days=req.days,
        status="generated",
    )
    session.add(itinerary)
    session.commit()
    session.refresh(itinerary)

    # Step 3: Match each activity using Milvus semantic search
    activities = []
    for idx, raw in enumerate(raw_activities):
        # Construct query text for semantic search
        query_text = f"{raw['activity_name']} {raw['keywords']}"

        # Match image (semantic search)
        matched_image = match_image(tenant_id, query_text)
        # Match cinematic clip (semantic search)
        matched_clip = match_clip(tenant_id, query_text)

        activity = ItineraryActivity(
            tenant_id=tenant_id,
            itinerary_id=itinerary.id,
            day=raw["day"],
            activity_name=raw["activity_name"],
            location=raw.get("location"),
            keywords=raw["keywords"],
            image_id=matched_image.id if matched_image else None,
            image_url=matched_image.url if matched_image else None,
            cinematic_clip_id=matched_clip.id if matched_clip else None,
            cinematic_clip_url=matched_clip.url if matched_clip else None,
            order_index=idx,
        )
        session.add(activity)
        activities.append(activity)

    session.commit()

    # Refresh to get IDs
    for act in activities:
        session.refresh(act)

    return _build_response(itinerary, activities, session)


# ---------------------------------------------------------------------------
# GET /itinerary/ - List itineraries
# ---------------------------------------------------------------------------
@router.get("/", response_model=List[ItineraryResponse])
async def list_itineraries(
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session)
):
    """List all itineraries for the authenticated tenant."""
    itineraries = session.exec(
        select(Itinerary).where(Itinerary.tenant_id == tenant_id)
    ).all()

    results = []
    for itin in itineraries:
        activities = session.exec(
            select(ItineraryActivity)
            .where(ItineraryActivity.itinerary_id == itin.id)
            .where(ItineraryActivity.tenant_id == tenant_id)
            .order_by(ItineraryActivity.order_index)
        ).all()
        results.append(_build_response(itin, activities, session))
    return results


# ---------------------------------------------------------------------------
# GET /itinerary/{id} - Get single itinerary
# ---------------------------------------------------------------------------
@router.get("/{itinerary_id}", response_model=ItineraryResponse)
async def get_itinerary(
    itinerary_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session)
):
    """Get a specific itinerary with all its activities and linked media."""
    itinerary = session.get(Itinerary, itinerary_id)
    if not itinerary or itinerary.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    activities = session.exec(
        select(ItineraryActivity)
        .where(ItineraryActivity.itinerary_id == itinerary.id)
        .where(ItineraryActivity.tenant_id == tenant_id)
        .order_by(ItineraryActivity.order_index)
    ).all()

    return _build_response(itinerary, activities, session)


# ---------------------------------------------------------------------------
# POST /itinerary/{id}/compile-video - Stitch all scenes into final video
# ---------------------------------------------------------------------------
@router.post("/{itinerary_id}/compile-video")
async def compile_video(
    itinerary_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session)
):
    """
    Compile the final cinematic video:
    1. Collect all cinematic clips from the itinerary (in order)
    2. Stitch them together with transitions
    3. Upload to S3
    4. Save the final video record in the database
    """
    itinerary = session.get(Itinerary, itinerary_id)
    if not itinerary or itinerary.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    # Idempotent behavior: if a final video already exists for this itinerary,
    # return it instead of compiling and inserting a duplicate row.
    existing_final = session.exec(
        select(FinalVideo)
        .where(FinalVideo.itinerary_id == itinerary.id)
        .where(FinalVideo.tenant_id == tenant_id)
    ).first()
    if existing_final:
        return {
            "message": "Final cinematic video already compiled",
            "final_video": {
                "id": existing_final.id,
                "video_url": existing_final.video_url,
                "itinerary_id": existing_final.itinerary_id,
                "status": existing_final.status,
                "clips_used": None,
            }
        }

    # Get activities in order
    activities = session.exec(
        select(ItineraryActivity)
        .where(ItineraryActivity.itinerary_id == itinerary_id)
        .where(ItineraryActivity.tenant_id == tenant_id)
        .order_by(ItineraryActivity.order_index)
    ).all()

    # Collect clip URLs (skip activities with no clip)
    clip_urls = []
    for act in activities:
        if act.cinematic_clip_url:
            clip_urls.append(act.cinematic_clip_url)

    if not clip_urls:
        raise HTTPException(
            status_code=400,
            detail="No cinematic clips are tagged to this itinerary. Upload clips and regenerate."
        )

    # Stitch all clips together
    output_path = f"/tmp/final_video_{itinerary.id}.mp4"
    final_local = media_processor.stitch_scenes(clip_urls, output_path)

    # Upload to S3
    s3_key = f"tenants/{tenant_id}/final-video/{itinerary.id}.mp4"
    final_url = storage_service.upload_file(final_local, s3_key)

    # Save to DB
    final_video = FinalVideo(
        tenant_id=tenant_id,
        itinerary_id=itinerary.id,
        video_url=final_url,
        status="compiled",
    )
    session.add(final_video)

    # Update itinerary status
    itinerary.status = "video_compiled"
    session.add(itinerary)
    try:
        session.commit()
        session.refresh(final_video)
    except IntegrityError:
        # A concurrent request may have inserted the final video first.
        session.rollback()
        existing_final = session.exec(
            select(FinalVideo)
            .where(FinalVideo.itinerary_id == itinerary.id)
            .where(FinalVideo.tenant_id == tenant_id)
        ).first()
        if existing_final:
            return {
                "message": "Final cinematic video already compiled",
                "final_video": {
                    "id": existing_final.id,
                    "video_url": existing_final.video_url,
                    "itinerary_id": existing_final.itinerary_id,
                    "status": existing_final.status,
                    "clips_used": len(clip_urls),
                }
            }
        raise

    return {
        "message": "Final cinematic video compiled successfully",
        "final_video": {
            "id": final_video.id,
            "video_url": final_video.video_url,
            "itinerary_id": final_video.itinerary_id,
            "status": final_video.status,
            "clips_used": len(clip_urls),
        }
    }


# ---------------------------------------------------------------------------
# DELETE /itinerary/{id} - Delete itinerary and related records
# ---------------------------------------------------------------------------
@router.delete("/{itinerary_id}")
async def delete_itinerary(
    itinerary_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Delete an itinerary and its related activities/final video."""
    tenant_id = current_user.tenant_id
    is_super_admin = current_user.role == "super_admin"

    itinerary = session.get(Itinerary, itinerary_id)
    if not itinerary:
        raise HTTPException(status_code=404, detail="Itinerary not found")
    if not is_super_admin and itinerary.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    final_video_stmt = select(FinalVideo).where(FinalVideo.itinerary_id == itinerary.id)
    if not is_super_admin:
        final_video_stmt = final_video_stmt.where(FinalVideo.tenant_id == tenant_id)
    final_video = session.exec(final_video_stmt).first()
    if final_video:
        session.delete(final_video)

    activities_stmt = select(ItineraryActivity).where(ItineraryActivity.itinerary_id == itinerary.id)
    if not is_super_admin:
        activities_stmt = activities_stmt.where(ItineraryActivity.tenant_id == tenant_id)
    activities = session.exec(activities_stmt).all()
    for activity in activities:
        session.delete(activity)

    # Ensure child rows are deleted before deleting the parent itinerary.
    session.flush()

    session.delete(itinerary)
    session.commit()

    return {
        "message": "Itinerary deleted successfully",
        "itinerary_id": itinerary_id,
        "deleted_activities": len(activities),
        "deleted_final_video": bool(final_video),
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _build_response(itinerary: Itinerary, activities: list, session: Session) -> ItineraryResponse:
    """Build a full ItineraryResponse from models."""
    # Check for final video
    final_vid = session.exec(
        select(FinalVideo).where(FinalVideo.itinerary_id == itinerary.id)
    ).first()

    return ItineraryResponse(
        id=itinerary.id,
        tenant_id=itinerary.tenant_id,
        prompt=itinerary.prompt,
        destination=itinerary.destination,
        days=itinerary.days,
        status=itinerary.status,
        final_video_url=final_vid.video_url if final_vid else None,
        activities=[
            ActivityResponse(
                id=act.id,
                day=act.day,
                activity_name=act.activity_name,
                location=act.location,
                keywords=act.keywords,
                image_id=act.image_id,
                image_url=act.image_url,
                cinematic_clip_id=act.cinematic_clip_id,
                cinematic_clip_url=act.cinematic_clip_url,
                order_index=act.order_index,
            ) for act in activities
        ],
        created_at=str(itinerary.created_at),
    )
