# Multimodal RAG On-Prem Execution Plan

**작성일:** 2026-03-17  
**프로젝트:** On-Premise Multimodal RAG Assistant  
**기준 레포:** `llm_again/`

---

## 1. 목표 정의

이 프로젝트의 목표는 사내 문서 기반 AI 어시스턴트를 넘어, 다음 조건을 만족하는 **멀티모달 RAG 제품**을 구축하는 것이다.

- 업무 영역: 신약 연구개발, 비즈니스 디벨롭먼트, 백오피스
- 문서 언어: 한국어 중심, 영어 혼합
- 주요 포맷: PDF, XLSX/XLS, DOCX, PPTX
- 문서 내용: 본문 텍스트, 표, 차트, 이미지, 스캔 문서, 혼합 레이아웃
- 배포 방식: 완전 온프레미스
- 운영 목표: 보안, 감사 추적, 검색 정확도, 응답 근거성, 운영 가능성

핵심 성공 조건은 다음과 같다.

1. 질문에 대해 텍스트뿐 아니라 표/이미지/차트가 포함된 문서에서도 근거를 회수할 수 있어야 한다.
2. 한국어 질의와 한국어 문서 검색 품질이 안정적이어야 한다.
3. 부서/폴더/권한 기반 접근 제어가 검색 단계에서 강제되어야 한다.
4. 운영자가 문서 처리 상태, 실패 원인, 모델/검색 설정을 통제할 수 있어야 한다.
5. 제품 관점에서 “챗봇 데모”가 아니라 “업무용 지식 시스템”으로 확장 가능해야 한다.

---

## 2. 제품 관점 핵심 유즈케이스

### 2.1 신약 연구개발

- 실험 계획서, 리포트, 프로토콜, 분석 결과에서 근거 기반 답변
- 타깃, 적응증, 바이오마커, 실험 조건, 통계 결과 검색
- 표/그래프/이미지 캡션과 본문 간 연계 회수
- 동일 개념의 한영 표기 혼용 대응

### 2.2 비즈니스 디벨롭먼트

- 딜 구조, 마일스톤, 지역권, 계약 조건, 회사/자산 비교 검색
- 기업명, 파이프라인명, 코드명, 금액/비율 등 exact match 중심 질의
- PPT/Excel 기반 요약 자료 회수

### 2.3 백오피스

- 정책, 프로세스, 양식, 규정 문서 검색
- 짧은 한글 키워드, 표 헤더, 문서 제목 기반 질의
- 최신 버전 우선 회수, 폐기/실패 문서 제외

---

## 3. 현재 레포 상태 진단

현재 레포는 **텍스트 중심 RAG 플랫폼의 골격**은 갖추고 있으나, 멀티모달 RAG 제품으로는 아직 부족하다.

### 3.1 이미 갖춘 기반

- FastAPI 기반 serving/pipeline/sync 분리
- PostgreSQL + pgvector + tsvector 기반 검색 구조
- Reranker, vLLM, JWT, 세션/채팅 저장
- MinerU 연동을 통한 PDF/이미지 OCR 진입점
- 문서/채팅/로그/운영용 DB 스키마

### 3.2 현재 핵심 한계

1. **멀티모달 인덱싱 부재**
   - 이미지, 차트, 표가 retrieval unit으로 저장되지 않음
   - `doc_image` 스키마는 있지만 실제 인덱싱 파이프라인에서 거의 활용되지 않음

2. **한국어 sparse 검색 취약**
   - PostgreSQL `simple` 토크나이저 기반
   - 형태소 분석, 사용자 사전, 동의어, 복합명사 분해 전략 없음

3. **그래프 계층 불완전**
   - GraphRAG 저장/조회 경로가 실질적으로 미완성
   - 규칙 기반 NER만으로는 도메인 엔터티 품질이 제한적

4. **문서 구조 보존 부족**
   - 표, 슬라이드, 캡션, 섹션, 페이지, 시트 구조를 retrieval에 충분히 반영하지 않음

5. **운영/품질 기준 부재**
   - 평가셋, KPI, 오프라인 검색 평가, 회귀 테스트 기준 부재
   - “정확해졌는지”를 판단할 기준이 없음

6. **문서와 구현 정합성 이슈**
   - 일부 README와 실제 코드/설정/경로가 불일치
   - 제품 수행 전에 실행 신뢰성부터 높여야 함

---

## 4. 목표 아키텍처

멀티모달 RAG를 위해 문서를 단순 텍스트가 아니라 **여러 retrieval object의 집합**으로 다뤄야 한다.

### 4.1 문서 단위가 아니라 객체 단위 인덱싱

각 문서를 아래 객체들로 분해한다.

- `text_block`: 문단, 섹션, 슬라이드 텍스트
- `table_block`: 표 전체, 표 제목, 시트 영역, 표 요약
- `image_block`: 이미지, 도표, figure, chart, 캡처
- `caption_block`: 이미지/표 캡션
- `layout_block`: 페이지/슬라이드/시트 메타데이터

각 객체에는 다음 메타데이터를 부여한다.

- `doc_id`
- `page_number` 또는 `sheet_name` 또는 `slide_number`
- `block_type`
- `section_path`
- `language`
- `bbox` 또는 위치 정보
- `parent_block_id`
- `source_text`
- `normalized_text`
- `keywords`

### 4.2 Retrieval 전략

질의 처리 시 아래를 병렬 사용한다.

1. Dense retrieval
2. Sparse retrieval
3. Table-aware retrieval
4. Image/caption retrieval
5. Entity/graph expansion
6. Metadata filtering

이후 RRF 또는 가중 fusion으로 합치고, cross-encoder re-rank를 수행한다.

### 4.3 Answer assembly 전략

최종 컨텍스트는 다음 조합으로 구성한다.

- 본문 근거 청크
- 표 요약 + 표 원문 일부
- 이미지/차트 설명
- 캡션/헤더
- 관련 엔터티/문서 연결 관계
- 권한/최신성 필터

---

## 5. 한국어/영어 혼합 대응 전략

### 5.1 결론

한국어 형태소 분석기 없이 시작은 가능하지만, 본 프로젝트 목표 기준으로는 **도입이 필요하다**.

### 5.2 적용 원칙

형태소 분석기는 생성 단계가 아니라 **인덱싱/검색 단계**에 적용한다.

적용 범위:

- sparse 검색용 정규화 토큰 생성
- 한국어 복합명사/조사 처리
- 도메인 사용자 사전 추가
- 한영 혼용 질의 확장

### 5.3 권장 방식

1. `Mecab-ko` 또는 동급 한국어 형태소 분석 도입
2. 신약/BD/백오피스 도메인 사전 구축
3. synonym dictionary 운영
4. 영문 약어-한글명 매핑 테이블 추가

예시:

- `계약금` ↔ `upfront`
- `마일스톤` ↔ `milestone`
- `비임상` ↔ `preclinical`
- `유효성` ↔ `efficacy`

---

## 6. 반드시 추가해야 할 데이터 모델

현재 스키마를 확장해 아래 테이블 또는 동등 구조를 추가한다.

- `doc_block`
  - 모든 retrieval object의 공통 저장소
- `doc_table`
  - 표 구조, 헤더, 행/열 정보
- `doc_caption`
  - figure/table caption
- `doc_keyword`
  - 형태소/사전 기반 키워드
- `doc_block_embedding`
  - block별 dense embedding
- `entity_alias`
  - 한영/약어/동의어 매핑
- `retrieval_eval_set`
  - 오프라인 평가용 질문/정답
- `retrieval_eval_result`
  - 평가 결과 저장

`doc_chunk`를 유지하더라도, 장기적으로는 `doc_block` 중심으로 재편하는 것이 바람직하다.

---

## 7. 단계별 실행 계획

## Phase 0. Stabilization

목표: 현재 레포를 “신뢰 가능한 실행 기반”으로 정리

### 작업

- README/compose/env/code 정합성 수정
- sync → pipeline 연결 오류 수정
- GraphRAG 저장 경로 복구
- 실패 로그/운영 로그 정합성 수정
- 로컬 개발 경로와 Docker 경로 정리
- 최소 smoke test 추가

### 완료 기준

- 문서 동기화 후 pipeline 자동 호출 성공
- 문서 1건 처리 → 검색 가능 → 채팅 응답까지 end-to-end 성공
- 실패 시 dashboard/admin에서 오류 확인 가능

## Phase 1. Korean + Hybrid Retrieval Upgrade

목표: 한글/영문 혼합 검색 품질 개선

### 작업

- 형태소 분석기 도입
- sparse 검색용 정규화 컬럼/인덱스 추가
- 도메인 사용자 사전 설계
- 질의 expansion 레이어 추가
- exact match boost 추가

### 완료 기준

- 한글 단일 키워드/복합명사 질의 recall 개선
- 영문 약어/한글 표현 간 검색 연결 가능

## Phase 2. Multimodal Parsing and Block Indexing

목표: 표/이미지/차트/슬라이드 구조를 retrieval 대상으로 승격

### 작업

- MinerU 결과 구조화 저장
- text/table/image/caption block 분리
- PPTX/Excel 전용 구조 파서 보강
- 이미지 요약 또는 vision caption 단계 추가
- block 단위 embedding + metadata 저장

### 완료 기준

- 표 질문 시 본문 대신 표가 근거로 회수됨
- 슬라이드/시트/페이지 단위 출처 인용 가능
- 차트/이미지 관련 설명도 retrieval 가능

## Phase 3. Fusion Retrieval and Reranking

목표: 멀티신호 검색을 제품 수준으로 고도화

### 작업

- dense/sparse/table/image fusion
- block type별 retrieval budget
- query intent classification
- rerank features 확장
- 최신성/권한/문서 상태 가중치 적용

### 완료 기준

- 사용 사례별 top-k 근거 품질이 안정화
- irrelevant chunk 비율 감소

## Phase 4. Graph and Entity Layer

목표: 신약/BD 도메인 엔터티 중심 탐색 강화

### 작업

- entity extraction 개선
- alias/entity canonicalization
- document-to-entity graph
- co-occurrence 대신 의미 있는 relation 확장
- query-time entity expansion

### 완료 기준

- 자산명/회사명/타깃명/적응증 기반 탐색 성능 향상

## Phase 5. Evaluation and Productization

목표: 품질 측정과 운영 체계 확립

### 작업

- 부서별 대표 질문셋 구축
- retrieval/answer 평가 파이프라인 구축
- admin 품질 지표 화면 추가
- 피드백 루프 수집
- 배포/운영 runbook 작성

### 완료 기준

- 품질 회귀 여부를 자동으로 판단 가능
- 운영자가 모델/검색 변경 영향을 관찰 가능

---

## 8. 우선순위 원칙

다음 순서로 진행한다.

1. 실행 안정화
2. 한국어 검색 품질
3. 표/이미지 구조 인덱싱
4. fusion retrieval
5. graph/entity 고도화
6. 운영 평가 체계

즉, “GraphRAG를 먼저 화려하게”보다 “표를 잘 찾고 한글 검색이 잘 되는 것”이 선행이다.

---

## 9. 제품 KPI

### 검색 품질 KPI

- Top-5 retrieval hit rate
- citation precision
- table question success rate
- Korean keyword recall
- cross-lingual alias hit rate

### 사용자 KPI

- 첫 답변 유용성 비율
- 재질문 비율
- 문서 근거 클릭률
- 부서별 주간 활성 사용자

### 운영 KPI

- 문서 처리 성공률
- 평균 처리 시간
- 실패 유형 분포
- 검색 latency / generation latency

---

## 10. 바로 다음 스프린트 범위

다음 구현 스프린트는 아래 범위를 1차 목표로 한다.

### Sprint A: Foundation Fix

- sync/pipeline 경로 정합성 수정
- Graph 저장 경로 복구
- pipeline 실패 로그 보강
- README/설정 정리
- smoke test 추가

### Sprint B: Korean Retrieval Upgrade

- 형태소 분석 레이어 도입
- sparse 검색 구조 개편
- synonym/alias 테이블 설계

### Sprint C: Multimodal Block Model

- `doc_block` 계층 도입
- 표/이미지/캡션 block 저장
- retrieval/query path를 `doc_chunk` + `doc_block` 혼합으로 전환

---

## 11. 수행 원칙

이 프로젝트는 “한 번에 완성”이 아니라 아래 원칙으로 수행한다.

- 제품 목표와 코드 변경을 매 턴 연결한다.
- 각 단계마다 운영 가능한 상태를 만든다.
- 새 기능보다 먼저 관측 가능성과 실패 복구를 확보한다.
- README와 실제 구현을 항상 같이 맞춘다.
- 품질은 체감이 아니라 평가셋으로 검증한다.

---

## 12. 실행 선언

이 레포는 폐기할 상태는 아니다.  
다만 현재 상태 그대로는 멀티모달 RAG 제품을 성공시키기 어렵다.

따라서 본 프로젝트는 아래 방식으로 수행한다.

- **현재 레포를 기반으로 계속 진행**
- **Phase 0부터 순차적으로 안정화 및 고도화**
- **한글 검색 품질과 멀티모달 인덱싱을 핵심 축으로 재구성**
- **각 Phase 완료 시점마다 문서/코드/운영 기준을 함께 업데이트**

이 문서를 본 프로젝트의 기준 실행 문서로 사용한다.
