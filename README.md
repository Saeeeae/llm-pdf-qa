# RAG Document Preprocessing Pipeline

문서(PDF, DOCX, XLSX, PPTX, 이미지)를 MinerU 기반으로 **OCR → Chunking → Embedding** 처리하여
PostgreSQL(청크 DB) + Qdrant(벡터 DB)에 저장하는 온프레미스 전처리 파이프라인.

## 목적

- RAG 서비스를 위한 **데이터 전처리 인프라** (Q&A 시스템 자체가 아님)
- FastAPI로 OCR/Chunking/Embedding 기능을 **재사용 가능한 API**로 제공
- 외부 서비스(챗봇, 검색 등)에서 동일한 전처리 파이프라인을 호출 가능
- 매일 02:00 자동 동기화로 신규/수정/삭제 파일 **차분 업데이트**

## Architecture

```
                        ┌─────────────────────────────────┐
                        │         FastAPI (port 8000)      │
                        │                                  │
  [파일 업로드] ──────▶  │  POST /api/v1/processing/parse   │  ← 파싱만
  [파일 업로드] ──────▶  │  POST /api/v1/processing/chunk   │  ← 파싱 + 청킹
  [파일 업로드] ──────▶  │  POST /api/v1/processing/embed   │  ← 파싱 + 청킹 + 임베딩
  [파일 업로드] ──────▶  │  POST /api/v1/processing/full-pipeline  │  ← 전체 + DB 저장
                        │  POST /api/v1/processing/search  │  ← 벡터 검색
                        └──────────┬───────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                     ▼
    ┌──────────────┐    ┌──────────────┐      ┌──────────────┐
    │  MinerU v2.x │    │   Chunker    │      │   Embedder   │
    │  (OCR/PDF)   │    │  (512 tokens)│      │ (E5-large)   │
    └──────┬───────┘    └──────┬───────┘      └──────┬───────┘
           └───────────┬───────┘                     │
                       ▼                             ▼
              ┌──────────────┐              ┌──────────────┐
              │  PostgreSQL  │              │    Qdrant    │
              │ (metadata +  │              │  (vectors)   │
              │   chunks)    │              │              │
              └──────────────┘              └──────────────┘

  [DOC_WATCH_DIR] ──▶ Celery Worker ──▶ 동일 파이프라인
                     (매일 02:00 자동 동기화)
```

### Docker Services

| Service | 역할 | Port |
|---------|------|------|
| `api` | FastAPI 문서 처리 API | 8000 |
| `celery-worker` | 비동기 인제스트 + 동기화 처리 | - |
| `celery-beat` | 매일 02:00 스케줄러 | - |
| `postgres` | 메타데이터 + 청크 원본 저장 | 5432 |
| `qdrant` | 벡터 저장/검색 | 6333 |
| `redis` | Celery 브로커 | 6379 |

---

## Quick Start

### 1. 환경 설정

```bash
git clone <repository-url>
cd llm_again

cp .env.example .env
vi .env
```

**필수 수정 항목:**

```ini
# 문서 폴더 경로 (호스트 머신의 절대경로)
DOC_WATCH_DIR=/home/user/documents     # Linux
DOC_WATCH_DIR=/Users/user/documents    # Mac

# DB 비밀번호 (운영 환경에서 반드시 변경)
POSTGRES_PASSWORD=your_secure_password

# GPU가 있는 경우 MinerU 백엔드 변경 (정확도 향상)
MINERU_BACKEND=hybrid-auto-engine      # GPU 10GB+ VRAM
# MINERU_BACKEND=pipeline              # CPU only (기본값)
```

### 2. 서비스 시작

```bash
make up
```

```bash
# 상태 확인
make ps

# 기대 출력:
# rag-api             running
# rag-postgres        running (healthy)
# rag-qdrant          running (healthy)
# rag-redis           running (healthy)
# rag-celery-worker   running
# rag-celery-beat     running
```

### 3. 파일 스캔 (처리 전 확인)

```bash
# DOC_WATCH_DIR 내 파일 목록 확인
docker compose exec celery-worker python -m app.main scan

# 출력 예시:
# Directory: /data/documents
# Total files: 47
# By type: {'pdf': 25, 'docx': 10, 'xlsx': 8, 'pptx': 4}
#
#   .pdf      1234.5 KB  annual_report_2024.pdf
#   .docx      456.2 KB  meeting_notes.docx
#   ...

# glob 패턴으로 특정 파일만 필터링
docker compose exec celery-worker python -m app.main scan --pattern "**/*.pdf"
docker compose exec celery-worker python -m app.main scan --pattern "report_*.xlsx"
docker compose exec celery-worker python -m app.main scan --ext pdf,docx

# API로 스캔
curl "http://localhost:8000/api/v1/documents/scan"
curl "http://localhost:8000/api/v1/documents/scan?pattern=**/*.pdf"
curl "http://localhost:8000/api/v1/documents/scan?extensions=pdf,docx&recursive=true"
```

### 4. 문서 처리

```bash
# 방법 A: 감시 폴더 전체 동기화
cp ~/my_documents/*.pdf /home/user/documents/
make sync

# 방법 B: 스캔 결과를 바로 인제스트
docker compose exec celery-worker python -m app.main scan --pattern "**/*.pdf" --ingest

# 방법 C: API로 파일 업로드 (전체 파이프라인)
curl -X POST http://localhost:8000/api/v1/processing/full-pipeline \
  -F "file=@report.pdf"

# 방법 D: API로 스캔 + 일괄 인제스트
curl -X POST "http://localhost:8000/api/v1/documents/scan/ingest?pattern=**/*.pdf"

# 방법 E: CLI로 단일 파일
make ingest-file FILE=/data/documents/report.pdf

# 방법 F: 특정 디렉토리만 인제스트
docker compose exec celery-worker python -m app.main ingest --dir /data/documents/2024/
```

### 5. 상태 확인

```bash
make status
# Documents: total=150, indexed=145, failed=3, pending=2
# Chunks: total=4230

# 또는 API:
curl http://localhost:8000/api/v1/documents/stats/summary
```

---

## 모델 다운로드

모든 모델은 **HuggingFace에서 첫 실행 시 자동 다운로드**됩니다.
Docker 볼륨에 캐시되어 이후 재다운로드 불필요.

| 모델 | 용도 | 크기 | 출처 |
|------|------|------|------|
| [intfloat/multilingual-e5-large](https://huggingface.co/intfloat/multilingual-e5-large) | 임베딩 (1024dim, 한/영) | ~2.2GB | HuggingFace 자동 |
| MinerU 내장 모델 (layoutlmv3 등) | PDF 레이아웃 분석, OCR | ~1-3GB | `mineru[all]` 설치 시 자동 |

```bash
# (선택) 사전 다운로드:
pip install huggingface_hub
huggingface-cli download intfloat/multilingual-e5-large
```

> **HuggingFace Token**: gated 모델 사용 시
> https://huggingface.co/settings/tokens 에서 토큰 발급 → `.env`의 `HF_TOKEN`에 설정

---

## API Reference

서비스 시작 후 Swagger UI에서 전체 API 확인 가능:
**http://localhost:8000/docs**

### Processing API (재사용 가능한 문서 처리)

| Endpoint | Method | 설명 |
|----------|--------|------|
| `/api/v1/processing/parse` | POST | 파일 업로드 → **파싱만** (텍스트 추출) |
| `/api/v1/processing/chunk` | POST | 파일 업로드 → **파싱 + 청킹** |
| `/api/v1/processing/embed` | POST | 파일 업로드 → **파싱 + 청킹 + 임베딩** |
| `/api/v1/processing/full-pipeline` | POST | 파일 업로드 → **전체 파이프라인 + DB 저장** |
| `/api/v1/processing/search` | POST | 쿼리 텍스트 → **벡터 유사도 검색** |

### Documents API (DB 관리 + 파일 스캔)

| Endpoint | Method | 설명 |
|----------|--------|------|
| `/api/v1/documents` | GET | 문서 목록 조회 (필터: status, type) |
| `/api/v1/documents/{doc_id}` | GET | 문서 상세 (청크 포함) |
| `/api/v1/documents/scan` | GET | **디렉토리 스캔** (glob 패턴, 확장자 필터) |
| `/api/v1/documents/scan/ingest` | POST | **스캔 + 일괄 인제스트** |
| `/api/v1/documents/ingest` | POST | 단일 파일 비동기 인제스트 (Celery) |
| `/api/v1/documents/sync` | POST | 감시 폴더 변경 감지 동기화 |
| `/api/v1/documents/{doc_id}` | DELETE | 문서 삭제 (DB + Qdrant) |
| `/api/v1/documents/stats/summary` | GET | 처리 현황 요약 |

### API 사용 예시

```bash
# 파싱만 (텍스트 추출 결과 확인)
curl -X POST http://localhost:8000/api/v1/processing/parse \
  -F "file=@document.pdf"

# 청킹 (커스텀 chunk_size)
curl -X POST "http://localhost:8000/api/v1/processing/chunk?chunk_size=256&chunk_overlap=30" \
  -F "file=@document.pdf"

# 전체 파이프라인 (파싱 → 청킹 → 임베딩 → DB 저장)
curl -X POST http://localhost:8000/api/v1/processing/full-pipeline \
  -F "file=@report.xlsx"

# 벡터 검색
curl -X POST http://localhost:8000/api/v1/processing/search \
  -H "Content-Type: application/json" \
  -d '{"query": "매출 실적 분석", "limit": 5}'

# 문서 목록 (indexed 상태만)
curl "http://localhost:8000/api/v1/documents?status=indexed&limit=10"

# 문서 삭제
curl -X DELETE http://localhost:8000/api/v1/documents/42
```

---

## 자동 동기화 (매일 02:00)

Celery Beat가 `DOC_WATCH_DIR`을 스캔하여 변경 사항을 자동 처리합니다.

| 변경 유형 | 감지 방식 | 처리 |
|----------|----------|------|
| **새 파일** | SHA-256 해시가 DB에 없음 | 전체 인제스트 |
| **수정된 파일** | 같은 경로, 다른 해시 | 기존 삭제 후 재인제스트 |
| **삭제된 파일** | DB에 있지만 디스크에 없음 | DB + Qdrant에서 제거 |

```ini
# .env에서 동기화 시각 변경
SYNC_CRON_HOUR=2
SYNC_CRON_MINUTE=0
```

---

## 지원 파일 형식 & 파서 상세

| 형식 | 확장자 | 파서 | 텍스트 | 표 | 이미지 | 비고 |
|------|--------|------|:------:|:--:|:------:|------|
| PDF | `.pdf` | MinerU v2.x | O | O | O | 다단 레이아웃, 수식 지원 |
| Word | `.docx` | python-docx | O | O | O (OCR) | 문서 순서 보존, 내장 이미지 MinerU OCR |
| Excel | `.xlsx`, `.xls` | openpyxl | O | O | - | 시트별 처리, 병합 셀 지원 |
| PowerPoint | `.pptx` | python-pptx | O | O | O (OCR) | 슬라이드별 처리, 이미지 MinerU OCR |
| 이미지 | `.png`, `.jpg`, `.tif` | MinerU OCR | O | - | - | 한국어/영어 OCR |

### 파서 처리 방식

**PDF** (`pdf_parser.py`)
- MinerU v2.x Python API 우선 → CLI fallback
- 출력: Markdown (표, 수식, 레이아웃 보존)
- 백엔드: `pipeline`(CPU) / `hybrid-auto-engine`(GPU)

**DOCX** (`docx_parser.py`)
- 문서 body 요소를 **순서대로** 처리 (paragraph → table → image 혼재)
- 표: 마크다운 테이블로 변환
- 이미지: 내장 이미지를 추출 → MinerU OCR로 텍스트 변환
- 셀 병합, 중첩 표 처리

**PPTX** (`pptx_parser.py`)
- 슬라이드별 처리 (텍스트 프레임 + 표 + 이미지)
- 이미지: shape에서 blob 추출 → MinerU OCR
- 그룹 shape 내부 탐색

**XLSX** (`xlsx_parser.py`)
- 시트별 처리, 각 시트를 `## Sheet: {이름}` 헤더로 구분
- 빈 행 스킵, 값만 추출 (`data_only=True`)

### MinerU 백엔드 선택

| 백엔드 | 정확도 | 요구사항 | 용도 |
|--------|--------|----------|------|
| `pipeline` | ~82+ | CPU, RAM 8GB+ | Mac 개발, CPU 서버 |
| `hybrid-auto-engine` | ~90+ | GPU VRAM 10GB+ | 운영 서버 (권장) |
| `vlm-auto-engine` | ~90+ | GPU VRAM 8GB+ | GPU 서버 |

---

## 프로젝트 구조

```
llm_again/
├── app/
│   ├── config.py              # 환경변수 설정 (Pydantic)
│   ├── main.py                # CLI (ingest, sync, status)
│   ├── api/
│   │   ├── main.py            # FastAPI 앱
│   │   └── routes/
│   │       ├── health.py      # 헬스체크
│   │       ├── documents.py   # 문서 CRUD + 동기화
│   │       └── processing.py  # 파싱/청킹/임베딩/검색 API
│   ├── db/
│   │   ├── init_schema.sql    # PostgreSQL DDL
│   │   ├── models.py          # SQLAlchemy ORM
│   │   ├── postgres.py        # DB 연결
│   │   └── qdrant.py          # 벡터 DB 관리
│   ├── parsers/
│   │   ├── base.py            # 파서 인터페이스
│   │   ├── pdf_parser.py      # MinerU PDF
│   │   ├── image_parser.py    # MinerU OCR
│   │   ├── docx_parser.py     # Word
│   │   ├── xlsx_parser.py     # Excel
│   │   └── pptx_parser.py     # PowerPoint
│   ├── processing/
│   │   ├── chunker.py         # 토큰 기반 청킹 (512 tokens, 50 overlap)
│   │   └── embedder.py        # E5 임베딩 ("passage:"/"query:" prefix)
│   ├── pipeline/
│   │   ├── ingest.py          # 인제스트 파이프라인
│   │   ├── scanner.py         # 파일 스캔 (glob, 확장자 필터)
│   │   └── sync.py            # 변경 감지 + 동기화
│   └── tasks/
│       ├── celery_app.py      # Celery 설정 + beat schedule
│       ├── ingest_tasks.py    # 비동기 인제스트
│       └── sync_tasks.py      # 스케줄 동기화
├── docker-compose.yml         # 전체 서비스 정의
├── Dockerfile.worker          # API + Worker 이미지
├── Makefile                   # 편의 명령어
├── requirements.txt           # Python 의존성
└── .env.example               # 환경변수 템플릿
```

---

## Makefile 명령어

| 명령어 | 설명 |
|--------|------|
| `make up` | 전체 서비스 시작 |
| `make down` | 서비스 중지 |
| `make build` | Docker 이미지 빌드 |
| `make init-db` | DB 스키마 재초기화 |
| `make scan` | 처리 가능한 파일 목록 조회 |
| `make scan-pdf` | PDF 파일만 조회 |
| `make scan-ingest` | 스캔 + 전체 인제스트 |
| `make ingest` | 전체 문서 인제스트 |
| `make ingest-file FILE=<path>` | 단일 파일 인제스트 |
| `make sync` | 변경 감지 동기화 |
| `make status` | 문서 처리 현황 |
| `make logs` | API + Worker 로그 |
| `make logs-api` | API 로그만 |
| `make logs-worker` | Worker 로그만 |
| `make ps` | 컨테이너 상태 |
| `make clean` | 전체 초기화 (볼륨 삭제) |

---

## 트러블슈팅

### MinerU 모델 다운로드 실패
```bash
docker compose exec celery-worker bash
python -c "from mineru.demo.demo import parse_doc; print('OK')"
```

### 임베딩 모델 로딩 느림 (첫 실행)
첫 실행 시 ~2.2GB 다운로드 필요. `hf_cache` 볼륨에 캐시됨.
```bash
make logs-worker
```

### PostgreSQL 연결 실패
```bash
docker compose logs postgres
make init-db
```

### Qdrant 확인
```bash
# 대시보드: http://localhost:6333/dashboard
curl http://localhost:6333/collections/documents
```

### Mac 메모리 부족
Docker Desktop → Settings → Resources → Memory → 8GB 이상

---

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DOC_WATCH_DIR` | `/data/documents` | 문서 감시 폴더 |
| `POSTGRES_HOST` | `postgres` | PostgreSQL 호스트 |
| `POSTGRES_PORT` | `5432` | PostgreSQL 포트 |
| `POSTGRES_DB` | `rag_system` | 데이터베이스명 |
| `POSTGRES_USER` | `admin` | DB 사용자 |
| `POSTGRES_PASSWORD` | `changeme` | DB 비밀번호 |
| `QDRANT_HOST` | `qdrant` | Qdrant 호스트 |
| `QDRANT_PORT` | `6333` | Qdrant 포트 |
| `QDRANT_COLLECTION` | `documents` | Qdrant 컬렉션명 |
| `EMBED_MODEL` | `intfloat/multilingual-e5-large` | 임베딩 모델 |
| `EMBED_DEVICE` | `cpu` | 디바이스 (cpu/cuda/mps) |
| `EMBED_BATCH_SIZE` | `32` | 배치 크기 |
| `MINERU_BACKEND` | `pipeline` | MinerU 백엔드 |
| `MINERU_LANG` | `korean` | OCR 언어 |
| `API_HOST` | `0.0.0.0` | FastAPI 호스트 |
| `API_PORT` | `8000` | FastAPI 포트 |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Celery 브로커 |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/1` | Celery 결과 |
| `SYNC_CRON_HOUR` | `2` | 동기화 시각 (시) |
| `SYNC_CRON_MINUTE` | `0` | 동기화 시각 (분) |
| `HF_TOKEN` | - | HuggingFace 토큰 |
