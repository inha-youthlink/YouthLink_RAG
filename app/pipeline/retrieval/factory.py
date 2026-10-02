from collections.abc import Callable

from app.llm.client import LLMClient
from app.pipeline.retrieval.base import Retriever
from app.pipeline.retrieval.vector import VectorRetriever
from app.repositories.vector_repository import VectorRepository

RetrieverBuilder = Callable[[LLMClient, VectorRepository], Retriever]

_REGISTRY: dict[str, RetrieverBuilder] = {
    "vector": VectorRetriever,
}


def create_retriever(name: str, llm: LLMClient, vector_repository: VectorRepository) -> Retriever:
    builder = _REGISTRY.get(name)
    if builder is None:
        raise ValueError(f"Unknown retriever: {name!r}. Available: {sorted(_REGISTRY)}")
    return builder(llm, vector_repository)
