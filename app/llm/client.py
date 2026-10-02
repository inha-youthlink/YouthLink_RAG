from dataclasses import dataclass

from openai import AsyncOpenAI

from app.core.config import Settings


@dataclass(frozen=True)
class ChatResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


class LLMClient:
    def __init__(self, client: AsyncOpenAI, embedding_model: str, chat_model: str) -> None:
        self._client = client
        self.embedding_model = embedding_model
        self.chat_model = chat_model

    @classmethod
    def from_settings(cls, settings: Settings) -> "LLMClient":
        client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout,
            max_retries=settings.openai_max_retries,
        )
        return cls(client, settings.embedding_model, settings.chat_model)

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self.embedding_model,
            input=text,
        )
        return response.data[0].embedding

    async def chat(self, messages: list[dict[str, str]]) -> ChatResult:
        response = await self._client.responses.create(
            model=self.chat_model,
            input=messages,
        )
        usage = response.usage
        # Responses API의 input/output 토큰을 trace 형식(prompt/completion)에 맞춤
        return ChatResult(
            text=response.output_text,
            prompt_tokens=usage.input_tokens if usage else 0,
            completion_tokens=usage.output_tokens if usage else 0,
        )

    async def close(self) -> None:
        await self._client.close()
