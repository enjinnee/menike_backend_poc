import json
import logging
import uuid
from typing import Dict, Optional
from datetime import datetime

from app.chat.manager import ChatManager
from app.providers.base import AIProvider

logger = logging.getLogger("manike.session")


class ChatSessionStore:
    """In-memory write-through cache for chat sessions.

    Active sessions are kept in _sessions for fast access.
    Every mutation is also written to PostgreSQL via the injected DB session.
    On cache miss (server restart), the manager is rebuilt from DB records.
    """

    def __init__(self):
        self._sessions: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # create — called by POST /api/session/new
    # ------------------------------------------------------------------
    def create(self, provider: AIProvider, db, user_id: str, tenant_id: str) -> tuple:
        """Create a new chat session, persist to DB, return (session_id, greeting)."""
        from app.models.sql_models import ChatSession, ChatMessage

        session_id = str(uuid.uuid4())
        manager = ChatManager(provider)
        greeting = manager.get_greeting()

        # In-memory store
        self._sessions[session_id] = {
            "manager": manager,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Persist ChatSession row
        db_chat_session = ChatSession(
            id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            title="New Chat",
            requirements_json=json.dumps(manager.user_requirements),
        )
        db.add(db_chat_session)
        db.flush()  # ensure chat_session row exists before FK reference in chat_message

        # Persist greeting as first ChatMessage
        db.add(ChatMessage(
            session_id=session_id,
            tenant_id=tenant_id,
            role="assistant",
            content=greeting,
        ))
        db.commit()
        logger.info("Session %s persisted to DB (user=%s, tenant=%s)", session_id, user_id, tenant_id)
        return session_id, greeting

    # ------------------------------------------------------------------
    # persist_exchange — called after every send_message
    # ------------------------------------------------------------------
    def persist_exchange(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        requirements: dict,
        db,
        tenant_id: str,
        destination: Optional[str] = None,
    ) -> None:
        """Append user + assistant messages to DB and update session metadata."""
        from app.models.sql_models import ChatSession, ChatMessage

        now = datetime.utcnow()

        db.add(ChatMessage(
            session_id=session_id,
            tenant_id=tenant_id,
            role="user",
            content=user_message,
            created_at=now,
        ))
        db.add(ChatMessage(
            session_id=session_id,
            tenant_id=tenant_id,
            role="assistant",
            content=assistant_message,
        ))

        db_session = db.get(ChatSession, session_id)
        if db_session:
            db_session.requirements_json = json.dumps(requirements)
            db_session.updated_at = datetime.utcnow()
            if destination and db_session.title == "New Chat":
                db_session.title = destination
            db.add(db_session)

        db.commit()

    # ------------------------------------------------------------------
    # get_manager — hot path returns from memory; falls back to DB rebuild
    # ------------------------------------------------------------------
    def get_manager(
        self,
        session_id: str,
        db=None,
        provider: Optional[AIProvider] = None,
    ) -> Optional[ChatManager]:
        if session_id in self._sessions:
            return self._sessions[session_id]["manager"]
        if db is None or provider is None:
            return None
        return self._rebuild_from_db(session_id, db, provider)

    # ------------------------------------------------------------------
    # _rebuild_from_db — reconstruct ChatManager from persisted rows
    # ------------------------------------------------------------------
    def _rebuild_from_db(self, session_id: str, db, provider: AIProvider) -> Optional[ChatManager]:
        from app.models.sql_models import ChatSession, ChatMessage
        from sqlmodel import select

        db_session = db.get(ChatSession, session_id)
        if not db_session or db_session.is_deleted:
            return None

        messages = db.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        ).all()

        manager = ChatManager(provider)

        # Restore requirements from JSON snapshot (avoids re-running AI extraction)
        if db_session.requirements_json:
            try:
                saved_reqs = json.loads(db_session.requirements_json)
                for field, value in saved_reqs.items():
                    if value is not None:
                        manager.flow.update_field(field, value)
            except Exception:
                pass

        # Replay chat history
        for msg in messages:
            manager.chat_history.append({
                "role": msg.role,
                "content": msg.content,
            })

        # Cache for subsequent requests in this server process
        self._sessions[session_id] = {
            "manager": manager,
            "created_at": db_session.created_at.isoformat(),
        }
        logger.info("Session %s rebuilt from DB (%d messages)", session_id, len(messages))
        return manager

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def delete(self, session_id: str) -> None:
        """Evict from in-memory cache. API layer handles DB soft-delete."""
        self._sessions.pop(session_id, None)
        logger.info("Session %s evicted from cache", session_id)


# Global singleton used across the app
chat_session_store = ChatSessionStore()
