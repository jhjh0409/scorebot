from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.pipeline.llm_utils import (
    ThrottledProvider,
    initialize_llm_provider,
    resolve_provider,
)
from backend.pipeline.models import (
    AnthropicProvider,
    ModelProvider,
    OpenAIProvider,
)


class TestResolveProvider:
    def test_known_model_names_route_themselves(self):
        assert resolve_provider("gemma3:4b", provider_env="") == ModelProvider.OLLAMA
        assert resolve_provider("gemini-2.5-flash-lite", provider_env="") == ModelProvider.GEMINI

    def test_prefix_inference_for_new_model_ids(self):
        assert resolve_provider("gemini-9.9-ultra", provider_env="") == ModelProvider.GEMINI
        assert resolve_provider("claude-sonnet-5", provider_env="") == ModelProvider.ANTHROPIC
        assert resolve_provider("gpt-5.1-mini", provider_env="") == ModelProvider.OPENAI

    def test_model_name_beats_mismatched_env(self):
        # explicit --model gemma3:4b must not be routed to gemini by the env
        assert resolve_provider("gemma3:4b", provider_env="gemini") == ModelProvider.OLLAMA
        assert resolve_provider("claude-sonnet-5", provider_env="gemini") == (
            ModelProvider.ANTHROPIC
        )

    def test_env_decides_unrecognized_ids(self):
        assert resolve_provider("my-fine-tune-v2", provider_env="openai") == (
            ModelProvider.OPENAI
        )
        assert resolve_provider("my-fine-tune-v2", provider_env="anthropic") == (
            ModelProvider.ANTHROPIC
        )

    def test_unrecognized_id_without_env_falls_back_to_ollama(self):
        assert resolve_provider("mystery-model", provider_env="") == ModelProvider.OLLAMA

    def test_invalid_env_raises_loudly(self):
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER 'gemeni'"):
            resolve_provider("gemini-2.5-flash", provider_env="gemeni")


class TestMissingKeys:
    @patch("backend.pipeline.llm_utils.ANTHROPIC_API_KEY", "")
    def test_anthropic_without_key_fails_loudly(self):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            initialize_llm_provider("claude-sonnet-5")

    @patch("backend.pipeline.llm_utils.OPENAI_API_KEY", "")
    def test_openai_without_key_fails_loudly(self):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            initialize_llm_provider("gpt-5.1-mini")

    @patch("backend.pipeline.llm_utils.ANTHROPIC_API_KEY", "test-key")
    def test_provider_comes_back_throttled(self):
        with patch("anthropic.Anthropic"):
            provider = initialize_llm_provider("claude-sonnet-5")
        assert isinstance(provider, ThrottledProvider)


MESSAGES = [
    {"role": "system", "content": "You are a strict evaluator."},
    {"role": "user", "content": "Score this resume as JSON."},
]
OPTIONS = {"stream": False, "temperature": 0.1, "top_p": 0.9}


class TestAnthropicProvider:
    @patch("anthropic.Anthropic")
    def test_chat_maps_messages_and_response(self, anthropic_cls):
        client = anthropic_cls.return_value
        client.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"ok": true}')]
        )

        provider = AnthropicProvider(api_key="k")
        response = provider.chat(
            model="claude-sonnet-5", messages=MESSAGES, options=OPTIONS, format={}
        )

        assert response == {"message": {"role": "assistant", "content": '{"ok": true}'}}
        params = client.messages.create.call_args.kwargs
        # system prompt is lifted out of the message list
        assert params["system"] == "You are a strict evaluator."
        assert params["messages"] == [MESSAGES[1]]
        assert params["temperature"] == 0.1
        assert params["max_tokens"] > 0
        assert "format" not in params


class TestOpenAIProvider:
    @patch("openai.OpenAI")
    def test_chat_maps_messages_and_response(self, openai_cls):
        client = openai_cls.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
        )

        provider = OpenAIProvider(api_key="k")
        response = provider.chat(
            model="gpt-5.1-mini", messages=MESSAGES, options=OPTIONS, format={}
        )

        assert response == {"message": {"role": "assistant", "content": '{"ok": true}'}}
        params = client.chat.completions.create.call_args.kwargs
        assert params["messages"] == MESSAGES  # system stays in-line for OpenAI
        # the pipeline's json-schema hint becomes OpenAI's json_object mode
        assert params["response_format"] == {"type": "json_object"}

    @patch("openai.OpenAI")
    def test_no_response_format_without_format_kwarg(self, openai_cls):
        client = openai_cls.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))]
        )
        OpenAIProvider(api_key="k").chat(model="gpt-5.1-mini", messages=MESSAGES)
        assert "response_format" not in client.chat.completions.create.call_args.kwargs
