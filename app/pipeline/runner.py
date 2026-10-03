from time import perf_counter

from app.core.dependencies import PipelineDeps
from app.pipeline.context import PipelineContext
from app.pipeline.handlers import default_rag
from app.schemas.pipeline import PipelineInput, PipelineOutput


async def run_pipeline(inp: PipelineInput, deps: PipelineDeps) -> PipelineOutput:
    started = perf_counter()
    ctx = PipelineContext(input=inp, deps=deps, query=inp.question)

    output = await default_rag.handle(ctx)

    # 핸들러 앞에 추가될 단계(질문 분석 등)까지 포함하도록 전체 시간은 여기서 기록함
    output.trace.setdefault("latency_ms", {})["total"] = int((perf_counter() - started) * 1000)
    return output
