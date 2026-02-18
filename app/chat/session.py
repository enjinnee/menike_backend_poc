import uuid
from typing import Dict, Optional
from app.chat.manager import ChatManager
from app.providers.base import AIProvider


class ChatSessionStore:
    """In-memory store for chat sessions."""

    def __init__(self):
        self._sessions: Dict[str, dict] = {}

    def create(self, provider: AIProvider) -> tuple:
        """Create a new chat session. Returns (session_id, greeting)."""
        session_id = str(uuid.uuid4())
        manager = ChatManager(provider)
        greeting = manager.get_greeting()
        self._sessions[session_id] = {
            "manager": manager,
        }
        return session_id, greeting

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def get_manager(self, session_id: str) -> Optional[ChatManager]:
        session = self._sessions.get(session_id)
        return session["manager"] if session else None

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


# Global singleton used across the app
chat_session_store = ChatSessionStore()
