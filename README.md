# YouthLink RAG

YouthLink RAG 기반 청년 지원 챗봇 및 신청 가이드 시스템의 RAG 서버입니다.

## 설계 및 작업 기록

- [설계 문서](docs/design.md): 시스템 구성, 파이프라인 구조, 설계 결정
- [주차별 작업 기록](docs/weekly/): 주차별 계획, 결정 사항, 결과

## 시작하기

### 사전 준비

- Python 3.12 이상
- [uv](https://docs.astral.sh/uv/)

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
