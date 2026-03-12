from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from shared.db import get_session
from shared.event_logger import get_event_logger
from shared.middleware import RequestLoggingMiddleware
from shared.models.orm import Document, PipelineLog
from rag_pipeline.tasks.pipeline_tasks import process_document_task, process_batch_task

elog = get_event_logger("pipeline")

app = FastAPI(title="RAG Pipeline API", version="2.0")
app.add_middleware(RequestLoggingMiddleware)


class TriggerRequest(BaseModel):
    doc_ids: list[int]


class TriggerResponse(BaseModel):
    message: str
    doc_ids: list[int]


@app.post("/pipeline/trigger", response_model=TriggerResponse)
def trigger_pipeline(req: TriggerRequest):
    if not req.doc_ids:
        raise HTTPException(400, "No doc_ids provided")
    process_batch_task.delay(req.doc_ids)
    elog.info("Pipeline triggered", details={"doc_ids": req.doc_ids[:20], "count": len(req.doc_ids)})
    return TriggerResponse(message="Pipeline triggered", doc_ids=req.doc_ids)


@app.post("/pipeline/trigger/full", response_model=TriggerResponse)
def trigger_full_reprocess():
    with get_session() as session:
        docs = session.query(Document.doc_id).all()
        doc_ids = [d.doc_id for d in docs]
    if not doc_ids:
        raise HTTPException(404, "No documents found")
    process_batch_task.delay(doc_ids)
    elog.info("Full reprocess triggered", details={"count": len(doc_ids)})
    return TriggerResponse(message="Full reprocess triggered", doc_ids=doc_ids)


@app.get("/pipeline/status/{doc_id}")
def pipeline_status(doc_id: int):
    with get_session() as session:
        doc = session.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(404, "Document not found")
        logs = session.query(PipelineLog).filter(
            PipelineLog.doc_id == doc_id
        ).order_by(PipelineLog.started_at.desc()).all()
        return {
            "doc_id": doc_id,
            "status": doc.status,
            "stages": [
                {
                    "stage": log.stage,
                    "status": log.status,
                    "started_at": log.started_at.isoformat() if log.started_at else None,
                    "finished_at": log.finished_at.isoformat() if log.finished_at else None,
                    "error": log.error_message,
                }
                for log in logs
            ],
        }


@app.get("/health")
def health():
    return {"status": "ok"}
