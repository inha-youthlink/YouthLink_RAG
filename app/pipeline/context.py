from dataclasses import dataclass, field
from typing import Any

from app.core.dependencies import PipelineDeps
from app.schemas.pipeline import PipelineInput


@dataclass
class PipelineContext:
    input: PipelineInput
    deps: PipelineDeps
    query: str
    trace: dict[str, Any] = field(default_factory=dict)
