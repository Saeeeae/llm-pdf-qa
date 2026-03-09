import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from rag_serving.api.auth.dependencies import get_current_user
from rag_serving.api.rag.retriever import hybrid_search
from rag_serving.api.rag.reranker import rerank
from rag_serving.api.rag.graph_retriever import get_graph_context
from rag_serving.api.rag.generator import build_messages, stream_response
from rag_serving.config import serving_settings
from shared.models.orm import (
    AuditLog, ChatMessage, ChatSession, LLMConfig, MsgRef,
    QueryLog, User, UserPreference,
)
from shared.models.registry import registry
from shared.db import get_session

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


def _get_accessible_folder_ids(user_id: int) -> list[int]:
    with get_session() as session:
        rows = session.execute(
            text(
                "SELECT folder_id FROM folder_access "
                "WHERE user_id = :uid AND is_active = TRUE "
                "AND (expires_at IS NULL OR expires_at > NOW())"
            ),
            {"uid": user_id},
        ).fetchall()
        return [r.folder_id for r in rows]


def _get_active_llm_config() -> LLMConfig:
    with get_session() as session:
        config = session.query(LLMConfig).filter(LLMConfig.is_active == True).first()
        if config:
            session.expunge(config)
            return config
    fallback = LLMConfig()
    fallback.model_name = serving_settings.vllm_model_name
    fallback.vllm_url = serving_settings.vllm_base_url
    fallback.system_prompt = "당신은 사내 문서를 기반으로 답변하는 AI 어시스턴트입니다. 제공된 문서 내용을 바탕으로 정확하고 도움이 되는 답변을 제공하세요."
    fallback.max_tokens = 4096
    fallback.temperature = 0.7
    fallback.top_p = 0.9
    fallback.context_chunks = 5
    return fallback


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

    def generate():
        full_response = ""
        context_chunks = []
        reranked_chunks = []
        graph_ctx = ""
        assistant_msg_id = None
        start_time = time.time()

        try:
            # Embed query
            embed_model = registry.embedding()
            query_vector = embed_model.encode(req.message).tolist()

            # Hybrid search (dense + sparse with RRF)
            accessible_folders = _get_accessible_folder_ids(user.user_id)
            context_chunks = hybrid_search(
                query_text=req.message,
                query_vector=query_vector,
                dept_id=user.dept_id,
                accessible_folder_ids=accessible_folders,
                search_scope=req.search_scope,
            )

            # Rerank
            llm_config = _get_active_llm_config()
            reranked_chunks = rerank(req.message, context_chunks, top_k=llm_config.context_chunks)

            # Graph context
            graph_ctx = get_graph_context(req.message)

            # Build messages with graph context
            llm_messages = build_messages(
                system_prompt=llm_config.system_prompt or "",
                context_chunks=reranked_chunks,
                graph_context=graph_ctx,
                chat_history=history,
                user_message=req.message,
            )

            # Stream from vLLM
            for token in stream_response(
                llm_messages,
                vllm_url=llm_config.vllm_url,
                model_name=llm_config.model_name,
                max_tokens=llm_config.max_tokens,
                temperature=llm_config.temperature,
                top_p=llm_config.top_p,
            ):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            # Send references
            if reranked_chunks:
                refs = [
                    {
                        "doc_id": c["doc_id"],
                        "file_name": c["file_name"],
                        "page": c.get("page_number"),
                        "score": round(c.get("rerank_score", c.get("rrf_score", 0)), 3),
                    }
                    for c in reranked_chunks
                ]
                yield f"data: {json.dumps({'type': 'references', 'refs': refs})}\n\n"

            # Save messages and log
            latency_ms = int((time.time() - start_time) * 1000)
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

                for chunk in reranked_chunks:
                    db_session.add(MsgRef(
                        msg_id=assistant_msg.msg_id,
                        doc_id=chunk["doc_id"],
                        chunk_id=chunk["chunk_id"],
                        relevance_score=chunk.get("rerank_score", chunk.get("rrf_score")),
                    ))

                s = db_session.query(ChatSession).filter(ChatSession.session_id == session_id).first()
                if s:
                    if not s.title:
                        s.title = req.message[:50]
                    s.updated_at = datetime.now(timezone.utc)

                # Log to query_logs
                db_session.add(QueryLog(
                    user_id=user.user_id,
                    session_id=session_id,
                    prompt=req.message,
                    retrieved_chunks=[
                        {"chunk_id": c["chunk_id"], "rrf_score": round(c.get("rrf_score", 0), 4)}
                        for c in context_chunks[:10]
                    ],
                    reranked_chunks=[
                        {"chunk_id": c["chunk_id"], "rerank_score": round(c.get("rerank_score", 0), 4)}
                        for c in reranked_chunks
                    ],
                    graph_context={"text": graph_ctx} if graph_ctx else None,
                    final_answer=full_response[:2000],
                    model_name=llm_config.model_name,
                    latency_ms=latency_ms,
                ))

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
