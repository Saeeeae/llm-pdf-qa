# CHECK

Ubuntu 24.04 + Intel Xeon + NVIDIA L40S 기준 Phase 0~2 재검증 체크리스트입니다.

## 1. Preflight

- `.env`가 최신 값인지 확인
- `DOC_WATCH_DIR`, `IMAGE_STORE_DIR`, `MINERU_MODEL_DIR`, `MINERU_OUTPUT_DIR`, `VLLM_BASE_URL`, `VLLM_MODEL_NAME`, `VLLM_MODEL`, `VLLM_SERVED_MODEL_NAME` 확인
- `NEXT_PUBLIC_API_URL`는 비워 두거나 실제 서버 주소로 설정

```bash
cd /Users/sae/Desktop/llm_again
cp -n .env.example .env
grep -E '^(POSTGRES_|NEO4J_|JWT_|DOC_WATCH_DIR|IMAGE_STORE_DIR|MINERU_|VLLM_|NEXT_PUBLIC_API_URL|PREFER_ENV_LLM_CONFIG)' .env
```

정상 기대값:
- `MINERU_OUTPUT_DIR=/data/images/mineru_output`
- `IMAGE_STORE_DIR=/data/images`
- `NEXT_PUBLIC_API_URL=` 또는 `http://<server-ip>:8002`

## 2. Clean Start

```bash
docker compose down
docker compose build --no-cache frontend serving-api pipeline-api pipeline-worker mineru-api
docker compose --profile gpu up -d postgres redis neo4j vllm-server mineru-api pipeline-api pipeline-worker serving-api sync-scheduler frontend
docker compose ps
```

정상 기대값:
- `postgres`, `redis`, `neo4j`, `vllm-server`, `mineru-api`, `pipeline-api`, `pipeline-worker`, `serving-api`, `frontend`, `sync-scheduler`가 `Up`

문제 신호:
- Docker build가 timezone/region prompt에서 멈추면 이미지 캐시 또는 Dockerfile 반영 여부 재확인
- `mineru-api` 또는 `vllm-server`가 바로 재시작되면 GPU/CUDA 로그 확인

## 3. Health Check

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:9000/health
```

정상 기대값:
- 모두 `200 OK`

## 4. DB Schema Check

```bash
docker compose exec -T postgres psql -U admin -d rag_system -c "\dt"
```

```bash
docker compose exec -T postgres psql -U admin -d rag_system -c "
select count(*) from sync_logs;
select count(*) from document;
select count(*) from doc_block;
select count(*) from doc_chunk;
select count(*) from doc_image;
select count(*) from entity_alias;
select count(*) from doc_keyword;
"
```

정상 기대값:
- `sync_logs`, `document`, `doc_block`, `doc_chunk`, `doc_image`, `entity_alias`, `doc_keyword` 테이블 존재
- 앱 최초 기동 직후 `entity_alias`는 0보다 커야 함

문제 신호:
- `sync_logs does not exist`면 오래된 볼륨일 가능성이 큼
- 필요한 경우 `make db-reset` 후 재기동

## 5. Frontend / Auth Check

브라우저 확인:
- `http://<server-ip>:3000/login`
- `http://<server-ip>:3000`
- `http://<server-ip>:3000/admin`

정상 기대값:
- 로그인 페이지가 `not found` 없이 열림
- admin 계정 로그인 시 `/admin`
- 일반 user 로그인 시 `/chat`
- 로그인 후 무한 로딩 없이 진입

관리자 계정 생성/갱신:

```bash
docker compose exec -T serving-api python3 - <<'PY'
from rag_serving.api.auth.password import hash_password
from shared.models.orm import User
from shared.db import get_session

email = "admin@company.com"
password = "change_me_admin_password"

with get_session() as s:
    user = s.query(User).filter(User.email == email).first()
    if not user:
        s.add(User(
            pwd=hash_password(password),
            usr_name="관리자",
            email=email,
            dept_id=1,
            role_id=1,
        ))
        print("created", email)
    else:
        user.pwd = hash_password(password)
        user.is_active = True
        user.role_id = 1
        print("updated", email)
PY
```

## 6. Sync / Pipeline Check

샘플 문서가 `DOC_WATCH_DIR` 아래에 있어야 합니다.

```bash
curl -X POST http://localhost:8001/pipeline/trigger/full
```

```bash
docker compose exec -T postgres psql -U admin -d rag_system -c "
select d.doc_id, d.file_name, d.status, d.error_msg,
       count(distinct b.block_id) as block_count,
       count(distinct c.chunk_id) as chunk_count,
       count(distinct i.image_id) as image_count
from document d
left join doc_block b on b.doc_id = d.doc_id
left join doc_chunk c on c.doc_id = d.doc_id
left join doc_image i on i.doc_id = d.doc_id
group by d.doc_id, d.file_name, d.status, d.error_msg
order by d.doc_id desc
limit 20;
"
```

```bash
docker compose exec -T postgres psql -U admin -d rag_system -c "
select id, doc_id, stage, status, started_at, finished_at, error_message
from pipeline_logs
order by id desc
limit 30;
"
```

정상 기대값:
- 문서 상태가 `indexed`
- `doc_block`, `doc_chunk`가 함께 증가
- PDF/image 문서는 `doc_image`도 증가
- 실패 시 `pipeline_logs.error_message`에 원인 표시

문제 신호:
- `Document <id> not found`가 반복되면 stale task 의심
- `processing`에 오래 머물면 worker 또는 모델 호출 로그 확인

## 7. MinerU Check

PDF 또는 이미지 파일 1건으로 직접 확인:

```bash
curl -X POST http://localhost:9000/parse \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "/data/documents/YOUR_SAMPLE.pdf",
    "method": "auto",
    "backend": "hybrid-auto-engine",
    "lang": "korean"
  }'
```

로그/결과 확인:

```bash
docker compose logs --tail=300 mineru-api
```

```bash
docker compose exec -T mineru-api sh -lc 'find /data/images/mineru_output -maxdepth 6 \( -name "*.md" -o -name "*.json" -o -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" \) | sort | tail -n 200'
```

```bash
docker compose exec -T mineru-api sh -lc 'ls -R /data/images/mineru_output | tail -n 200'
```

정상 기대값:
- `/parse` 응답에 `markdown`, `pages`, `metadata.mineru_output_dir`
- `MINERU_OUTPUT_DIR` 아래에 `.md`와 이미지 파일 생성

문제 신호:
- `No markdown output from MinerU`면 output 구조 mismatch 또는 MinerU 내부 파싱 실패 가능성
- `결과값을 읽을 수 없다` 계열이면 `.md` 파일 생성 여부와 실제 output 경로부터 확인

## 8. Admin Check

브라우저에서:
- `http://<server-ip>:3000/admin`

정상 기대값:
- 문서 목록/상세가 열림
- `block_count`, `chunk_count`, `image_count`가 표시
- 문서 상세 드로어에서 recent blocks 표시
- 이미지가 있는 문서는 preview가 보임

추가 확인:
- 최근 실패/동기화/모듈 상태 카드가 비정상 없이 렌더링

## 9. Chat / Retrieval Check

권장 질의:
- `표로 EGFR 적응증 정리된 문서 보여줘`
- `슬라이드에서 milestone summary가 있는 페이지 찾아줘`
- `Sheet 기준으로 NSCLC 관련 값을 보여줘`

정상 기대값:
- 응답에 reference가 붙음
- reference 메타에 `block_id`, `block_type`, `page_number`, `sheet_name`, `slide_number`가 포함될 수 있음
- admin/user 권한에 맞는 화면으로 진입

## 10. LLM Config / Env Check

```bash
docker compose exec -T postgres psql -U admin -d rag_system -c "
select config_id, provider, model_name, vllm_url, is_active
from llm_config
order by config_id;
"
```

`.env`에서 확인:
- `PREFER_ENV_LLM_CONFIG=true`
- `VLLM_BASE_URL`
- `VLLM_MODEL_NAME`

정상 기대값:
- 실제 런타임은 DB 값보다 `.env`의 `VLLM_BASE_URL`, `VLLM_MODEL_NAME` 우선 사용

## 11. Known Debug Order

문제가 생기면 아래 순서로 봅니다.

1. `docker compose ps`
2. `docker compose logs --tail=200 frontend serving-api pipeline-api pipeline-worker mineru-api vllm-server`
3. `curl http://localhost:8001/health && curl http://localhost:8002/health && curl http://localhost:9000/health`
4. DB에서 `document`, `pipeline_logs`, `doc_block`, `doc_chunk`, `doc_image`, `sync_logs` 확인
5. MinerU output 디렉토리와 `.md` 생성 여부 확인
6. `/admin`과 `/chat`에서 실제 reference 메타 확인

## 12. Phase 2 Complete Criteria

아래가 모두 만족되면 Phase 2는 실운영 검증 기준으로도 거의 닫힌 상태로 봅니다.

- frontend login/admin/chat 진입 정상
- sync 후 pipeline 재처리 정상
- `document`, `doc_block`, `doc_chunk`, `doc_image` 적재 정상
- MinerU PDF/image parse 결과에서 markdown/image 산출 정상
- `/admin`에서 block/image preview 확인 가능
- chat 응답에 block-aware reference 포함
