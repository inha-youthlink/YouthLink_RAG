from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_GET_BY_IDS_SQL = text("""
SELECT policy_no, policy_name,
       application_period_type_code, application_start_date, application_end_date,
       application_url, application_method, submission_documents, supervising_org_name
FROM policy
WHERE policy_no = ANY(:policy_nos)
""")


@dataclass(frozen=True)
class PolicyRecord:
    policy_no: str
    policy_name: str
    application_period_type_code: str | None
    application_start_date: date | None
    application_end_date: date | None
    application_url: str | None
    application_method: str | None
    submission_documents: str | None
    supervising_org_name: str | None


class PolicyRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ANY는 결과 순서를 보장하지 않아 dict로 반환함. 호출 측에서 묶기 결과 순서대로 꺼내 씀
    async def get_by_ids(self, policy_nos: list[str]) -> dict[str, PolicyRecord]:
        if not policy_nos:
            return {}

        async with self._session_factory() as session:
            result = await session.execute(_GET_BY_IDS_SQL, {"policy_nos": policy_nos})
            return {row["policy_no"]: PolicyRecord(**row) for row in result.mappings()}
