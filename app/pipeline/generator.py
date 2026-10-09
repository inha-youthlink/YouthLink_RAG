from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from app.pipeline.context import PipelineContext
from app.pipeline.grouping import PolicyGroup
from app.repositories.policy_repository import PolicyRecord

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

ALWAYS_OPEN_CODE = "0057002"
NO_RESTRICTION_NAME = "제한없음"
MISSING = "정보 없음"
NO_EVIDENCE = "검색된 정책 없음"

PROFILE_CODE_LABELS = {
    "marriage_status_code": "혼인 상태",
    "major_code": "전공",
    "job_code": "취업 상태",
    "school_code": "학력",
    "special_target_code": "특화 대상",
}


class ApplicationStatus(StrEnum):
    ALWAYS_OPEN = "상시 모집"
    OPEN = "신청 가능"
    UPCOMING = "신청 예정"
    CLOSED = "마감"
    UNKNOWN = "정보 없음"


@dataclass(frozen=True)
class GenerationResult:
    answer: str
    prompt_version: str
    # 평가 서버가 근거 템플릿을 복제하지 않도록 LLM에 넘긴 정책별 근거 블록을 그대로 전달함
    contexts: list[str]
    prompt_tokens: int
    completion_tokens: int


async def generate(ctx: PipelineContext, prompt_name: str = "generate_v1") -> GenerationResult:
    system_prompt = (PROMPTS_DIR / f"{prompt_name}.md").read_text(encoding="utf-8")
    profile_text = await _format_profile(ctx)
    contexts = _format_evidence(ctx.groups, ctx.policies, ctx.today)
    evidence = "\n\n".join(contexts) if contexts else NO_EVIDENCE
    user_message = "\n\n".join([
        f"[오늘 날짜]\n{ctx.today.isoformat()}",
        f"[사용자 프로필]\n{profile_text}",
        f"[근거]\n{evidence}",
        f"[질문]\n{ctx.query}",
    ])

    result = await ctx.deps.llm.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ])
    return GenerationResult(
        answer=result.text,
        prompt_version=prompt_name,
        contexts=contexts,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )


# API의 마감 코드는 갱신을 신뢰하기 어려워 상시 여부만 코드로 판단하고 나머지는 날짜로 판단함
def application_status(policy: PolicyRecord, today: date) -> ApplicationStatus:
    if policy.application_period_type_code == ALWAYS_OPEN_CODE:
        return ApplicationStatus.ALWAYS_OPEN

    start, end = policy.application_start_date, policy.application_end_date
    if start is None and end is None:
        return ApplicationStatus.UNKNOWN
    if end is not None and end < today:
        return ApplicationStatus.CLOSED
    if start is not None and start > today:
        return ApplicationStatus.UPCOMING
    return ApplicationStatus.OPEN


async def _format_profile(ctx: PipelineContext) -> str:
    profile = ctx.input.profile
    codes = [getattr(profile, field) for field in PROFILE_CODE_LABELS if getattr(profile, field)]
    code_names = await ctx.deps.common_code_repository.get_names(codes)

    lines = []
    if profile.age is not None:
        lines.append(f"나이: {profile.age}세")
    if profile.gender:
        lines.append(f"성별: {profile.gender}")
    if profile.annual_income is not None:
        lines.append(f"연소득: {_format_won(profile.annual_income)}")
    for field, label in PROFILE_CODE_LABELS.items():
        name = code_names.get(getattr(profile, field) or "")
        if name:
            # 정책 조건의 "제한없음"과 구분되도록 사용자 입장의 표현으로 바꿈
            lines.append(f"{label}: {'해당 없음' if name == NO_RESTRICTION_NAME else name}")
    return "\n".join(lines) if lines else MISSING


def _format_evidence(groups: list[PolicyGroup], policies: dict[str, PolicyRecord], today: date) -> list[str]:
    blocks = []
    for group in groups:
        policy = policies.get(group.policy_no)
        if policy is None:
            continue
        # 정책 번호는 답변에 노출되지 않도록 근거에 넣지 않음
        blocks.append("\n".join([
            f"<정책 {len(blocks) + 1}> {policy.policy_name}",
            f"[신청 상태] {_format_status(policy, today)}",
            f"[신청 방법] {policy.application_method or MISSING}",
            f"[제출 서류] {policy.submission_documents or MISSING}",
            f"[담당 기관] {policy.supervising_org_name or MISSING}",
            f"[신청 링크] {policy.application_url or MISSING}",
            "[내용]",
            *(chunk.content for chunk in group.chunks),
        ]))
    return blocks


def _format_status(policy: PolicyRecord, today: date) -> str:
    status = application_status(policy, today)
    if status in (ApplicationStatus.ALWAYS_OPEN, ApplicationStatus.UNKNOWN):
        return status.value
    start = policy.application_start_date.isoformat() if policy.application_start_date else "미정"
    end = policy.application_end_date.isoformat() if policy.application_end_date else "미정"
    return f"{status.value} (신청 기간: {start} ~ {end})"


def _format_won(amount: int) -> str:
    if amount >= 10_000 and amount % 10_000 == 0:
        return f"{amount // 10_000:,}만 원"
    return f"{amount:,}원"
