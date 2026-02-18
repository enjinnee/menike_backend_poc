from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.core.auth import get_current_tenant_id
from app.chat.session import chat_session_store
from app.providers.factory import ProviderFactory

router = APIRouter(prefix="/api", tags=["Chat"])


class SendMessageRequest(BaseModel):
    session_id: str
    message: str


@router.post("/session/new")
async def new_session(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Create a new chat session.
    Returns a session_id and the assistant's greeting message.
    Requires a valid JWT token.
    """
    try:
        provider = ProviderFactory.create()
        session_id, greeting = chat_session_store.create(provider)
        return {
            "session_id": session_id,
            "greeting": greeting,
        }
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/send")
async def send_message(
    req: SendMessageRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Send a message in a chat session.
    Returns the assistant's response, current collected requirements,
    and whether the conversation is complete enough to generate an itinerary.
    """
    manager = chat_session_store.get_manager(req.session_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Chat session not found")

    response = manager.send_message(req.message)

    return {
        "response": response,
        "requirements": manager.extract_requirements(),
        "is_complete": manager.is_requirements_complete(),
        "messages": manager.chat_history,
    }


@router.get("/chat/history/{session_id}")
async def get_history(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Get the full chat history and current requirements for a session.
    """
    manager = chat_session_store.get_manager(session_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Chat session not found")

    return {
        "messages": manager.chat_history,
        "requirements": manager.extract_requirements(),
        "is_complete": manager.is_requirements_complete(),
    }


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Delete a chat session from memory."""
    if not chat_session_store.exists(session_id):
        raise HTTPException(status_code=404, detail="Chat session not found")
    chat_session_store.delete(session_id)
    return {"message": "Session deleted", "session_id": session_id}
