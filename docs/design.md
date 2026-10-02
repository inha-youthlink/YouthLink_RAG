# YouthLink RAG 서버 설계 정리

> RAG Technique 담당 기준. Phase 1(RAG 서버가 대화 저장) → Phase 2(Spring으로 이전)를 모두 반영.
> 최종 수정: 2026-10-02 (5주차)

---

## 0. 확정된 방향

| 항목 | 결정 |
|---|---|
| 구조 | **워크플로우형**. LLM은 해석을 맡고, 처리 방식 결정은 코드가 한다 |
| 구현 | **FastAPI로 직접 구현**. 부품 라이브러리는 적극 활용, LangChain은 로컬 실험용 |
| DB | **PostgreSQL + pgvector**. 정책 데이터와 벡터 검색을 같은 DB에서 처리 (SQL JOIN으로 필터링 가능) |
| 대화 저장 | **Phase 1**: RAG 서버가 저장 → **Phase 2**: Spring으로 이전 |
| 핵심 원칙 | **파이프라인은 순수 함수**, 저장은 별도 계층. 저장 위치가 바뀌어도 파이프라인과 테스트는 유지 |
| 품질의 핵심 | Advanced 기법 조합보다 **질문 이해와 처리 방식 결정** |
| 구조 원칙 | 디렉터리 구조는 유지하고, 새 기능은 **파일과 폴더 추가**로 확장. 코드 수정은 허용 |

---

## 1. 먼저 합의해야 할 것

### 1-1. ETL과의 데이터 계약

**확정** (ETL `db/schema.sql` 기준)
- **임베딩 모델과 차원**: `text-embedding-3-small`, 1536차원. 질문도 같은 모델로 임베딩 (`policy_chunk.embedding_model`로 확인)
- **거리 기준**: 코사인 → pgvector `<=>` 연산자, 점수는 `1 - 거리`
- **벡터 인덱스**: HNSW (`vector_cosine_ops`), `WHERE embedding IS NOT NULL` 조건부 인덱스 → 검색 쿼리에도 `embedding IS NOT NULL` 조건 필요

**방향** (ETL 담당자 공유)
- **청크 단위**: 1정책 1청크. 길면 `[세부 내용]`을 문장 단위로 분할
- **임베딩 텍스트 형식**: `[정책] ... [나이] ... [학력] ... [소득 조건] ... [세부 내용] ...`

**미정**
- **`chunk_type` 값의 의미**: 스키마상 필수 값. 분할 여부 구분인지 다른 구분인지
- **분할된 청크의 헤더 반복 여부**: 두 번째 청크부터 `[정책] 정책명`이 없으면 검색과 답변 출처에 불리
- **갱신 방식**: 공고 수정 시 기존 청크 삭제 후 재삽입 여부

### 1-2. 자격 조건 저장 규칙
- 나이: `min_age`, `max_age`, `age_limit_yn`
- 소득: `income_condition_code`, `min_income`, `max_income`, `income_etc`
- 지역: `policy_region`
- 혼인, 전공, 직업, 학력, 특화 대상: `marriage_status_code`, `policy_eligibility_code`
- 구조화 어려운 조건: `additional_qualification`, `participation_exclusion`
- **"제한 없음"과 "정보 없음"의 표현 규칙**
  - 확인됨: 컬럼의 `NULL`은 정보 부재나 변환 실패일 수 있으므로 "제한 없음"으로 해석하지 않음
  - 확인됨: "제한없음"은 명시적인 코드로 존재 (`common_code`의 `0011009` 전공, `0013010` 취업, `0049010` 학력, `0014010` 특화, `0055003` 혼인). 코드 존재 여부만으로 자격을 판단하지 않음
  - 미정: `policy_region`에 행이 없으면 전국인지, 정보 없음인지
  - 이 규칙이 모호하면 **전공무관 정책 누락 문제**가 그대로 재현됨

### 1-3. 테이블 소유권

| 테이블 | Phase 1 | Phase 2 |
|---|---|---|
| `policy`, `policy_region`, `policy_eligibility_code`, `common_code`, `policy_chunk` | ETL 쓰기 / RAG 읽기 | 동일 |
| `chat_room`, `chat_profile`, `chat_message`, `message_policy_ref` | **RAG 서버** (마이그레이션 포함) | **Spring** |

어느 시점이든 **한 테이블에 쓰는 서버는 하나**.

**재합의 필요**: 현재 ETL의 `db/schema.sql`이 `chat_*` 테이블까지 생성한다. 채팅 테이블의 생성·변경(마이그레이션) 주체를 ETL 담당자와 다시 정한다.

---

## 2. 시스템 구성

백엔드는 3개 서버로 운영한다.

| 서버 | 역할 |
|---|---|
| **ETL 서버** | 온통청년 API 수집, 정책 테이블 적재, 청크·임베딩 생성 |
| **RAG 서버** (이 저장소) | 질문 이해, 검색, 답변 생성. Phase 1에서는 채팅 저장도 담당 |
| **RAG 평가 서버** | `/internal/pipeline`을 호출해 RAG·LLM 성능 평가 |

### Phase 1 (지금)
```
[ETL 서버] ── 정책·청크 적재 ──→ [PostgreSQL + pgvector] ←── 읽기 ── [RAG 서버]

[클라이언트] ── /api/rooms/... ──→ [RAG 서버]
                                     ├ 저장 계층 (chat_* 테이블)
                                     └ 파이프라인 (순수 함수)
[RAG 평가 서버] ── /internal/pipeline ──→ [RAG 서버 파이프라인]
```
- 클라이언트: 프론트 없이 백엔드부터 구성하므로 Swagger, 테스트 스크립트, 이후 붙는 프론트

### Phase 2 (Spring 추가 후)
```
[프론트] ──── /api/rooms/... ────→ [Spring] (세션, 채팅방, 메시지 저장)
                                      └── /internal/pipeline ──→ [RAG 서버]
[RAG 평가 서버] ── /internal/pipeline ────────────────────────→ [RAG 서버]
```

`/internal/pipeline`은 끝까지 유지되고, 앞단의 저장 담당만 바뀐다.

---

## 3. FastAPI 프로젝트 구조

### 3-1. 디렉터리 구조 (`[+]`는 이후 추가 예정)
```
YouthLink_RAG/
├─ app/
│  ├─ main.py                    # 앱 생성, 라우터 등록, lifespan
│  ├─ core/
│  │  ├─ config.py               # .env/환경 변수 → 설정 객체
│  │  └─ dependencies.py         # Depends 주입 함수
│  ├─ api/
│  │  ├─ internal.py             # POST /internal/pipeline (저장 없음, 계속 유지)
│  │  ├─ health.py               # GET /health
│  │  └─ rooms.py                [+ 6주차] 채팅방/메시지 API (Phase 2에서 제거)
│  ├─ schemas/
│  │  ├─ pipeline.py             # Profile, PipelineInput/Output, Chunk, PolicyItem
│  │  ├─ analysis.py             [+ 6주차] LLM 구조화 출력
│  │  └─ api.py                  [+ 6주차] 채팅 API 요청/응답
│  ├─ models/                    [+ 6주차] SQLAlchemy 채팅 테이블 모델
│  ├─ llm/
│  │  └─ client.py               # embed(), chat() — OpenAI 호출의 유일한 통로
│  ├─ pipeline/                  # RAG 로직 (DB 쓰기 없음)
│  │  ├─ context.py              # PipelineContext
│  │  ├─ runner.py               # 흐름 조립만
│  │  ├─ analyzer.py             [+ 6주차] 질문 분석
│  │  ├─ validator.py            [+ 6주차] LLM 출력 검증
│  │  ├─ router.py               [+ ~8주차] intent별 분기
│  │  ├─ relevance.py            [+ ~8주차] "관련 정책 없음" 판정
│  │  ├─ verifier.py             [+ 필요 시] 답변 검증
│  │  ├─ handlers/
│  │  │  ├─ default_rag.py       # 기본 RAG 흐름 (이후 기본/대체 경로로 재사용)
│  │  │  ├─ policy_list.py       [+ ~8주차]
│  │  │  ├─ policy_detail.py     [+ ~8주차]
│  │  │  ├─ eligibility.py       [+ ~8주차]
│  │  │  └─ comparison.py        [+ ~8주차]
│  │  ├─ retrieval/
│  │  │  ├─ base.py              # Retriever 인터페이스
│  │  │  ├─ vector.py            # 벡터 유사도 top-k
│  │  │  ├─ factory.py           # 설정값 → 구현체 선택
│  │  │  ├─ bm25.py              [+ 12~13주차]
│  │  │  ├─ transforms.py        [+ 12~13주차] Multi Query, HyDE, Step-back, Decomposition
│  │  │  ├─ fusion.py            [+ 12~13주차] RRF
│  │  │  └─ rerank.py            [+ 12~13주차]
│  │  ├─ grouping.py             # 청크 → 정책 단위 묶기
│  │  └─ generator.py            # 프롬프트 조립 + 답변 생성
│  ├─ services/                  [+ 6주차]
│  │  └─ chat_service.py         # 상태 조회 → 파이프라인 → 저장 (Phase 2에서 제거)
│  ├─ repositories/
│  │  ├─ vector_repository.py    # policy_chunk 벡터 검색 (읽기)
│  │  ├─ policy_repository.py    # policy 조회 (읽기)
│  │  └─ chat_repository.py      [+ 6주차] chat_* 테이블 (Phase 2에서 제거)
│  └─ prompts/
│     ├─ generate_v1.md
│     └─ analyze_v1.md           [+ 6주차]
├─ .github/                      # 이슈·PR 템플릿
├─ docs/
│  ├─ design.md                  # 설계 문서 (항상 최신)
│  └─ weekly/                    # 주차별 계획과 결과
├─ migrations/                   [+ 6주차] Alembic
├─ tests/
│  ├─ conftest.py
│  └─ test_pipeline.py
├─ CLAUDE.local.md
├─ .env.example
├─ .gitignore
├─ pyproject.toml
└─ README.md
```

`app/` 아래 파이썬 패키지와 `tests/`에는 `__init__.py`를 둔다 (`prompts/` 제외).

### 3-2. 계층 규칙

| 계층 | 할 수 있는 일 | 하면 안 되는 일 |
|---|---|---|
| `api/` | 요청 검증, `run_pipeline()` 또는 서비스 호출, 응답 반환 | 비즈니스 로직 |
| `services/` | 저장소 조회 → 파이프라인 → 저장 | 검색, LLM 호출 직접 수행 |
| `pipeline/` | 질문 분석, 검색, 답변 생성 | **DB 쓰기** |
| `repositories/` | DB 읽기/쓰기 | 비즈니스 판단 |
| `llm/` | OpenAI 호출 | 다른 곳에서 OpenAI 직접 호출 금지 |

### 3-3. 라이브러리

| 용도 | 라이브러리 |
|---|---|
| 웹 서버 | FastAPI, Uvicorn |
| 스키마, 설정 | Pydantic, pydantic-settings |
| LLM, 임베딩 | OpenAI SDK 3.x (`AsyncOpenAI`, 답변 생성은 Responses API, 구조화 출력) |
| DB | SQLAlchemy 2.1 (`sqlalchemy[asyncio]`, greenlet 포함), asyncpg, pgvector (Python 패키지) |
| 마이그레이션 | Alembic (채팅 테이블) |
| BM25 | `rank_bm25` + `kiwipiepy` |
| 리랭크 | 한국어 지원 cross-encoder 또는 rerank API |
| 테스트 | pytest, pytest-asyncio |

**모델** (설정으로 변경 가능)

| 용도 | 모델 | 설정 키 |
|---|---|---|
| 임베딩 | `text-embedding-3-small` (ETL과 반드시 동일) | `EMBEDDING_MODEL` |
| 답변 생성 | `gpt-6-luna` (비용·속도 기준, 품질 부족 시 `gpt-6.1-sol` 검토) | `CHAT_MODEL` |

### 3-4. 구현 포인트
- `config.py`: `pydantic-settings`로 `.env` → 타입 검증된 설정. `@lru_cache`로 한 번만 로드. 우선순위는 환경 변수 > `.env` > 기본값
  - 필수 값(`OPENAI_API_KEY`, `DATABASE_URL`)은 기본값 없음 → 빠지면 서버 시작 시 에러
  - 비밀 값은 `SecretStr`로 로그 출력 시 가림
  - `env_ignore_empty=True`: `.env`의 빈 값은 기본값 사용. `.env.example`은 필수/선택 섹션으로 나누고 선택 값에 기본값 주석
  - `.env` 변경 후에는 서버 재시작 필요 (`--reload`는 `.py` 변경만 감지)
- lifespan에서 OpenAI 클라이언트, DB 엔진, 저장소, 검색기를 한 번 생성해 재사용. 잘못된 `RETRIEVER` 값은 서버 시작 시 실패
- 파이프라인 의존성(`PipelineDeps`: 설정, LLM, 검색기, 저장소)은 `Depends`로 주입 → 테스트에서 `dependency_overrides`로 교체
- 모든 엔드포인트와 LLM 호출은 async, 병렬 호출은 `asyncio.gather`
- OpenAI 호출에 타임아웃과 재시도
- 스트리밍은 `StreamingResponse`(SSE), 상태와 출처는 마지막 이벤트로
- `/internal/*`은 외부에 노출하지 않음 (내부 네트워크 또는 API 키)
- `/health`는 서버 생존 확인만. 외부 서비스(OpenAI) 확인은 넣지 않음

---

## 4. API 설계

### 4-1. 내부용 (계속 유지)
```
POST /internal/pipeline   PipelineInput → PipelineOutput (저장 없음)
```
- 지금: 직접 테스트, RAG 평가 서버
- Phase 2: Spring이 호출
- 응답 형식은 필드 추가만 자유롭게

### 4-2. 외부용 (Phase 1에만 RAG 서버에 존재)
```
POST /api/rooms                     채팅방 생성 (session_id, profile) → room_id
GET  /api/rooms?session_id=...      세션의 채팅방 목록
GET  /api/rooms/{room_id}/messages  대화 기록 조회
POST /api/rooms/{room_id}/messages  질문 전송 (session_id, question, action)
```
질문 전송 응답:
```json
{
  "message_id": "...",
  "answer": "...",
  "sources": [{ "policy_no": "...", "policy_name": "...", "url": "..." }],
  "shown_policy_ids": ["..."]
}
```
이 경로와 형식을 Phase 2에서 Spring이 그대로 이어받으면 프론트는 서버 주소만 바꾸면 된다.

---

## 5. 채팅 데이터 모델 (ETL 담당 ERD 기준)

### 5-1. 현재 ERD
```
chat_room           room_id(UUID), title, created_at, updated_at
chat_profile        room_id(PK,FK), age, gender, region_code, marriage_status_code,
                    annual_income, major_code, job_code, school_code,
                    special_target_code, extra_profile(JSONB), updated_at
chat_message        message_id(BIGINT), room_id(FK), role, content, created_at
message_policy_ref  message_id(PK,FK), policy_no(PK,FK), relevance_score
```
- `message_policy_ref`가 "답변에 등장한 정책 ID"를 정규화된 형태로 저장 → 대화 상태의 "직전에 보여준 정책 목록"으로 사용

### 5-2. 추가 확인 필요
- 마감 정책을 삭제하는지 보관하는지 (`message_policy_ref`가 `policy`를 FK로 참조)
- 첨부파일 출처 청크의 원본 파일명/URL 저장 여부 (답변 출처 표시용)

### 5-3. 운영 원칙
- 채팅방 ID는 UUID, 요청마다 세션-채팅방 소유 관계 확인
- 세션 ID는 Phase 1에서 호출 측이 생성, Phase 2에서 Spring이 발급
  - 프론트 없이 백엔드부터 구성하므로 Phase 1의 호출 측은 Swagger, 테스트 스크립트, 이후 붙는 프론트
  - 세션 ID는 UUID 등 임의 문자열. 요청의 세션 ID와 채팅방의 세션 ID가 다르면 404 (인증·토큰은 두지 않음)
  - `chat_room.session_id`는 처음부터 `NOT NULL` + 인덱스 (나중에 추가하면 기존 채팅방 보정과 API 명세 변경 필요)
- 개인정보 보관 기간 정의 (세션 만료 후 삭제 등)

---

## 6. 요청 하나의 처리 흐름

```
[chat_service]
  1. 세션-채팅방 소유 확인
  2. 프로필, 최근 3~5턴, 현재 정책, 직전에 보여준 정책 조회
  3. PipelineInput 구성 → run_pipeline()
  4. 메시지, metadata, message_policy_ref, 상태 저장
  5. 응답 반환

[run_pipeline]
  ① 질문 분석 (LLM 1회, 구조화 출력) — action이 있으면 생략
  ② 출력 검증
  ③ intent별 핸들러 실행
  ④ 관련성 판정
  ⑤ 답변 생성
  ⑥ (선택) 답변 검증
  ⑦ 갱신된 상태와 trace 반환
```

---

## 7. 대화 상태

| 항목 | 의미 | 용도 |
|---|---|---|
| **직전에 보여준 정책 목록** | 직전 답변에 등장한 정책들 (`message_policy_ref`) | "두 번째 거", "그중에 월세" 등 **목록 안 지목** |
| **현재 정책** | 지금 대화가 집중하는 정책 하나 | 정책 이름 없는 **후속 질문**의 기본 대상 |

- **설정**: 상세보기 클릭, 특정 정책 지목, 답변이 정책 하나를 자세히 다룬 경우
- **교체**: 다른 정책을 명확히 지목
- **초기화**: 화제 전환 (`is_new_topic`)

| 턴 | 대화 | 보여준 정책 | 현재 정책 |
|---|---|---|---|
| 1 | "서울 주거 지원 정책 뭐 있어?" → 3개 | [월세, 전세대출, 임대주택] | 없음 |
| 2 | "두 번째 거 자세히" | [전세대출] | **전세대출** |
| 3 | "소득 기준은?" | [전세대출] | 전세대출 |
| 4 | "신청 서류는?" | [전세대출] | 전세대출 |
| 5 | "월세 지원이랑 비교하면?" | [전세대출, 월세] | 전세대출 |
| 6 | "청년 취업 정책도 알려줘" | [취업A, 취업B] | **초기화** |

- LLM에는 최근 3~5턴과 상태만 전달, 긴 이전 답변은 앞부분만

---

## 8. 질문 이해 (가장 중요한 단계)

### 8-1. 역할 분담

| LLM이 하는 일 | 내가 설계하는 것 |
|---|---|
| 의도 분류 | 의도 범주와 출력 스키마 |
| "그 정책"이 가리키는 정책 지목 | LLM에 넣을 맥락 (대화, 후보 목록, 프로필) |
| 대화 맥락 반영 질문 재작성 | 프롬프트와 few-shot 예시 |
| 새로 언급된 정보 추출 | 결과 이후의 규칙, 검증, 대체 경로 |

### 8-2. LLM 없이 확정되는 입력
- 정책 카드 "상세보기" → 현재 정책 설정
- "신청 가이드 PDF", "추천 정책" 버튼 → `action`
- 채팅방 생성 시 프로필

### 8-3. 출력 검증
- 후보에 없는 정책 ID → 버리고 되묻기
- 애매한 분류 → `unclear` 또는 기본 RAG 경로 (`default_rag`)
- 스키마 오류 → 재시도 또는 기본값

### 8-4. 규칙

| 상황 | 규칙 |
|---|---|
| 화제 전환 | 현재 정책 초기화 또는 교체 |
| 여러 정책 중 "그 정책" | 현재 정책 우선, 없으면 되묻기 |
| 프로필과 대화 충돌 | 이번 답변은 대화 우선, 프로필 수정 여부 되묻기 |
| 저장된 정책 마감/수정 | 조회 시 최신 상태 재확인 |

---

## 9. 핸들러

| intent | 처리 방식 |
|---|---|
| **정책 목록** | RDB 조회, 마감 상태 반영해 신청 가능한 공고 우선. RAG 불필요 |
| **정책 상세** | 대상 정책이 있으면 그 정책의 청크 안에서만 검색 (짧으면 전체). 없으면 1차 필터링 후 검색 |
| **자격 확인** | 조건 컬럼과 프로필을 **코드로 비교**, 조건별 충족/불충족/판단 불가. `additional_qualification` 등 텍스트 조건만 LLM이 근거와 함께 "확인 필요"로 설명 |
| **비교** | 정책별로 분해 후 결합 |
| **범위 밖** | 범위 안내 |
| **판단 불가** | 되묻기 또는 `default_rag` |

---

## 10. 검색

### 10-1. 기본
- pgvector 검색: 질문 임베딩과 `policy_chunk.embedding` 거리 정렬 후 top-k
- 1차 필터링 결과는 `policy_ids`로 받아 `WHERE policy_no = ANY(...)`로 제한. 같은 DB라 `policy_region` 등과 JOIN도 가능
- 검색 쿼리에는 `embedding_model = 설정값`과 `embedding IS NOT NULL` 조건을 항상 포함 (다른 모델 임베딩 혼입 방지, HNSW 조건부 인덱스 사용)
- **top-k는 청크 단위** → `policy_no`로 묶고 정책별 최고 점수를 대표값으로
  - 1정책 1청크 방향이므로 top-k가 사실상 추천 정책 수. 분할된 정책만 묶기로 합쳐짐
- Parent-child: 청크로 검색 후 `policy`에서 정책 정보 조회. 분할된 정책은 검색된 청크 외 나머지 청크도 함께 가져올지 결정 필요

### 10-2. 프로필 기반 1차 필터링

**문제 인식**
- 후보가 적어지는 것 자체는 큰 문제가 아님. 벡터 검색은 후보 수와 관계없이 동작하고, 후보가 적으면 관련 없는 정책이 섞일 여지도 줄어듦
- 진짜 위험은 **잘못된 제외**. 정책 데이터에는 `NULL`(정보 없음), "제한없음" 코드, 지역 행 없음 등 해석이 애매한 값이 많아, 프로필이 세부적일수록 받을 수 있는 정책이 조용히 사라질 가능성이 커짐 (전공무관 정책 누락 문제)

**원칙: 확실히 불충족인 정책만 제외**

자격 판정과 같은 3단계 판정을 필터링에도 적용한다.

| 판정 | 처리 | 예시 |
|---|---|---|
| **불충족** (확실함) | 제외 | `max_age=34`인데 사용자가 40세 |
| **판단 불가** | 남김 + 답변에 "확인 필요" 표시 | 나이 컬럼 `NULL`, 지역 행 없음 |
| **충족** | 남김 | "제한없음" 코드, 조건 범위 안 |

**보조 장치**
- **단계적 완화**: 거른 후보가 기준 수(예: 5개) 미만이면 신뢰도가 낮은 조건부터 하나씩 풀어 재검색하고, 어떤 조건을 뺐는지 답변에 안내
- **질문 유형별 적용**

| 질문 유형 | 필터링 |
|---|---|
| 정책 목록, 탐색 | 적용 ("내가 받을 수 있는 정책") |
| 특정 정책 상세, 비교 | 적용하지 않음 (사용자가 정책을 지목) |
| 자격 확인 | 거르지 않고 조건별 판정 결과 제시 |

- **0건일 때 원인 안내**: 어떤 조건 때문에 후보가 없는지 설명 (11장 참고)

**연결 방식**
- 필터링 결과는 정책 번호 목록으로 만들어 `Retriever.retrieve(query, policy_ids, k)`의 `policy_ids`로 전달. 검색 코드는 변경하지 않음
- 필터링 조회는 `policy_repository`에 추가 (DB 접근은 `repositories/`에서만)
- `policy_ids`가 적고 데이터가 많으면 HNSW 탐색 후 조건 적용 방식 때문에 결과가 k개보다 적을 수 있음 → pgvector 반복 탐색 옵션(`hnsw.iterative_scan`) 검토

**결정 전 확인**
- 실제 ETL 데이터로 대표 프로필 몇 개(예: 24세·서울·미취업·대학 재학)의 후보 수를 측정해 완화 기준을 정한다
- 1-2의 미정 규칙(`policy_region` 빈 행 의미, 복수 조건 AND/OR)이 정해져야 판정 기준을 확정할 수 있음
- 프로필 지역 코드와 정책 지역 코드(`zipCd`)의 단위가 같은지, 상하위 지역 처리가 필요한지

### 10-3. Advanced 기법 (질문 유형별 선택 적용)

| 기법 | 적합한 경우 | 주의점 |
|---|---|---|
| Multi Query | 막연한 탐색형 | 한국어 도메인 프롬프트 |
| HyDE | 질문과 공고문 표현 차이 큼 | 공고문 형식 가상 답변 |
| Step-back | 지나치게 구체적인 질문 | 추상화 수준 |
| Decomposition | 비교, 복합 질문 | 결과 결합 |
| Hybrid (BM25) | 정책명, 고유명사, 숫자 | **kiwipiepy 필수**, 후보가 적으면 즉석 계산 |
| RRF | 결과 통합 | 간단 |
| ReRank | 순위 개선 | 한국어 모델, 응답 속도 |
| Compression | 긴 컨텍스트 | 자격 조건 문장 손실 주의 |

---

## 11. "관련 정책 없음" 판정

- **벡터 검색은 항상 k개를 반환** → 별도 판정 필요
- 방법: 유사도 임계값, 리랭커 점수, LLM 관련성 판정 (리랭커 + LLM 조합이 흔함)
- RDB 필터 결과 0건이면 LLM 없이 바로 응답

| 상황 | 응답 |
|---|---|
| 조건에 맞는 정책 없음 | 없다고 안내 + **어떤 조건 때문인지** 설명 |
| 범위 밖 | 범위 안내 |
| 공고문에 정보 없음 | 명시되지 않았다고 안내 + 담당 부서 연락처 (`supervising_org_name` 등) |
| 프로필 부족 | 필요한 정보 되묻기 |

---

## 12. 답변 생성과 검증

- 입력: 재작성된 질문, 검색 근거(정책 번호, 청크 타입 포함), 프로필, 최근 3~5턴, **오늘 날짜**
- 근거는 청크 내용 + 정책 정보(정책명, 신청 기간, URL). ETL 청크에는 신청 기간과 링크가 없어 `policy` 테이블에서 보완
- 신청 상태(신청 가능/마감/상시/정보 없음)는 코드에서 계산해 전달 (LLM의 날짜 비교 오류 방지), 마감 정책은 답변에 명시
- 프로필 코드 값은 `common_code`로 이름 변환 후 전달. 지역은 코드 사전이 없어 제외
- 사실 정보는 **검색 근거에서만**. 이전 답변을 사실 근거로 재사용 금지
- 근거가 없으면 모른다고 답함
- 출처(정책명, `application_url`/`reference_url_*`) 표시
- intent별 프롬프트 분리, `prompts/`에 버전 파일로 관리
- 신청 가이드: `submission_documents`, `application_method`, 발급처 링크, 담당 기관
- 답변 검증(선택): 자격 확인 등 중요 유형에만, 실패 시 재생성 또는 안전 응답

---

## 13. 로깅

`trace`에 기록:
- 원래 질문, 질문 분석 결과, 라우팅 경로
- 검색된 청크와 점수, 리랭크 결과
- 프롬프트 버전, 기법 조합
- 사용 모델 (임베딩, 답변 생성) → 모델별 결과 비교용
- 응답 시간, 토큰 사용량

---

## 14. 비기능 요구사항

- **응답 속도**: 병렬 호출, 효과 있는 기법만 유지
- **비용**: 요청당 LLM 호출 수와 토큰 추적
- **최신성**: 공고 수정과 마감 반영
- **보안**: `/internal/*` 비공개, 세션-채팅방 소유 확인
- **개인정보**: 대화 보관 기간, 로컬 LLM 전환 검토 (`llm/client.py`만 교체)

---

## 15. Spring 이전 계획 (Phase 1 → Phase 2)

### 15-1. 지금부터 지킬 준비
1. 파이프라인은 DB에 쓰지 않는다
2. 채팅 저장 코드는 `api/rooms.py`, `services/`, `models/`, `chat_repository.py`에만
3. 채팅 테이블은 JPA 매핑하기 쉬운 형태 유지
4. 외부 API 명세 문서화 → Spring이 그대로 구현
5. `metadata` JSON 구조 문서화 → Spring은 해석 없이 저장/전달

### 15-2. 이전 절차

| 단계 | 작업 |
|---|---|
| 1 | Spring이 기존 `chat_*` 테이블을 JPA 엔티티로 매핑 (같은 DB, 소유권만 이전) |
| 2 | Spring이 `/api/rooms/...`를 같은 명세로 구현, 내부에서 `/internal/pipeline` 호출 |
| 3 | 세션 ID 발급을 Spring으로 |
| 4 | 스테이징에서 동일 질문으로 Phase 1과 결과 비교 |
| 5 | 프론트 API 주소를 **한 번에 전환** (이중 쓰기 기간 없음) |
| 6 | RAG 서버에서 `rooms.py`, `services/`, `models/`, `chat_repository.py` 제거, 마이그레이션 관리도 Spring(Flyway 등)으로 |

### 15-3. 주의점
- 이중 쓰기 금지
- SSE 사용 시 Spring 중계 방식 확인
- Spring → RAG 타임아웃 넉넉히
- `/internal/pipeline` 호출 주체 제한

---

## 16. 일정

| 시기 | 목표 |
|---|---|
| **5주차** | 프로젝트 골격, `/internal/pipeline`으로 Naive RAG 한 사이클. [weekly/week05.md](weekly/week05.md) 참고 |
| **6주차** | 질문 분석 (2~3개 intent), 현재 정책 상태, 채팅 저장 계층 (`/api/rooms`, ERD 수정 요청 반영) |
| **~8주차** | 핸들러 확장, 관련성 판정, 자격 판정 1차, RAG 평가 서버 연동 |
| **9~10주차** | UI 연동, Spring 추가 시 이전 절차 진행 |
| **11주차** | 중간시연: 질문 이해 + 기본 분기 + 근거 기반 답변 |
| **12~13주차** | Advanced 기법 비교 실험, 오류 분석 기반 개선 |
| **14주차~** | 안정화, 최종 시연 준비 |

### 6주차 채팅 저장 전 ERD 수정 요청

| 요청 | 이유 |
|---|---|
| `chat_room.session_id` (인덱스) | 세션별 채팅방 목록, 소유권 확인 |
| `chat_room.current_policy_no` 또는 `state` JSONB | 후속 질문의 기준 정책 |
| `chat_message.metadata` JSONB | intent, 재작성된 질문, trace 요약 |
| 채팅 테이블 마이그레이션 관리 주체 = RAG 서버 | Phase 1 소유권 |

---
