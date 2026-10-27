import json
from typing import Final

import httpx
import pytest

import litellm
import litellm.anthropic_interface as messages_api

_OPENAI_PROVIDERS: Final = (
    "deerapi",
    "infiniai",
    "bltcy",
    "xiakexing",
    "shubiaobiao",
    "omnilink",
    "onerouter",
    "funcloud",
    "comflychat",
    "apimart",
    "toapis",
    "azure_openai_v1",
    "apigo",
)
_GEMINI_PROVIDERS: Final = ("deerapi_gemini", "ominilink_gemini")
_CLAUDE_PROVIDERS: Final = ("deerapi_claude", "funcloud_claude")


def _response(provider: str, stream: bool) -> httpx.Response:
    if provider in _GEMINI_PROVIDERS:
        payload = {
            "candidates": [
                {"index": 0, "content": {"role": "model", "parts": [{"text": "ok"}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3, "totalTokenCount": 10},
        }
        return (
            httpx.Response(200, text=f"data: {json.dumps(payload)}\n\n", headers={"content-type": "text/event-stream"})
            if stream
            else httpx.Response(200, json=payload)
        )
    if provider in _CLAUDE_PROVIDERS:
        payload = {
            "id": "msg-unit",
            "type": "message",
            "role": "assistant",
            "model": "unit-model",
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 7, "output_tokens": 3},
        }
        events = (
            {
                "type": "message_start",
                "message": {
                    **payload,
                    "content": [],
                    "stop_reason": None,
                    "usage": {"input_tokens": 7, "output_tokens": 0},
                },
            },
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "ok"}},
            {"type": "content_block_stop", "index": 0},
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 3},
            },
            {"type": "message_stop"},
        )
        return (
            httpx.Response(
                200,
                text="".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events),
                headers={"content-type": "text/event-stream"},
            )
            if stream
            else httpx.Response(200, json=payload)
        )
    payload = {
        "id": "chatcmpl-unit",
        "object": "chat.completion",
        "created": 1,
        "model": "unit-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    }
    chunks = (
        {
            **payload,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"}, "finish_reason": None}],
        },
        {**payload, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    )
    return (
        httpx.Response(
            200,
            text="".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )
        if stream
        else httpx.Response(200, json=payload)
    )


@pytest.mark.parametrize("provider", (*_OPENAI_PROVIDERS, *_GEMINI_PROVIDERS, *_CLAUDE_PROVIDERS))
@pytest.mark.parametrize("is_async", (False, True))
@pytest.mark.parametrize("stream", (False, True))
async def test_custom_providers_dispatch_chat_over_their_protocol(provider, is_async, stream, monkeypatch, respx_mock):
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)
    monkeypatch.setenv(f"{provider.upper()}_API_KEY", "env-key")
    route = respx_mock.route(method="POST", host="dispatch.test").mock(return_value=_response(provider, stream))
    base = "https://dispatch.test/v1beta" if provider in _GEMINI_PROVIDERS else "https://dispatch.test/v1"
    api_base = f"{base}/messages" if provider in _CLAUDE_PROVIDERS else base
    kwargs = {
        "model": f"{provider}/unit-model",
        "messages": [{"role": "user", "content": "hello"}],
        "api_key": "explicit-key",
        "api_base": api_base,
        "stream": stream,
        "max_tokens": 32,
    }
    response = await litellm.acompletion(**kwargs) if is_async else litellm.completion(**kwargs)
    if stream:
        if provider in _CLAUDE_PROVIDERS:
            assert response.custom_llm_provider == provider
        chunks = [chunk async for chunk in response] if is_async else list(response)
        assert "".join(choice.delta.content or "" for chunk in chunks for choice in chunk.choices) == "ok"
        assert chunks[-1].choices[0].finish_reason == "stop"
    else:
        assert response.choices[0].message.content == "ok"
        assert (response.usage.prompt_tokens, response.usage.completion_tokens) == (7, 3)
    request = route.calls.last.request
    body = json.loads(request.content)
    if provider in _GEMINI_PROVIDERS:
        assert (
            request.url.path == f"/v1beta/models/unit-model:{'streamGenerateContent' if stream else 'generateContent'}"
        )
        assert (
            request.headers.get("x-goog-api-key") == "explicit-key" or request.url.params.get("key") == "explicit-key"
        )
        assert body["contents"][0]["parts"] == [{"text": "hello"}]
    elif provider in _CLAUDE_PROVIDERS:
        assert request.url.path == "/v1/messages"
        assert request.headers["authorization"] == "Bearer explicit-key"
        assert "x-api-key" not in request.headers
        assert body["model"] == "unit-model"
    else:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer explicit-key"
        assert body["model"] == "unit-model"
    assert "custom_llm_provider" not in body


@pytest.mark.parametrize("provider", _CLAUDE_PROVIDERS)
@pytest.mark.parametrize("stream", (False, True))
async def test_custom_claude_dispatches_native_messages(provider, stream, monkeypatch, respx_mock):
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)
    route: Final = respx_mock.post("https://native-messages.test/v1/messages").mock(
        return_value=_response(provider, stream)
    )
    arguments: Final = {
        "model": f"{provider}/unit-model",
        "messages": [{"role": "user", "content": "hello"}],
        "api_key": "native-key",
        "api_base": "https://native-messages.test/v1/messages",
        "stream": stream,
        "max_tokens": 32,
    }
    result: Final = await messages_api.acreate(**arguments)
    if stream:
        payload: Final = b"".join([event async for event in result]).decode()
        events: Final = tuple(json.loads(line[6:]) for line in payload.splitlines() if line.startswith("data: "))
        assert events[-1]["type"] == "message_stop"
        assert any(event.get("delta", {}).get("text") == "ok" for event in events)
    else:
        assert result["content"] == [{"type": "text", "text": "ok"}]
        assert result["usage"] == {"input_tokens": 7, "output_tokens": 3}
    request: Final = route.calls.last.request
    assert json.loads(request.content) == {
        "model": "unit-model",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 32,
        "stream": stream,
    }
    assert request.headers["authorization"] == "Bearer native-key"
    assert "x-api-key" not in request.headers


@pytest.mark.parametrize(
    "provider,key_variable",
    (
        ("deerapi", "DEER_API_KEY"),
        ("infiniai", "INFINI_API_KEY"),
        ("bltcy", "BLT_API_KEY"),
        ("xiakexing", "XKX_API_KEY"),
        ("shubiaobiao", "SBB_API_KEY"),
        ("omnilink", "OMNI_API_KEY"),
        ("onerouter", "ONER_API_KEY"),
        ("funcloud", "FUN_API_KEY"),
        ("comflychat", "COMFLY_API_KEY"),
        ("apimart", "API_MART_API_KEY"),
        ("toapis", "TOAPIS_API_KEY"),
        ("azure_openai_v1", "AZURE_API_KEY"),
        ("azure_openai_v1", "AZURE_OPENAI_API_KEY"),
        ("deerapi_gemini", "DEERAPI_API_KEY"),
        ("ominilink_gemini", "OMINILINK_GEMINI_API_KEY"),
        ("deerapi_claude", "DEERAPI_CLAUDE_API_KEY"),
        ("funcloud_claude", "FUNCLOUD_CLAUDE_API_KEY"),
    ),
)
async def test_custom_provider_uses_configured_base_and_legacy_key_alias(provider, key_variable, monkeypatch, respx_mock):
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)
    monkeypatch.delenv(f"{provider.upper()}_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv(key_variable, "legacy-environment-key")
    suffix: Final = "v1beta" if provider in _GEMINI_PROVIDERS else "v1/messages" if provider in _CLAUDE_PROVIDERS else "v1"
    monkeypatch.setenv(f"{provider.upper()}_API_BASE", f"https://legacy-env.test/{suffix}")
    route: Final = respx_mock.route(method="POST", host="legacy-env.test").mock(return_value=_response(provider, False))

    result: Final = await litellm.acompletion(
        model=f"{provider}/unit-model", messages=[{"role": "user", "content": "hello"}], max_tokens=32
    )

    assert result.choices[0].message.content == "ok"
    request: Final = route.calls.last.request
    if provider in _GEMINI_PROVIDERS:
        assert request.headers.get("x-goog-api-key", request.url.params.get("key")) == "legacy-environment-key"
    else:
        assert request.headers["authorization"] == "Bearer legacy-environment-key"


async def test_apigo_dispatches_native_responses(monkeypatch, respx_mock):
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)
    route = respx_mock.post("https://apigo-responses.test/v1/responses").mock(return_value=httpx.Response(200, json={
        "id": "resp-unit", "object": "response", "created_at": 1, "status": "completed", "model": "unit-model",
        "error": None, "incomplete_details": None, "parallel_tool_calls": True, "tools": [], "tool_choice": "auto",
        "output": [{"id": "msg-unit", "type": "message", "role": "assistant", "status": "completed", "content": [
            {"type": "output_text", "text": "ok", "annotations": []}
        ]}],
        "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
    }))

    result = await litellm.aresponses(model="apigo/unit-model", input="hello", api_key="unit-key", api_base="https://apigo-responses.test/v1")

    assert result.output[0].content[0].text == "ok"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (7, 3)
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer unit-key"
    assert json.loads(request.content) == {"model": "unit-model", "input": "hello"}


@pytest.mark.parametrize("provider", _GEMINI_PROVIDERS)
@pytest.mark.parametrize("is_async", (False, True))
async def test_custom_gemini_never_uses_standard_gemini_credentials(provider, is_async, monkeypatch, respx_mock):
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)
    monkeypatch.setattr(litellm, "api_key", None)
    for key in ("DEERAPI_GEMINI_API_KEY", "DEERAPI_API_KEY", "OMINILINK_GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "standard-google-key")
    monkeypatch.setenv("GEMINI_API_KEY", "standard-gemini-key")
    route = respx_mock.route(method="POST", host="custom-without-key.test").mock(return_value=_response(provider, False))
    params = {
        "model": f"{provider}/unit-model", "messages": [{"role": "user", "content": "hello"}],
        "api_base": "https://custom-without-key.test/v1beta", "max_tokens": 32,
    }

    if is_async:
        with pytest.raises(litellm.APIConnectionError, match="Missing Gemini API key"):
            await litellm.acompletion(**params)
    else:
        with pytest.raises(litellm.APIConnectionError, match="Missing Gemini API key"):
            litellm.completion(**params)
    assert not route.called
