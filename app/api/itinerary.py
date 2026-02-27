import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_tenant_id, get_current_user
from app.core.database import get_session
from app.models.sql_models import (
    Itinerary, ItineraryActivity, ImageLibrary, CinematicClip, FinalVideo, User
)
from app.services.generators import ItineraryGenerator
from app.services.matcher import match_image, match_clip
from app.services.ai_itinerary_generator import AIItineraryGenerator
from app.services.video_compiler import VideoCompilerFactory
from app.chat.session import chat_session_store
from app.providers.factory import ProviderFactory
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/itinerary", tags=["Itinerary Service"])

# Legacy mock generator (kept for backward compat)
_legacy_gen = ItineraryGenerator()


class ItineraryRequest(BaseModel):
    # --- AI-powered chat-based flow (recommended) ---
    session_id: Optional[str] = None   # Session from POST /api/session/new

    # --- Legacy fallback (if session_id not provided) ---
    prompt: Optional[str] = None        # e.g. "3-day trip to Galle and Ella"
    destination: Optional[str] = None   # e.g. "Sri Lanka"
    days: Optional[int] = None          # e.g. 3


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
    rich_itinerary: Optional[dict] = None  # Full AI-generated itinerary with media URLs
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
    Generate a travel itinerary with Milvus-matched images and cinematic clips.

    AI-powered flow (recommended):
      Provide a `session_id` from POST /api/session/new.
      The conversation is used to generate a rich AI itinerary, then
      Milvus semantic search selects the best matching images/clips for
      each activity. Everything is saved to PostgreSQL.

    Legacy flow (fallback):
      Provide `prompt`, `destination`, and `days` directly.
      Uses a rule-based activity generator with Milvus matching.
    """

    if req.session_id:
        # ----------------------------------------------------------------
        # AI-POWERED CHAT-BASED FLOW
        # ----------------------------------------------------------------
        manager = chat_session_store.get_manager(req.session_id)
        if not manager:
            raise HTTPException(
                status_code=404,
                detail="Chat session not found. Create one via POST /api/session/new"
            )

        requirements = manager.extract_requirements()
        conversation_summary = manager.get_conversation_summary()

        destination = requirements.get("destination") or "Sri Lanka"

        # Calculate duration from dates
        start_date_str = requirements.get("start_date")
        end_date_str = requirements.get("end_date")
        days = 3  # default
        if start_date_str and end_date_str:
            try:
                start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
                days = max(1, (end_dt - start_dt).days + 1)
            except ValueError:
                pass

        # Build summary prompt for storage
        prompt_text = conversation_summary[:1000] if len(conversation_summary) > 1000 else conversation_summary

        # Generate rich AI itinerary
        try:
            provider = ProviderFactory.create()
        except ValueError as e:
            raise HTTPException(status_code=500, detail=f"AI provider not configured: {str(e)}")

        ai_gen = AIItineraryGenerator(provider)
        rich_itinerary = ai_gen.generate_itinerary(conversation_summary)

        if not rich_itinerary:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate itinerary from AI. Check AI provider configuration."
            )

        # Extract flat list of activities for Milvus matching
        raw_activities = ai_gen.extract_activities_for_matching(rich_itinerary)

    else:
        # ----------------------------------------------------------------
        # LEGACY RULE-BASED FLOW
        # ----------------------------------------------------------------
        if not req.prompt or not req.destination or req.days is None:
            raise HTTPException(
                status_code=400,
                detail="Provide either 'session_id' (AI flow) or all of 'prompt', 'destination', 'days' (legacy flow)"
            )

        prompt_text = req.prompt
        destination = req.destination
        days = req.days
        rich_itinerary = None

        raw_activities = _legacy_gen.generate(req.prompt, req.destination, req.days)

    # ------------------------------------------------------------------
    # Save Itinerary record to PostgreSQL
    # ------------------------------------------------------------------
    itinerary = Itinerary(
        tenant_id=tenant_id,
        prompt=prompt_text,
        destination=destination,
        days=days,
        status="generated",
        rich_itinerary_json=json.dumps(rich_itinerary) if rich_itinerary else None,
    )
    session.add(itinerary)
    session.commit()
    session.refresh(itinerary)

    # ------------------------------------------------------------------
    # Milvus semantic search: match each activity → image + clip
    # ------------------------------------------------------------------
    db_activities = []
    used_image_ids: set = set()

    for idx, raw in enumerate(raw_activities):
        # Build a rich query string for semantic search
        query_parts = [
            raw.get("activity_name", ""),
            raw.get("location", ""),
            raw.get("keywords", ""),
            raw.get("description", "")[:80],
        ]
        query_text = " ".join(p for p in query_parts if p)

        matched_image = match_image(tenant_id, query_text, exclude_ids=used_image_ids)
        matched_clip = match_clip(tenant_id, query_text)

        if matched_image:
            used_image_ids.add(matched_image.id)

        activity = ItineraryActivity(
            tenant_id=tenant_id,
            itinerary_id=itinerary.id,
            day=raw["day"],
            activity_name=raw["activity_name"],
            location=raw.get("location"),
            keywords=raw.get("keywords", ""),
            image_id=matched_image.id if matched_image else None,
            image_url=matched_image.url if matched_image else None,
            cinematic_clip_id=matched_clip.id if matched_clip else None,
            cinematic_clip_url=matched_clip.url if matched_clip else None,
            order_index=idx,
        )
        session.add(activity)
        db_activities.append((raw, activity))

    session.commit()

    # Refresh to get DB-assigned IDs
    for _, act in db_activities:
        session.refresh(act)

    # ------------------------------------------------------------------
    # Enrich the rich_itinerary JSON with matched media URLs
    # ------------------------------------------------------------------
    if rich_itinerary:
        act_iter = iter(db_activities)
        for day_data in rich_itinerary.get("days", []):
            for act_data in day_data.get("activities", []):
                try:
                    _raw, db_act = next(act_iter)
                    act_data["image_url"] = db_act.image_url
                    act_data["cinematic_clip_url"] = db_act.cinematic_clip_url
                    act_data["image_id"] = db_act.image_id
                    act_data["cinematic_clip_id"] = db_act.cinematic_clip_id
                    act_data["db_activity_id"] = db_act.id
                except StopIteration:
                    break

        # Persist the enriched JSON back to DB
        itinerary.rich_itinerary_json = json.dumps(rich_itinerary)
        session.add(itinerary)
        session.commit()

    # Mark the chat session as generated so has_changes resets to False.
    # Without this, every subsequent user message would set has_changes=True
    # and trigger an unnecessary auto-regeneration on the frontend.
    if req.session_id:
        manager = chat_session_store.get_manager(req.session_id)
        if manager:
            manager.mark_generated()

    activities_list = [act for _, act in db_activities]
    return _build_response(itinerary, activities_list, session, rich_itinerary)


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
        rich = json.loads(itin.rich_itinerary_json) if itin.rich_itinerary_json else None
        results.append(_build_response(itin, activities, session, rich))
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

    rich = json.loads(itinerary.rich_itinerary_json) if itinerary.rich_itinerary_json else None
    return _build_response(itinerary, activities, session, rich)


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

    # Idempotent: return existing final video if already compiled or still processing.
    # If the record is stuck in "processing" (e.g. a CloudRun job silently failed),
    # delete it so compilation can be retried.
    existing_final = session.exec(
        select(FinalVideo)
        .where(FinalVideo.itinerary_id == itinerary.id)
        .where(FinalVideo.tenant_id == tenant_id)
    ).first()
    if existing_final:
        if existing_final.status == "compiled" and existing_final.video_url:
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
        # Record exists but is stuck in "processing" or "failed" — delete and retry
        session.delete(existing_final)
        session.commit()

    # Get activities in order
    activities = session.exec(
        select(ItineraryActivity)
        .where(ItineraryActivity.itinerary_id == itinerary_id)
        .where(ItineraryActivity.tenant_id == tenant_id)
        .order_by(ItineraryActivity.order_index)
    ).all()

    # Collect clip URLs (skip activities with no clip)
    clip_urls = [act.cinematic_clip_url for act in activities if act.cinematic_clip_url]

    if not clip_urls:
        raise HTTPException(
            status_code=400,
            detail="No cinematic clips are tagged to this itinerary. Upload clips and regenerate."
        )

    # Compile via the configured backend (local FFmpeg or Cloud Run Job).
    # Run in a thread executor so the blocking FFmpeg subprocess calls don't
    # stall the async event loop.
    compiler = VideoCompilerFactory.create()
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, lambda: compiler.compile(clip_urls, itinerary.id, tenant_id)
        )
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Save to DB
    final_video = FinalVideo(
        tenant_id=tenant_id,
        itinerary_id=itinerary.id,
        video_url=result.video_url or "",
        status=result.status,
    )
    session.add(final_video)

    if not result.is_async:
        itinerary.status = "video_compiled"
        session.add(itinerary)

    try:
        session.commit()
        session.refresh(final_video)
    except IntegrityError:
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

    response = {
        "message": "Final cinematic video compiled successfully" if not result.is_async
                   else "Video compilation started — poll GET /itinerary/{id} for status",
        "final_video": {
            "id": final_video.id,
            "video_url": final_video.video_url,
            "itinerary_id": final_video.itinerary_id,
            "status": final_video.status,
            "clips_used": len(clip_urls),
        }
    }

    if result.is_async:
        from fastapi.responses import JSONResponse
        return JSONResponse(content=response, status_code=202)

    return response


# ---------------------------------------------------------------------------
# GET /itinerary/{id}/video-status - Poll video compilation status
# ---------------------------------------------------------------------------
@router.get("/{itinerary_id}/video-status")
async def get_video_status(
    itinerary_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session)
):
    """
    Poll the video compilation status for an itinerary.
    Returns:
      - status: "not_started" | "processing" | "compiled" | "failed"
      - video_url: populated only when status == "compiled"
      - error: populated only when status == "failed"
    """
    itinerary = session.get(Itinerary, itinerary_id)
    if not itinerary or itinerary.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    final_video = session.exec(
        select(FinalVideo)
        .where(FinalVideo.itinerary_id == itinerary_id)
        .where(FinalVideo.tenant_id == tenant_id)
    ).first()

    if not final_video:
        return {"status": "not_started", "video_url": None, "error": None}

    if final_video.status == "failed":
        return {"status": "failed", "video_url": None, "error": "Video compilation failed. Please try again."}

    if final_video.status == "compiled" and final_video.video_url:
        return {"status": "compiled", "video_url": final_video.video_url, "error": None}

    return {"status": "processing", "video_url": None, "error": None}


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
def _build_response(
    itinerary: Itinerary,
    activities: list,
    session: Session,
    rich_itinerary: Optional[dict] = None,
) -> ItineraryResponse:
    """Build a full ItineraryResponse from models."""
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
        rich_itinerary=rich_itinerary,
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
