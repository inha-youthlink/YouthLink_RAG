from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    # App
    app_name: str = "YouthLink RAG"
    app_env: Literal["local", "dev", "prod"] = "local"
    debug: bool = False

    # OpenAI
    openai_api_key: SecretStr
    openai_timeout: float = 30.0
    openai_max_retries: int = 2
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-6-luna"

    # PostgreSQL
    database_url: SecretStr

    # Retrieval
    retriever: str = "vector"
    top_k: int = Field(default=10, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
