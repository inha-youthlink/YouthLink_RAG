from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_GET_NAMES_SQL = text("""
SELECT code, code_name
FROM common_code
WHERE code = ANY(:codes)
""")


class CommonCodeRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # 서버 시작이 DB에 의존하지 않도록 캐시하지 않고 요청마다 필요한 코드만 조회함
    async def get_names(self, codes: list[str]) -> dict[str, str]:
        if not codes:
            return {}

        async with self._session_factory() as session:
            result = await session.execute(_GET_NAMES_SQL, {"codes": codes})
            return {row["code"]: row["code_name"] for row in result.mappings()}
