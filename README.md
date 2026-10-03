# YouthLink RAG

YouthLink RAG 기반 청년 지원 챗봇 및 신청 가이드 시스템의 RAG 서버입니다.

## 설계 및 작업 기록

- [설계 문서](docs/design.md): 시스템 구성, 파이프라인 구조, 설계 결정
- [주차별 작업 기록](docs/weekly/): 주차별 계획, 결정 사항, 결과

## 기술 스택

- Python 3.12, [uv](https://docs.astral.sh/uv/)
- FastAPI, Uvicorn, Pydantic, pydantic-settings
- PostgreSQL + pgvector, SQLAlchemy 2.1 (async), asyncpg
- OpenAI: 임베딩 `text-embedding-3-small`, 답변 생성 `gpt-6-luna`

## 시작하기

### 사전 준비

- Python 3.12 이상
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL + pgvector (ETL 서버의 스키마와 정책 데이터가 적재된 DB)

### 설치

```bash
uv sync
```

### 환경 변수

```bash
# macOS / Linux
cp .env.example .env

# Windows
copy .env.example .env
```

`.env`에 필요한 값을 채웁니다. `.env`는 커밋하지 않습니다.

### 실행

```bash
uv run uvicorn app.main:app --reload
```

- API 문서 (Swagger UI): http://127.0.0.1:8000/docs
- API 문서 (ReDoc): http://127.0.0.1:8000/redoc

## API

| Method | Path | 설명 |
|---|---|---|
| GET | `/health` | 서버 상태 확인 |
| POST | `/internal/pipeline` | 프로필 + 질문 → 추천 정책 + 답변 + trace (저장 없음) |

### `POST /internal/pipeline`

```json
{
  "question": "월세 지원받을 수 있는 정책 있어?",
  "profile": {
    "age": 24,
    "annual_income": 20000000,
    "job_code": "0013003"
  }
}
```

- `profile`은 생략할 수 있고, 각 항목도 모두 선택입니다.
- 응답은 `answer`(답변), `policies`(관련도순 추천 정책), `trace`(검색 결과, 모델, 단계별 시간, 토큰)로 구성됩니다.
- 요청 검증 실패는 422, OpenAI·DB 호출 실패는 503을 반환합니다.
- 자세한 형식은 `/docs`와 [5주차 작업 기록](docs/weekly/week05.md)을 참고하세요.

## 디렉터리 구조

```
app/
├─ main.py         # 앱 생성, lifespan, 라우터 등록
├─ api/            # 라우터 (health, internal)
├─ core/           # 설정, 의존성 주입
├─ schemas/        # 요청·응답 스키마
├─ llm/            # OpenAI 호출 (임베딩, 답변 생성)
├─ pipeline/       # RAG 처리 흐름 (검색, 정책 묶기, 답변 생성)
├─ repositories/   # DB 조회 (읽기 전용)
└─ prompts/        # 프롬프트 파일 (버전별)
docs/              # 설계 문서, 주차별 작업 기록
```

파일 단위 구조는 [설계 문서](docs/design.md)의 3-1을 참고하세요.
