"""Google Gemini 구현 (google-genai SDK)."""
from __future__ import annotations

import os

from google import genai
from google.genai import errors, types

from . import LLMError, T

DEFAULT_MODEL = "gemini-3.6-flash"
TIMEOUT_MS = 60_000


class GeminiClient:
    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))

    def generate(self, *, system: str, prompt: str, schema: type[T]) -> T:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
        )
        # 외부 호출의 경계: 네트워크·API·응답 형식 오류를 모두 LLMError 하나로 바꾼다
        try:
            response = self._client.models.generate_content(
                model=self.model, contents=prompt, config=config,
            )
            return schema.model_validate_json(response.text or "")
        except errors.APIError as exc:
            if exc.code == 429:  # 한도 초과. 원문 JSON은 길어서 화면에 그대로 내보내지 않는다
                raise LLMError(_quota_message(exc)) from exc
            raise LLMError(f"Gemini 호출 실패: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Gemini 호출 실패: {exc}") from exc


def _quota_message(exc: errors.APIError) -> str:
    if "PerDay" in str(exc):  # quotaId 예: GenerateRequestsPerDayPerProjectPerModel-FreeTier
        return "Gemini 하루 사용량 한도를 넘었습니다. 태평양 시간 자정(한국 시간 오후 4~5시)에 초기화됩니다."
    return "Gemini 사용량 한도를 넘었습니다. 1분쯤 뒤에 다시 시도하세요."


def gemini_from_env() -> GeminiClient | None:
    """GEMINI_API_KEY가 없으면 None. LLM 없이도 앱의 나머지 기능은 동작한다."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    return GeminiClient(os.environ.get("NETRECALL_GEMINI_MODEL", DEFAULT_MODEL), api_key)
