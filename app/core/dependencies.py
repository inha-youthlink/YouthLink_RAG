from dataclasses import dataclass

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.llm.client import LLMClient


@dataclass(frozen=True)
class PipelineDeps:
    settings: Settings
    llm: LLMClient


def get_llm(request: Request) -> LLMClient:
    return request.app.state.llm


def get_pipeline_deps(
    settings: Settings = Depends(get_settings),
    llm: LLMClient = Depends(get_llm),
) -> PipelineDeps:
    return PipelineDeps(settings=settings, llm=llm)
