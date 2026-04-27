FROM python:3.11-slim
WORKDIR /app
COPY ./packages/shared-py /packages/shared-py
COPY ./modules/m8-web-search /app
RUN pip install --no-cache-dir -e /packages/shared-py && pip install --no-cache-dir -e /app
ENV MODULE_IMPL=real
CMD ["sh","-c","if [ \"$MODULE_IMPL\" = \"mock\" ]; then uvicorn mocks.mock_server:app --host 0.0.0.0 --port 8000; else uvicorn app.main:app --host 0.0.0.0 --port 8000; fi"]
