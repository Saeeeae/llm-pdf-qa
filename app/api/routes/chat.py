import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.chat.rag_pipeline import (
    build_messages,
    get_active_llm_config,
    retrieve_context,
    stream_llm_response,
)
from app.db.models import AuditLog, ChatMessage, ChatSession, MsgRef, Role, User, UserPreference
from app.db.postgres import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateSessionRequest(BaseModel):
    title: str | None = None


class SessionResponse(BaseModel):
    session_id: int
    title: str | None
    created_at: str
    message_count: int = 0


class MessageResponse(BaseModel):
    msg_id: int
    sender_type: str
    message: str
    created_at: str


class ChatRequest(BaseModel):
    message: str
    search_scope: str = "all"
    use_web_search: bool = False


@router.post("/sessions", response_model=SessionResponse)
def create_session(req: CreateSessionRequest, user: User = Depends(get_current_user)):
    with get_session() as session:
        chat_session = ChatSession(
            created_by=user.user_id,
            title=req.title,
            session_type="private",
        )
        session.add(chat_session)
        session.flush()
        return SessionResponse(
            session_id=chat_session.session_id,
            title=chat_session.title,
            created_at=chat_session.created_at.isoformat(),
        )


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(limit: int = 20, offset: int = 0, user: User = Depends(get_current_user)):
    with get_session() as session:
        sessions = (
            session.query(ChatSession)
            .filter(ChatSession.created_by == user.user_id)
            .order_by(ChatSession.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            SessionResponse(
                session_id=s.session_id,
                title=s.title,
                created_at=s.created_at.isoformat(),
                message_count=len(s.messages),
            )
            for s in sessions
        ]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
def get_messages(session_id: int, user: User = Depends(get_current_user)):
    with get_session() as session:
        chat_session = session.query(ChatSession).filter(
            ChatSession.session_id == session_id,
            ChatSession.created_by == user.user_id,
        ).first()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")
        return [
            MessageResponse(
                msg_id=m.msg_id,
                sender_type=m.sender_type,
                message=m.message,
                created_at=m.created_at.isoformat(),
            )
            for m in sorted(chat_session.messages, key=lambda x: x.created_at)
        ]


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, user: User = Depends(get_current_user)):
    with get_session() as session:
        chat_session = session.query(ChatSession).filter(
            ChatSession.session_id == session_id,
            ChatSession.created_by == user.user_id,
        ).first()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")
        session.delete(chat_session)


@router.post("/sessions/{session_id}/stream")
def stream_chat(session_id: int, req: ChatRequest, user: User = Depends(get_current_user)):
    with get_session() as session:
        chat_session = session.query(ChatSession).filter(
            ChatSession.session_id == session_id,
            ChatSession.created_by == user.user_id,
        ).first()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        messages_history = sorted(chat_session.messages, key=lambda x: x.created_at)[-20:]
        history = [{"role": m.sender_type, "content": m.message} for m in messages_history]

        role = session.query(Role).filter(Role.role_id == user.role_id).first()
        auth_level = role.auth_level if role else 0

    def generate():
        full_response = ""
        context_chunks = []
        assistant_msg_id = None

        try:
            context_chunks = retrieve_context(
                query=req.message,
                user_id=user.user_id,
                user_dept_id=user.dept_id,
                user_auth_level=auth_level,
                search_scope=req.search_scope,
            )

            llm_config = get_active_llm_config()
            llm_messages = build_messages(
                system_prompt=llm_config.system_prompt or "",
                context_chunks=context_chunks,
                chat_history=history,
                user_message=req.message,
            )

            for token in stream_llm_response(llm_messages, llm_config):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            if context_chunks:
                refs = [
                    {
                        "doc_id": c["doc_id"],
                        "file_name": c["file_name"],
                        "page": c.get("page_number"),
                        "score": round(c["score"], 3),
                    }
                    for c in context_chunks
                ]
                yield f"data: {json.dumps({'type': 'references', 'refs': refs})}\n\n"

            with get_session() as db_session:
                user_msg = ChatMessage(
                    session_id=session_id,
                    user_id=user.user_id,
                    sender_type="user",
                    message=req.message,
                )
                db_session.add(user_msg)
                db_session.flush()

                assistant_msg = ChatMessage(
                    session_id=session_id,
                    sender_type="assistant",
                    message=full_response,
                )
                db_session.add(assistant_msg)
                db_session.flush()
                assistant_msg_id = assistant_msg.msg_id

                for chunk in context_chunks:
                    db_session.add(MsgRef(
                        msg_id=assistant_msg.msg_id,
                        doc_id=chunk["doc_id"],
                        chunk_id=chunk["chunk_id"],
                        relevance_score=chunk["score"],
                    ))

                s = db_session.query(ChatSession).filter(ChatSession.session_id == session_id).first()
                if s:
                    if not s.title:
                        s.title = req.message[:50]
                    s.updated_at = datetime.now(timezone.utc)

                db_session.add(AuditLog(
                    user_id=user.user_id,
                    action_type="chat_query",
                    target_type="chat_session",
                    target_id=session_id,
                    description=req.message[:200],
                ))

            yield f"data: {json.dumps({'type': 'done', 'msg_id': assistant_msg_id})}\n\n"

        except Exception as e:
            logger.error("Stream chat error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
