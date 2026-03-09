FROM python:3.11-slim

WORKDIR /app
COPY rag-pipeline/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY rag-pipeline /app/rag_pipeline

ENV PYTHONPATH=/app
CMD ["uvicorn", "rag_pipeline.api.main:app", "--host", "0.0.0.0", "--port", "8001"]
