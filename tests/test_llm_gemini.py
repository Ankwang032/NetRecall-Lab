from types import SimpleNamespace

import pytest
from google.genai import errors
from pydantic import BaseModel, Field

from integrations.llm import LLMError
from integrations.llm import gemini
from integrations.llm.gemini import DEFAULT_MODEL, GeminiClient, gemini_from_env


class Answer(BaseModel):
    value: int = Field(ge=0, le=10)


class StubModels:
    def __init__(self, result):
        self.result = result
        self.kwargs = None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return SimpleNamespace(text=self.result)


@pytest.fixture
def stub(monkeypatch):
    holder = {}

    def make(result):
        models = StubModels(result)
        monkeypatch.setattr(gemini.genai, "Client", lambda **_: SimpleNamespace(models=models))
        holder["models"] = models
        return GeminiClient("test-model", "key")

    make.holder = holder
    return make


def test_sends_system_prompt_and_json_schema(stub):
    client = stub('{"value": 3}')
    assert client.generate(system="역할", prompt="질문", schema=Answer) == Answer(value=3)
    kwargs = stub.holder["models"].kwargs
    assert (kwargs["model"], kwargs["contents"]) == ("test-model", "질문")
    config = kwargs["config"]
    assert config.system_instruction == "역할"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == Answer.model_json_schema()


@pytest.mark.parametrize("text", ["not json", '{"value": 11}', "", None])
def test_invalid_response_raises_llm_error(stub, text):
    with pytest.raises(LLMError):
        stub(text).generate(system="", prompt="", schema=Answer)


def test_api_failure_raises_llm_error(stub):
    with pytest.raises(LLMError, match="연결 끊김"):
        stub(ConnectionError("연결 끊김")).generate(system="", prompt="", schema=Answer)


def quota_error(quota_id):
    return errors.ClientError(429, {"error": {
        "code": 429, "message": "You exceeded your current quota", "status": "RESOURCE_EXHAUSTED",
        "details": [{"violations": [{"quotaId": quota_id}]}],
    }})


@pytest.mark.parametrize("quota_id, expected", [
    ("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "1분쯤 뒤에"),
    ("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "하루 사용량"),
])
def test_quota_error_is_short_message(stub, quota_id, expected):
    with pytest.raises(LLMError) as info:
        stub(quota_error(quota_id)).generate(system="", prompt="", schema=Answer)
    assert expected in str(info.value)
    assert "RESOURCE_EXHAUSTED" not in str(info.value)  # 원문 JSON을 화면에 내보내지 않는다


@pytest.mark.parametrize("code, status, expected", [
    (503, "UNAVAILABLE", "요청이 몰려"),
    (504, "DEADLINE_EXCEEDED", "제시간에 오지 않았습니다"),
])
def test_server_error_is_short_message(stub, code, status, expected):
    error = errors.ServerError(code, {"error": {"code": code, "message": "원문 메시지", "status": status}})
    with pytest.raises(LLMError) as info:
        stub(error).generate(system="", prompt="", schema=Answer)
    assert expected in str(info.value) and "잠시 뒤에 다시 시도" in str(info.value)
    assert status not in str(info.value)


def test_from_env_without_key_is_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert gemini_from_env() is None


def test_from_env_uses_model_variable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.delenv("NETRECALL_GEMINI_MODEL", raising=False)
    assert gemini_from_env().model == DEFAULT_MODEL
    monkeypatch.setenv("NETRECALL_GEMINI_MODEL", "other-model")
    assert gemini_from_env().model == "other-model"
