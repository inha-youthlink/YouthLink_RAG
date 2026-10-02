from typing import Protocol

from app.schemas.pipeline import Chunk


class Retriever(Protocol):
    async def retrieve(self, query: str, policy_ids: list[str] | None, k: int) -> list[Chunk]: ...
