FROM python:3.11-slim

WORKDIR /app
COPY rag-sync-monitor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY rag-sync-monitor /app/rag_sync_monitor

ENV PYTHONPATH=/app
CMD ["streamlit", "run", "rag_sync_monitor/dashboard/app.py", "--server.port=8003", "--server.headless=true"]
