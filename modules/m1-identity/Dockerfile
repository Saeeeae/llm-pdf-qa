FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY ./packages/shared-py /packages/shared-py
COPY ./modules/m1-identity /app
RUN pip install --no-cache-dir -e /packages/shared-py && pip install --no-cache-dir -e /app
# Log directory — bind-mounted from host data/logs/m1-identity/
RUN mkdir -p /var/log/m1-identity && chmod 777 /var/log/m1-identity
ENV MODULE_IMPL=real
# Single worker on purpose: RotatingFileHandler is not process-safe, so
# multi-worker would corrupt log rotation. Identity workload (auth + scheduled
# sync) is light; scale horizontally with replicas instead of in-process workers.
CMD ["sh","-c","if [ \"$MODULE_IMPL\" = \"mock\" ]; then uvicorn mocks.mock_server:app --host 0.0.0.0 --port 8000; else uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --loop uvloop --http httptools; fi"]
