FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC

# Install Python 3.11 via deadsnakes PPA (Ubuntu 22.04 only has 3.10)
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ >/etc/timezone && \
    apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3.11-dev python3.11-distutils \
    build-essential curl && \
    ln -sf /usr/bin/python3.11 /usr/bin/python && \
    ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install PyTorch with CUDA first
RUN python -m pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124

COPY rag-pipeline/requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY rag-pipeline /app/rag_pipeline

ENV PYTHONPATH=/app
CMD ["python", "-m", "uvicorn", "rag_pipeline.api.main:app", "--host", "0.0.0.0", "--port", "8001"]
