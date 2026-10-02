from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_GET_BY_IDS_SQL = text("""
SELECT policy_no, policy_name, application_start_date, application_end_date, application_url
FROM policy
WHERE policy_no = ANY(:policy_nos)
""")


@dataclass(frozen=True)
class PolicyRecord:
    policy_no: str
    policy_name: str
    application_start_date: date | None
    application_end_date: date | None
    application_url: str | None


class PolicyRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_by_ids(self, policy_nos: list[str]) -> dict[str, PolicyRecord]:
        if not policy_nos:
            return {}

        async with self._session_factory() as session:
            result = await session.execute(_GET_BY_IDS_SQL, {"policy_nos": policy_nos})
            return {row["policy_no"]: PolicyRecord(**row) for row in result.mappings()}
