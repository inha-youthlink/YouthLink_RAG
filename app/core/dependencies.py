from dataclasses import dataclass

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.llm.client import LLMClient
from app.pipeline.retrieval.base import Retriever
from app.repositories.policy_repository import PolicyRepository


# VectorRepository는 넣지 않음. 파이프라인은 검색기를 통해서만 검색함
@dataclass(frozen=True)
class PipelineDeps:
    settings: Settings
    llm: LLMClient
    retriever: Retriever
    policy_repository: PolicyRepository


def get_llm(request: Request) -> LLMClient:
    return request.app.state.llm


def get_retriever(request: Request) -> Retriever:
    return request.app.state.retriever


def get_policy_repository(request: Request) -> PolicyRepository:
    return request.app.state.policy_repository


def get_pipeline_deps(
    settings: Settings = Depends(get_settings),
    llm: LLMClient = Depends(get_llm),
    retriever: Retriever = Depends(get_retriever),
    policy_repository: PolicyRepository = Depends(get_policy_repository),
) -> PipelineDeps:
    return PipelineDeps(
        settings=settings,
        llm=llm,
        retriever=retriever,
        policy_repository=policy_repository,
    )
