FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY ./packages/shared-py /packages/shared-py
COPY ./modules/m4-rag /app
RUN pip install --no-cache-dir -e /packages/shared-py && pip install --no-cache-dir -e /app
ENV HF_HOME=/data/models \
    TRANSFORMERS_CACHE=/data/models \
    SENTENCE_TRANSFORMERS_HOME=/data/models \
    MODULE_IMPL=real
CMD ["sh","-c","if [ \"$MODULE_IMPL\" = \"mock\" ]; then uvicorn mocks.mock_server:app --host 0.0.0.0 --port 8000; else uvicorn app.main:app --host 0.0.0.0 --port 8000; fi"]
