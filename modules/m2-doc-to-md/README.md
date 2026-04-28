# M2 Doc → Markdown

원본 문서(PDF/DOCX/XLSX/HWP/HWPX/PPTX)를 스캔해 마크다운으로 변환하고, M3에 청킹·임베딩 트리거를 보냅니다.

- **Port**: 8102 (호스트), 8000 (컨테이너 내부)
- **Run (host)**: `make run`
- **Run (Docker)**: `make docker-up` 또는 루트의 `make up`
- **Pipeline (Docker)**: `make docker-pipeline` (혹은 `docker-pipeline-full`)
- **Test**: `make test`

## 데이터 흐름

```
${DATA2_ROOT} (호스트, 보통 /data2/)            ← 원본 문서 디렉토리 (RO 마운트)
    ↓ scanner.py: 변경 감지 (mtime + sha256)
    ↓ 문서별 Redis 락 (m2:lock:{rel_path}, owner UUID, TTL)
    ↓ converter.py: kordoc CLI → Markdown body
                    + frontmatter 헤더 (L1 메타)
${DATA_ROOT}/markdown/{relative_path}.md       ← 마크다운 출력 (m3가 RO로 읽음)
    ↓ POST /chunk-embed { doc_id, markdown_path, source_hash } → m3
    ↓ 실패 시 DLQ (Redis list, 지수 백오프 재시도)
${DATA_ROOT}/state/.pipeline_state.json        ← 처리 상태 (atomic write)
${DATA_ROOT}/logs/m2/                          ← 일자별 로그
```

## L1 Frontmatter (m3가 파싱해 chunks.metadata에 저장)

```yaml
---
source_path: hr/policy/2024-vacation.pdf
source_hash: 8af3...d2e1
format: pdf
folder_path: hr/policy
filename: 2024-vacation.pdf
size_bytes: 41280
mtime: 2024-12-03T05:12:44+00:00
converted_at: 2026-04-28T10:00:00+00:00
---

# (마크다운 본문)
```

## 환경 변수

| 변수 | 컨테이너 기본 | 설명 |
|------|--------------|------|
| `M2_SOURCE_DIR` | `/data2` | 원본 문서 루트 (RO 마운트 권장) |
| `M2_OUTPUT_DIR` | `/data/markdown` | 마크다운 출력. m3와 공유 |
| `M2_STATE_DIR` | `/data/state` | `.pipeline_state.json` 디렉토리 (atomic write) |
| `M2_LOG_DIR` | `/data/logs` | 일자별 로그 파일 |
| `M3_API_URL` | `http://m3-chunk-embed:8000` | 다운스트림 |
| `REDIS_URL` | `redis://redis:6379/0` | 락 + DLQ |
| `KORDOC_BIN` | `kordoc` | 변환기 바이너리 (PATH에 있어야 함) |

호스트 dev에서 `make run`으로 실행 시에는 `M2_SOURCE_DIR=/path/to/docs` 등을 셸에서 export.

## 엔드포인트

```bash
# 점진적 변환 시작 (백그라운드 작업, job_id 반환)
curl -X POST http://localhost:8102/ingest/scan
# → {"job_id":"abc123...", "status":"queued"}

# 작업 상태
curl http://localhost:8102/ingest/status/abc123...
# → {"status":"running"|"done"|"error:..."}

# 헬스
curl http://localhost:8102/health
curl http://localhost:8102/ready
```

또는 CLI로:
```bash
make pipeline               # 호스트에서 1회 실행 (호스트 venv + 호스트 경로)
make pipeline-full          # 호스트, .pipeline_state.json 삭제 후 재실행
make docker-pipeline        # 컨테이너 안에서 1회 (마운트된 /data2 사용) ← 권장
make docker-pipeline-full   # 컨테이너 안에서 state 클리어 후 재실행
```

## 실패 처리

- 변환 실패: `dlq.push({type:"convert", rel, retry_count, next_retry})` → 다음 실행에서 백오프 후 재시도 (최대 3회)
- M3 트리거 실패: `dlq.push({type:"m3_trigger", doc_id, md_path})` → 동일 패턴
- 락 타임아웃 / 동시 실행 충돌: skip 후 다음 회차로 미룸

## 운영 노트

- `kordoc`은 PDF/DOCX/XLSX/HWP/HWPX 변환. PPTX는 python-pptx로 fallback (status: `ok-pptx-fallback`).
- 동일 cron 노드 다중 인스턴스 지원: per-document Redis 락으로 race-free.
- 변환 timeout 5분 (kordoc 단일 호출당). 큰 PDF는 수동 분할 권장.
