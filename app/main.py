from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import health
from app.core.config import get_settings
from app.llm.client import LLMClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    # 서버 시작: OpenAI, DB 클라이언트 생성
    app.state.llm = LLMClient.from_settings(settings)
    app.state.engine = create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
    )
    app.state.session_factory = async_sessionmaker(app.state.engine, expire_on_commit=False)

    yield

    # 서버 종료: 클라이언트 정리
    await app.state.llm.close()
    await app.state.engine.dispose()


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(health.router)
