# Production Readiness — Improvement Backlog

현 코드 베이스 production readiness 평가 (7.3/10) 중 10점 미달 영역의 개선 항목.
각 항목: Why / What / How / Effort.

## 점수 현황

| 영역 | 현 | 목표 | 격차 |
|------|----|------|------|
| 코드 품질 | 7 | 10 | 3 |
| M3/M4 기능 완성도 | 7 | 10 | 3 |
| CI/CD | 8 | 10 | 2 |
| Infra | 7 | 10 | 3 |
| 관측성 | 7 | 10 | 3 |
| 부하 검증 | 8 | 10 | 2 |

---

## 1. 코드 품질 (7→10)

**1.1 mypy strict 모드**
- Why: `--no-strict-optional --ignore-missing-imports` — 타입 안정성 제한적
- What: 모든 백엔드 모듈 strict mypy 통과
- How: `pyproject.toml [tool.mypy]` 단계적 강화 (`disallow_untyped_defs` → stubs → `strict=True`)
- Effort: 2주

**1.2 테스트 커버리지 80%**
- Why: 단위 테스트 163개, 커버리지 미측정. M6/M7-fe 0%.
- What: 모든 모듈 80% 라인 커버리지 + 핵심 분기 100%
- How: `pytest --cov=app --cov-fail-under=80` CI 의무화; frontend `vitest --coverage` + Playwright
- Effort: 3주

**1.3 OpenTelemetry 분산 추적**
- Why: trace context 없음 — M5→M3→pgvector 연쇄 호출 디버깅 불가
- What: 모든 백엔드 OTel auto-instrumentation + Tempo backend
- How: `opentelemetry-instrumentation-fastapi/asyncpg/httpx` 추가, `traceparent` 헤더 전파
- Effort: 1주

**1.4 Frontend 단위 테스트**
- Why: M7-fe 0%, M6 부분
- What: 모든 컴포넌트 단위 테스트 + 8개 e2e 시나리오
- How: vitest + @testing-library/react + Playwright
- Effort: 2주

---

## 2. M3/M4 기능 완성도 (7→10)

**2.1 임베딩 멀티 스킴**
- Why: BAAI/bge-m3 단일 — 한/영 혼합 정확도 한계
- What: 환경변수 모델 선택 + `chunks.embedding_model` 컬럼
- How: `EMBED_MODEL` env (`bge-m3`/`e5-large`/`nomic-embed`), re-embedding migration job
- Effort: 1주

**2.2 Reranker 통합**
- Why: RRF만 — top-3 정확도 80% 수준 추정
- What: cross-encoder reranker로 hybrid 결과 재정렬
- How: `RERANKER_MODEL` env, `reranker.predict([(query, chunk)])` 후 재정렬, `RERANKER_ENABLED=0` 옵션
- Effort: 3-5일

**2.3 Neo4j Graph RAG**
- Why: 벡터 검색만 — 엔티티 관계 미활용
- What: NER entity 추출 + Neo4j 저장 + Cypher 검색
- How: `(Doc)-[:CONTAINS]->(Chunk)-[:MENTIONS]->(Entity)`, M4 1-hop 이웃 청크 추가
- Effort: 2-3주

**2.4 vLLM 클러스터**
- Why: 단일 vLLM URL — 장애/스케일 한계
- What: URL 리스트 + weighted round-robin load balancer
- How: `VLLM_URLS=url1,url2,url3` env, httpx 클라이언트에 WRR
- Effort: 3일

**2.5 의미 기반 답변 캐싱**
- Why: 유사 질의 반복 → vLLM 토큰 낭비
- What: query embedding 기반 캐시 (similarity > 0.95)
- How: pgvector/Redis에 `(query_embedding, answer)` 저장, TTL 1h
- Effort: 2-3일

---

## 3. CI/CD (8→10)

**3.1 Canary 배포**
- Why: main push → 즉시 배포 — 회귀 시 전체 영향
- What: 5% → 25% → 100% 점진 배포
- How: Argo Rollouts metric-based progressive rollout, GitHub Actions CLI 호출
- Effort: 1주

**3.2 Mutation testing**
- Why: 라인 커버리지만으로 테스트 품질 측정 불완전
- What: mutation score 측정
- How: `make mutation-test` (mutmut + Stryker), CI nightly 실행
- Effort: 3일

---

## 4. Infra (7→10)

**4.1 Kubernetes 매니페스트**
- Why: docker-compose만 — k8s 배포 불가
- What: Helm chart 또는 Kustomize manifests
- How: `infra/helm/<module>/` 작성, ArgoCD 연동
- Effort: 2주

**4.2 Vault/External Secrets**
- Why: docker secrets — 회전 자동화 없음
- What: HashiCorp Vault 또는 AWS Secrets Manager + 90일 자동 회전
- How: External Secrets Operator (k8s) 설치 후 SecretStore 설정
- Effort: 1주

**4.3 백업 오프사이트 (S3)**
- Why: `backups/` 로컬만 — 호스트 손실 시 복구 불가
- What: S3 cross-region replication
- How: `backup.sh` 끝에 `aws s3 sync backups/ s3://rag-backups/`, IAM + lifecycle 정책
- Effort: 2일

**4.4 복구 drill (월 1회)**
- Why: 백업 복구 가능 여부 미검증
- What: 자동 복구 + 무결성 검증 (row count, checksum)
- How: `monthly-restore-drill` scheduled task, 별도 namespace 복구 후 검증
- Effort: 1주

---

## 5. 관측성 (7→10)

**5.1 SLO/SLI + 에러 버짓**
- Why: 알림 임계값만 있고 SLO 없음
- What: 가용성 99.9% / p95 지연 < 2s (200qpm), 버짓 소진 시 배포 freeze
- How: Prometheus recording rules + Grafana SLO 대시보드
- Effort: 1주

**5.2 RUM (Real User Monitoring)**
- Why: 백엔드 메트릭만 — 사용자 체감 지연 미측정
- What: Web Vitals 수집 + Grafana 대시보드
- How: `web-vitals` npm + Grafana Faro collector
- Effort: 3-5일

**5.3 trace ↔ 로그 correlation**
- Why: 로그에 trace_id 없어 디버깅 어려움
- What: 모든 로그에 trace_id, span_id 자동 주입
- How: OTel SDK + structlog processor (1.3과 병행)
- Effort: 2-3일

---

## 6. 부하 검증 (8→10)

**6.1 Chaos engineering**
- Why: 부하 테스트만 — 부분 장애 시나리오 미검증
- What: 장애 주입 시나리오: postgres 30s 다운, redis 50% 패킷 드롭, m3 OOM kill
- How: Litmus Chaos 또는 chaos-monkey 스크립트
- Effort: 1-2주

**6.2 nightly 부하 테스트 + 회귀 검증**
- Why: 수동 실행 — 회귀 감지 불가
- What: p95 > 이전 대비 110% → CI fail
- How: GitHub Actions schedule, 결과 S3 저장, jq로 비교
- Effort: 3일

---

## 우선순위 매트릭스

| 항목 | Impact | Effort | 우선순위 |
|------|--------|--------|----------|
| 1.3 OTel 분산 추적 | 高 | 1주 | P0 |
| 5.3 trace ↔ 로그 | 高 | 3일 | P0 |
| 4.3 백업 오프사이트 | 高 | 2일 | P0 |
| 1.2 커버리지 80% | 高 | 3주 | P1 |
| 2.2 Reranker | 中 | 3-5일 | P1 |
| 4.4 복구 drill | 高 | 1주 | P1 |
| 2.5 답변 캐싱 | 中 | 3일 | P1 |
| 5.1 SLO | 中 | 1주 | P1 |
| 1.4 Frontend 테스트 | 中 | 2주 | P2 |
| 3.1 Canary | 高 | 1주 | P2 |
| 4.1 K8s manifests | 高 | 2주 | P2 |
| 4.2 Vault | 中 | 1주 | P2 |
| 6.2 부하 nightly | 中 | 3일 | P2 |
| 1.1 mypy strict | 中 | 2주 | P3 |
| 2.1 멀티 임베딩 | 中 | 1주 | P3 |
| 2.3 Graph RAG | 高 | 2-3주 | P3 |
| 2.4 vLLM 클러스터 | 中 | 3일 | P3 |
| 5.2 RUM | 中 | 3-5일 | P3 |
| 6.1 Chaos | 中 | 1-2주 | P3 |
| 3.2 Mutation testing | 低 | 3일 | P4 |

## 권고 일정

| Sprint | 기간 | 항목 |
|--------|------|------|
| 1 | 2주 | P0 — OTel + trace 로그 + 백업 오프사이트 |
| 2 | 2주 | P1 — Reranker, 답변 캐싱, SLO, 복구 drill |
| 3 | 3주 | P1 — 커버리지 80% |
| 4-5 | 4주 | P2 — Frontend 테스트, Canary, K8s, Vault, 부하 nightly |
| 6+ | 계속 | P3/P4 — 점진 적용 |
