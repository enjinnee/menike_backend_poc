import json
import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.auth import get_current_user
from app.core.database import get_session
from app.chat.session import chat_session_store
from app.models.sql_models import ChatSession, ChatMessage, User, FinalVideo, Itinerary
from app.providers.factory import ProviderFactory

logger = logging.getLogger("manike.chat")

router = APIRouter(prefix="/api", tags=["Chat"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class SendMessageRequest(BaseModel):
    session_id: str
    message: str


class VoiceMessageRequest(BaseModel):
    session_id: str
    transcript: str


class ShareToggleRequest(BaseModel):
    is_shared: bool


class SessionSummary(BaseModel):
    session_id: str
    title: str
    is_shared: bool
    is_owner: bool
    created_at: str
    updated_at: str
    requirements: Optional[dict] = None
    itinerary_id: Optional[str] = None


# ---------------------------------------------------------------------------
# POST /api/session/new
# ---------------------------------------------------------------------------
@router.post("/session/new")
async def new_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Create a new chat session persisted to PostgreSQL."""
    try:
        provider = ProviderFactory.create()
        session_id, greeting = chat_session_store.create(
            provider=provider,
            db=db,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )
        logger.info("New session created: %s (user=%s)", session_id, current_user.id)
        return {"session_id": session_id, "greeting": greeting}
    except ValueError as e:
        logger.error("Failed to create session for user=%s: %s", current_user.id, e)
        raise HTTPException(status_code=500, detail="Unable to start a new chat session. Please contact the administrator.")


# ---------------------------------------------------------------------------
# POST /api/chat/send
# ---------------------------------------------------------------------------
@router.post("/chat/send")
async def send_message(
    req: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Send a message; persist both turns to DB. Handles server-restart cache miss."""
    db_session = db.get(ChatSession, req.session_id)
    if not db_session or db_session.is_deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")

    _check_session_access(db_session, current_user)

    provider = ProviderFactory.create()
    manager = chat_session_store.get_manager(req.session_id, db=db, provider=provider)
    if not manager:
        logger.error("Session %s could not be loaded for user=%s", req.session_id, current_user.id)
        raise HTTPException(status_code=404, detail="Chat session could not be loaded")

    logger.info("Message received in session=%s (user=%s)", req.session_id, current_user.id)
    response = manager.send_message(req.message)
    requirements = manager.extract_requirements()

    chat_session_store.persist_exchange(
        session_id=req.session_id,
        user_message=req.message,
        assistant_message=response,
        requirements=requirements,
        db=db,
        tenant_id=current_user.tenant_id,
        destination=requirements.get("destination"),
    )

    return {
        "response": response,
        "requirements": requirements,
        "is_complete": manager.is_requirements_complete(),
        "requirements_complete": manager.is_ready_to_generate(),
        "has_changes": manager.has_changes_since_generation(),
        "messages": manager.chat_history,
    }


# ---------------------------------------------------------------------------
# POST /api/chat/voice
# ---------------------------------------------------------------------------
@router.post("/chat/voice")
async def process_voice_message(
    req: VoiceMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Process voice transcription; persist exchange to DB."""
    db_session = db.get(ChatSession, req.session_id)
    if not db_session or db_session.is_deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")

    _check_session_access(db_session, current_user)

    transcript = req.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Empty transcript")

    provider = ProviderFactory.create()
    manager = chat_session_store.get_manager(req.session_id, db=db, provider=provider)
    if not manager:
        raise HTTPException(status_code=404, detail="Chat session could not be loaded")

    response = manager.send_message(transcript)
    requirements = manager.extract_requirements()

    chat_session_store.persist_exchange(
        session_id=req.session_id,
        user_message=transcript,
        assistant_message=response,
        requirements=requirements,
        db=db,
        tenant_id=current_user.tenant_id,
        destination=requirements.get("destination"),
    )

    return {
        "response": response,
        "requirements": requirements,
        "requirements_complete": manager.is_ready_to_generate(),
        "has_changes": manager.has_changes_since_generation(),
    }


# ---------------------------------------------------------------------------
# GET /api/chat/sessions — sidebar session list
# ---------------------------------------------------------------------------
@router.get("/chat/sessions", response_model=List[SessionSummary])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Return own sessions + shared sessions within the same tenant."""
    own = db.exec(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .where(ChatSession.is_deleted == False)
        .order_by(ChatSession.updated_at.desc())
    ).all()

    shared = db.exec(
        select(ChatSession)
        .where(ChatSession.tenant_id == current_user.tenant_id)
        .where(ChatSession.user_id != current_user.id)
        .where(ChatSession.is_shared == True)
        .where(ChatSession.is_deleted == False)
        .order_by(ChatSession.updated_at.desc())
    ).all()

    return (
        [_to_summary(s, is_owner=True) for s in own]
        + [_to_summary(s, is_owner=False) for s in shared]
    )


# ---------------------------------------------------------------------------
# GET /api/chat/history/{session_id}
# ---------------------------------------------------------------------------
@router.get("/chat/history/{session_id}")
async def get_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Return chat history and requirements; reads from DB on cache miss."""
    db_session = db.get(ChatSession, session_id)
    if not db_session or db_session.is_deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")

    _check_session_access(db_session, current_user)

    provider = ProviderFactory.create()
    manager = chat_session_store.get_manager(session_id, db=db, provider=provider)

    if manager:
        return {
            "messages": manager.chat_history,
            "requirements": manager.extract_requirements(),
            "is_complete": manager.is_requirements_complete(),
        }

    # Fallback: raw DB read
    messages = db.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    ).all()

    return {
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "requirements": json.loads(db_session.requirements_json or "{}"),
        "is_complete": False,
    }


# ---------------------------------------------------------------------------
# POST /api/session/{session_id}/resume
# ---------------------------------------------------------------------------
@router.post("/session/{session_id}/resume")
async def resume_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Load a past session into memory and return full message list for resumption."""
    db_session = db.get(ChatSession, session_id)
    if not db_session or db_session.is_deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")

    _check_session_access(db_session, current_user)

    provider = ProviderFactory.create()
    manager = chat_session_store.get_manager(session_id, db=db, provider=provider)
    if not manager:
        logger.error("Failed to rebuild session=%s from DB for user=%s", session_id, current_user.id)
        raise HTTPException(status_code=500, detail="Failed to rebuild session from database")

    messages = db.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    ).all()

    return {
        "session_id": session_id,
        "title": db_session.title,
        "is_shared": db_session.is_shared,
        "is_owner": db_session.user_id == current_user.id,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "requirements": manager.extract_requirements(),
        "is_complete": manager.is_requirements_complete(),
        "requirements_complete": manager.is_ready_to_generate(),
        "itinerary_id": db_session.itinerary_id,
    }


# ---------------------------------------------------------------------------
# PATCH /api/session/{session_id}/share — owner only
# ---------------------------------------------------------------------------
@router.patch("/session/{session_id}/share")
async def toggle_share(
    session_id: str,
    req: ShareToggleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Toggle is_shared on a session. Only the owner may call this."""
    db_session = db.get(ChatSession, session_id)
    if not db_session or db_session.is_deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")

    if db_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the session owner can change sharing")

    db_session.is_shared = req.is_shared
    db_session.updated_at = datetime.utcnow()
    db.add(db_session)
    db.commit()
    db.refresh(db_session)

    return {"session_id": session_id, "is_shared": db_session.is_shared}


# ---------------------------------------------------------------------------
# DELETE /api/session/{session_id} — owner only, soft-delete
# ---------------------------------------------------------------------------
@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Soft-delete a session (owner only). Also removes FinalVideo record and GCS blob."""
    db_session = db.get(ChatSession, session_id)
    if not db_session or db_session.is_deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")

    if db_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the session owner can delete this session")

    # Delete associated FinalVideo + GCS blob if present
    if db_session.itinerary_id:
        final_video = db.exec(
            select(FinalVideo).where(FinalVideo.itinerary_id == db_session.itinerary_id)
        ).first()
        if final_video:
            _delete_gcs_blob(final_video.video_url)
            db.delete(final_video)

    db_session.is_deleted = True
    db_session.updated_at = datetime.utcnow()
    db.add(db_session)
    db.commit()

    chat_session_store.delete(session_id)
    return {"message": "Session deleted", "session_id": session_id}


def _delete_gcs_blob(video_url: str) -> None:
    """Best-effort deletion of a GCS blob given its public URL."""
    try:
        from google.cloud import storage as gcs
        import google.auth
        bucket_name = os.getenv("GCS_BUCKET_NAME", "manike-ai-media")
        prefix = f"https://storage.googleapis.com/{bucket_name}/"
        if not video_url.startswith(prefix):
            return
        blob_name = video_url[len(prefix):]
        credentials, _ = google.auth.default()
        client = gcs.Client(credentials=credentials)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()
        logger.info("Deleted GCS blob: %s", blob_name)
    except Exception as exc:
        logger.warning("Could not delete GCS blob for %s: %s", video_url, exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _check_session_access(db_session: ChatSession, current_user: User) -> None:
    """Raise 403 if the user has no access to this session."""
    is_owner = db_session.user_id == current_user.id
    is_shared_in_tenant = (
        db_session.is_shared and db_session.tenant_id == current_user.tenant_id
    )
    if not is_owner and not is_shared_in_tenant:
        raise HTTPException(status_code=403, detail="Access denied")


def _to_summary(s: ChatSession, is_owner: bool) -> SessionSummary:
    reqs = None
    if s.requirements_json:
        try:
            reqs = json.loads(s.requirements_json)
        except Exception:
            pass
    return SessionSummary(
        session_id=s.id,
        title=s.title,
        is_shared=s.is_shared,
        is_owner=is_owner,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
        requirements=reqs,
        itinerary_id=s.itinerary_id,
    )
