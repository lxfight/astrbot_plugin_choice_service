import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR))

from decision_service import (  # noqa: E402
    DecisionError,
    DecisionService,
    DecisionStats,
    resolve_endpoint,
)
from i18n import Translator, load_i18n, resolve_locale  # noqa: E402


def service_with(handler, *, api_key="test-key", **kwargs):
    return DecisionService(
        api_key=api_key,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_provider_presets_and_custom_endpoint():
    assert resolve_endpoint("typesafe", "", "") == (
        "typesafe",
        "https://api.typesafe.ai/v1/systemone",
        "jev-latest",
    )
    assert resolve_endpoint("openrouter", "", "")[1] == (
        "https://openrouter.ai/api/v1/systemone"
    )
    assert resolve_endpoint("vercel", "", "")[2] == "typesafe-ai/jev"
    assert resolve_endpoint("custom", "https://example.com/v1/systemone", "model") == (
        "custom",
        "https://example.com/v1/systemone",
        "model",
    )
    with pytest.raises(ValueError, match="base_url"):
        resolve_endpoint("custom", "", "model")


def test_choose_maps_options_and_records_stats():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        captured["authorization"] = request.headers["Authorization"]
        return httpx.Response(
            200,
            json={
                "model": "decision-test",
                "answers": {
                    "answer": {
                        "type": "choice",
                        "choice": "o2",
                        "confidence": 0.8,
                        "probabilities": {"o1": 0.2, "o2": 0.8},
                    }
                },
            },
        )

    service = None

    async def run_with_stats():
        nonlocal service
        service = service_with(handler)
        try:
            result = await service.choose(
                "应该回复吗？",
                {"reply": "直接回复", "wait": "保持沉默"},
                state={"text": "在吗"},
            )
            return result, service.stats.snapshot()
        finally:
            await service.close()

    result, stats = asyncio.run(run_with_stats())

    assert captured["authorization"] == "Bearer test-key"
    assert captured["body"]["state"] == {"text": "在吗"}
    assert captured["body"]["questions"]["answer"] == {
        "type": "choice",
        "instructions": "应该回复吗？",
        "criteria": {"o1": "直接回复", "o2": "保持沉默"},
    }
    assert result.choice == "wait"
    assert result.probability == pytest.approx(0.8)
    assert result.confidence == pytest.approx(0.8)
    assert result.probabilities == {
        "reply": pytest.approx(0.2),
        "wait": pytest.approx(0.8),
    }
    assert result.model == "decision-test"
    assert stats["total"] == 1
    assert stats["succeeded"] == 1
    assert stats["choice_counts"] == {"wait": 1}
    assert stats["recent"][0]["question"] == "应该回复吗？"


def test_yes_no_threshold_and_stats():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "decision-test",
                "answers": {"answer": {"type": "noul", "noul": 0.6}},
            },
        )

    async def run():
        service = service_with(handler)
        try:
            accepted = await service.yes_no("应该主动回复吗？", threshold=0.5)
            rejected = await service.yes_no("应该主动回复吗？", threshold=0.7)
            return accepted, rejected, service.stats.snapshot()
        finally:
            await service.close()

    accepted, rejected, stats = asyncio.run(run())
    assert accepted.value is True
    assert rejected.value is False
    assert accepted.probability == pytest.approx(0.6)
    assert stats["bool_calls"] == 2
    assert stats["recent"][0]["result"] == "no"
    assert stats["recent"][1]["result"] == "yes"


def test_failures_are_recorded_and_missing_key_fails_fast():
    service = service_with(lambda request: httpx.Response(200), api_key="")

    async def run():
        try:
            await service.choose("问题", ["A", "B"])
        finally:
            await service.close()

    with pytest.raises(DecisionError, match="API key"):
        asyncio.run(run())
    snapshot = service.stats.snapshot()
    assert snapshot["failed"] == 1
    assert snapshot["last_error"] == "API key is not configured"


def test_unknown_choice_is_rejected_and_counted():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "decision-test",
                "answers": {
                    "answer": {
                        "type": "choice",
                        "choice": "not-offered",
                        "confidence": 1.0,
                        "probabilities": {"o1": 0.5, "o2": 0.5},
                    }
                },
            },
        )

    service = service_with(handler)

    async def run():
        try:
            await service.choose("问题", ["A", "B"])
        finally:
            await service.close()

    with pytest.raises(DecisionError, match="not offered"):
        asyncio.run(run())
    assert service.stats.snapshot()["failed"] == 1


def test_stats_snapshot_has_dashboard_shape():
    stats = DecisionStats()
    stats.record_success(
        kind="choice",
        question="问题",
        result="A",
        probability=0.9,
        confidence=0.8,
        latency_ms=120,
        model="model",
    )
    snapshot = stats.snapshot()
    assert snapshot["success_rate"] == 1.0
    assert snapshot["average_latency_ms"] == 120
    assert snapshot["recent"][0]["ok"] is True
    stats.reset()
    assert stats.snapshot()["total"] == 0


def test_all_locales_have_page_and_chat_resources():
    resources = load_i18n(PLUGIN_DIR)
    assert set(resources) == {"zh-CN", "en-US", "ja-JP", "ru-RU"}
    for locale, data in resources.items():
        assert data["metadata"]["display_name"] == "Choice Service", locale
        assert data["config"]["provider"]["labels"], locale
        assert data["views"]["stats"]["title"] == "Choice Service", locale
        assert data["messages"]["usage"], locale
        assert data["messages"]["result"], locale
    assert resolve_locale("auto", "ja-JP") == "ja-JP"
    assert resolve_locale("auto", None) == "zh-CN"
    assert resolve_locale("ru", "en-US") == "ru-RU"
    for locale in resources:
        translator = Translator(locale, resources)
        assert "/choose" in translator.t("usage"), locale
        assert "测试" in translator.t("failed", error="测试"), locale
