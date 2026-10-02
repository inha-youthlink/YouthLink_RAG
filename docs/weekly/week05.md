# 5주차 작업 계획 (2026-09-29 ~ 10-04)

> 목표: **Naive RAG 한 사이클 완성**
> 설계 기준 문서: [design.md](../design.md)

---

## 1. 목표

`POST /internal/pipeline` 하나로 **프로필 + 질문**을 받으면
1. 벡터 유사도 top-k로 관련 정책을 찾아 **추천 목록**을 보여주고
2. 검색 근거로 **LLM 답변**을 생성해 반환한다

## 2. 범위

| 하는 것 | 하지 않는 것 |
|---|---|
| FastAPI 프로젝트 골격 | 질문 분석, 라우팅 (6주차) |
| 벡터 top-k 검색 (pgvector) | 채팅 저장, 대화 기록 (6주차) |
| 청크 → 정책 단위 묶기 | 프로필 기반 필터링 (규칙 확정 후) |
| 정책 메타데이터 조회 | Advanced RAG 기법 |
| 기본 프롬프트로 답변 생성 | pytest 테스트 (기능 완성 우선, 성능 평가는 RAG 평가 서버 담당) |
| trace 기록 | |

**전제**
- 정책 데이터와 청크·임베딩은 ETL 서버가 적재한다. 청킹이 끝나기 전에는 로컬 가짜 데이터로 확인한다 (8번)
- 프로필은 답변 생성 프롬프트에만 반영한다

---

## 3. 작업 단위

이슈 5개로 나눠 순서대로 진행한다. 각 이슈는 앞 이슈의 결과물을 사용한다.

| 순서 | 이슈 | 내용 | 확인 방법 |
|---|---|---|---|
| 1 | FastAPI 기본 설정 | 설정 객체, 앱 생성(lifespan 틀), `GET /health`, README 실행 방법 | 서버 실행 후 `/health`, `/docs` |
| 2 | RAG 기반 설정 | 의존성, OpenAI·DB 설정, `LLMClient`(`embed`, `chat`), 공용 스키마, `PipelineContext`, `PipelineDeps` | 실제 API로 `embed()` 1536차원, `chat()` 응답·토큰 확인 |
| 3 | 검색 | `Retriever` 인터페이스·벡터 구현·팩토리, 벡터 검색 쿼리, 정책 묶기, 정책 정보 조회 | 가짜 데이터로 관련 정책이 상위에 오는지 |
| 4 | 답변 생성 | `generate_v1.md` 프롬프트, `generator.py` | 근거 안에서만 답하는지, 마감 정책 표시 |
| 5 | 파이프라인 API | `default_rag` 핸들러, `runner.py`, `POST /internal/pipeline`, trace | 요청 → 추천 정책 + 답변 + trace 반환 |

## 4. 처리 흐름

```
POST /internal/pipeline  (profile + question)
  → api/internal.py           요청 검증 (PipelineInput)
  → pipeline/runner.py        PipelineContext 생성 → default_rag 호출
  → handlers/default_rag.py
      1. 질문 임베딩 + 벡터 top-k 청크 검색   retriever (VectorRetriever)
      2. 청크를 정책 단위로 묶기              grouping.py
      3. 정책 메타데이터 조회                 policy_repository
      4. 프롬프트 조립 + 답변 생성            generator.py → llm.chat()
  → PipelineOutput (answer, policies, trace)
```

## 5. API 명세 (`/internal/pipeline`)

RAG 평가 서버와의 계약이다. 이후에는 기본값 있는 선택 필드만 추가하고, 기존 필드의 이름 변경·삭제는 하지 않는다.

### 요청
```json
{
  "question": "월세 지원받을 수 있는 정책 있어?",
  "profile": {
    "age": 24,
    "region_code": "...",
    "marriage_status_code": "...",
    "annual_income": 20000000,
    "major_code": null,
    "job_code": "...",
    "school_code": "...",
    "special_target_code": null
  }
}
```
- `question`은 1글자 이상, `profile`은 생략 가능 (빈 프로필)
- `age`, `annual_income`은 0 이상. 검증 실패 시 422

### 응답
```json
{
  "answer": "...",
  "policies": [
    {
      "policy_no": "...",
      "policy_name": "청년월세 지원",
      "application_start_date": "2026-09-01",
      "application_end_date": "2026-09-30",
      "application_url": "...",
      "score": 0.82
    }
  ],
  "trace": {
    "retrieved_chunks": [{ "chunk_id": "...", "policy_no": "...", "chunk_type": "...", "score": 0.82 }],
    "prompt_version": "generate_v1",
    "embedding_model": "text-embedding-3-small",
    "chat_model": "gpt-6-luna",
    "latency_ms": { "...": 0 },
    "tokens": { "prompt": 1820, "completion": 310 }
  }
}
```
- 신청 기간이 없는 정책(상시 모집 등)은 날짜가 `null`
- `latency_ms` 세부 항목은 파이프라인 API 이슈에서 확정

---

## 6. 설계 결정

| 주제 | 결정 | 이유 |
|---|---|---|
| 답변 생성 모델 | `gpt-6-luna` (`CHAT_MODEL`로 변경 가능) | 근거 기반 정리 작업이라 소형 모델로 충분하고, 비용이 상위 모델의 약 1/20. 근거 외 답변이 나오면 `gpt-6.1-sol` 검토 |
| 임베딩 모델 | `text-embedding-3-small`, 1536차원 | ETL과 반드시 같아야 함 |
| OpenAI 호출 | SDK 3.x, 답변 생성은 Responses API, 호출은 `LLMClient`로 일원화 | 신규 프로젝트 권장 방식, 구조화 출력(6주차)과 연결 |
| DB 접근 | SQLAlchemy 2.1 async (`sqlalchemy[asyncio]`) + asyncpg, 읽기 쿼리는 SQL 직접 작성 | 2.1부터 greenlet이 기본 설치에서 빠짐. pgvector 연산자를 그대로 사용 |
| 설정 관리 | 필수 값(API 키, DB URL)만 기본값 없음, `.env`의 빈 값은 기본값 사용, `.env.example`은 필수/선택 섹션 | 필수 값 누락은 서버 시작 시 바로 발견, 선택 값은 키만 보이고 기본값 유지 |
| 자원 생성 | OpenAI 클라이언트, DB 엔진, 저장소, 검색기는 lifespan에서 한 번 생성 | 요청마다 연결 생성 방지, 잘못된 설정은 서버 시작 시 실패 |
| 검색 구조 | `Retriever` 인터페이스 + 팩토리 (`RETRIEVER=vector`) | 설정만 바꿔 기법 비교 가능. `policy_ids`는 1차 필터링 연결용으로 미리 유지 |
| 검색 쿼리 | 코사인 거리(`<=>`), `embedding_model` 조건 + `embedding IS NOT NULL` | 다른 모델 임베딩 혼입 방지, HNSW 조건부 인덱스 사용 |
| top-k 단위 | 청크 단위, 기본 10 | 1정책 1청크 방향이라 정책 단위와 차이가 작음. 추천 정책 수는 최대 k개 |
| 정책 묶기 | 대표 점수는 정책 내 최고 점수, 청크는 원문 순서 | 평균은 분할된 정책에 불리, 근거는 원문 순서가 자연스러움 |
| 답변 근거 | 청크 내용 + 정책 정보(정책명, 신청 기간, URL, 신청 방법, 제출 서류, 담당 기관) | ETL 청크에는 신청 기간과 링크가 없어 `policy` 테이블에서 보완 |
| 마감 표시 | 신청 상태(상시 모집/신청 가능/신청 예정/마감/정보 없음)는 코드에서 계산해 프롬프트에 전달. 상시 여부만 신청 기간 구분 코드(`0057002`)로 판단하고, 나머지는 신청 기간과 오늘 날짜를 비교. 날짜가 없으면 정보 없음 | LLM의 날짜 비교 오류 방지. API의 마감 코드는 갱신을 신뢰하기 어려움 |
| 프로필 반영 | 코드 값은 `common_code`에서 요청마다 필요한 코드만 조회해 이름 변환 후 프롬프트에 전달. 지역은 사전이 없어 제외 | LLM은 코드 의미를 모름. 시작 시 캐시하면 DB 없이 서버가 뜨지 않고 갱신 시 재시작 필요 |
| 프로필 필터링 | 이번 주 제외. 방향은 "확실히 불충족인 정책만 제외" | 잘못된 제외가 가장 큰 위험 ([design.md](../design.md) 10-2) |
| 테스트 | pytest 보류 | 기능 완성 우선, RAG·LLM 성능 평가는 평가 서버 담당 |
| 문서 관리 | `design.md`(항상 최신) + 주차 문서(주 끝에 결과를 정리하고 이후 수정하지 않음) | 결정 과정과 실험 기록을 남김 |

---

## 7. ETL 데이터 계약

**확정** (ETL `db/schema.sql` 기준)
- 임베딩: `text-embedding-3-small`, 1536차원, 코사인 거리
- 인덱스: HNSW (`vector_cosine_ops`), `WHERE embedding IS NOT NULL` 조건부
- 청크: 1정책 1청크, 길면 `[세부 내용]`을 문장 단위로 분할
- 청크 형식: `[정책] ... [나이] ... [학력] ... [소득 조건] ... [세부 내용] ...`

**확인할 것**
1. `chunk_type`에 들어가는 값과 의미
2. 분할된 청크에 `[정책] 정책명` 헤더가 반복되는지
3. 청킹·임베딩 적재 일정, 로컬 DB 준비 방법 (덤프 제공 또는 공용 DB)
4. `policy_region`에 행이 없을 때의 의미 (전국 / 정보 없음)
5. `chat_*` 테이블 생성·변경 주체 (현재 ETL `schema.sql`에 포함)

---

## 8. 확인 환경

ETL 청킹이 끝나기 전까지 로컬 DB에 가짜 데이터를 넣어 검색과 답변을 확인한다.

- 로컬 PostgreSQL + pgvector에 ETL `extensions.sql` → `schema.sql` → `common_code.sql` 실행
- 가짜 정책 25개: 일자리·주거·교육·금융·복지 각 5개, `policy_no`는 `TEST-` 접두어
  - 청크는 ETL 형식을 따르고, 2~3개 정책은 세부 내용을 길게 써서 여러 청크로 분할 (정책 묶기 확인용)
  - 신청 기간은 진행 중·마감·상시를 섞음 (마감 표시 확인용)
  - 청크 임베딩은 실제 `text-embedding-3-small`로 생성
- 적재 스크립트는 저장소에 포함하지 않는다
- 실제 ETL 데이터가 준비되면 같은 질문으로 다시 확인한다

## 9. 테스트 질문 수집

6주차 질문 이해 설계와 "관련 정책 없음" 판정(~8주차)의 근거가 된다. 질문마다 검색 청크, 점수, 답변을 기록한다.

| 유형 | 예시 | 확인할 것 |
|---|---|---|
| 일반 탐색 | "서울 사는 24살인데 받을 수 있는 주거 지원 있어?" | 관련 정책이 상위에 나오는지 |
| 특정 정책 | "청년월세 지원 신청 기간 알려줘" | 해당 정책 청크가 1위인지 |
| 후속 질문 | "그 정책 서류 뭐 필요해?" | 단독 질문으로는 실패하는지 (6주차 근거) |
| 비교 | "월세 지원이랑 전세대출 차이가 뭐야?" | 두 정책이 모두 검색되는지 |
| 자격 확인 | "나 이거 받을 수 있어?" | 조건 판단이 정확한지 |
| 관련 없음 | "강아지 사료 추천해줘" | 점수 분포, 엉뚱한 정책을 답하는지 |
| 정책 없음 | 존재하지 않는 지원 분야 질문 | "없다"고 답하는지 |

함께 기록할 것: 관련/비관련 질문의 유사도 점수 분포, 분할 청크의 검색 순위, 요청당 토큰과 응답 시간

---

## 10. 구현 체크리스트

- [x] FastAPI 골격: 설정 객체, lifespan, `GET /health`
- [x] RAG 기반: `LLMClient`(임베딩·답변 생성), DB 연결, 공용 스키마
- [x] 로컬 확인 환경: ETL 스키마 + 가짜 정책 적재
- [x] 검색: 벡터 top-k, 정책 단위 묶기, 정책 정보 조회
- [ ] 답변 생성: `generate_v1` 프롬프트, 신청 기간 상태·프로필 이름 변환
- [ ] 파이프라인 API: `POST /internal/pipeline`, trace 기록
- [ ] 테스트 질문 결과 기록, 실제 ETL 데이터로 재확인
- [ ] README 마무리

## 11. 6주차 미리보기

- 질문 분석 스키마 (2~3개 intent) → `analyzer.py`, `schemas/analysis.py`
- `PipelineContext.analysis` 추가, `runner.py`에 분석 단계 연결
- 현재 정책 상태 관리
- 채팅 저장 계층: `api/rooms.py`, `services/`, `models/`, `chat_repository.py`, `migrations/`
- ERD 수정 요청 전달, 채팅 테이블 마이그레이션 주체 재합의
