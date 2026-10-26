"""AstrBot entry point for the System One compatible decision service."""

from __future__ import annotations

from pathlib import Path

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.api.web import json_response

from .decision_service import DecisionService
from .i18n import Translator, load_i18n, resolve_locale

PLUGIN_NAME = "astrbot_plugin_choice_service"


class ChoiceServicePlugin(Star):
    """Expose generic choice decisions to plugins and the dashboard."""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self.service = DecisionService(
            api_key=str(config.get("api_key", "")),
            provider=str(config.get("provider", "typesafe")),
            base_url=str(config.get("base_url", "")),
            model=str(config.get("model", "")),
            timeout_sec=float(config.get("timeout_sec", 10)),
        )
        self._i18n = load_i18n(Path(__file__).resolve().parent)
        self.context.register_web_api(
            f"/{PLUGIN_NAME}/stats",
            self.page_stats,
            ["GET"],
            "Decision statistics",
        )
        self.context.register_web_api(
            f"/{PLUGIN_NAME}/stats/reset",
            self.page_reset_stats,
            ["POST"],
            "Reset decision statistics",
        )

    def _t(self, key: str, **kwargs) -> str:
        """Translate a chat-facing message."""
        bot_language = self.context.get_config().get("language")
        locale = resolve_locale(self.config.get("language", "auto"), bot_language)
        return Translator(locale, self._i18n).t(key, **kwargs)

    def _page_payload(self) -> dict:
        return {
            "provider": self.service.provider,
            "base_url": self.service.base_url,
            "model": self.service.model,
            "timeout_sec": self.service.timeout_sec,
            "api_key_configured": bool(self.service.api_key),
            "stats": self.service.stats.snapshot(),
        }

    async def page_stats(self):
        """Return live decision statistics for the plugin page."""
        return json_response(self._page_payload())

    async def page_reset_stats(self):
        """Reset live decision statistics."""
        self.service.stats.reset()
        return json_response(self._page_payload())

    @filter.command("choose")
    async def choose(self, event: AstrMessageEvent):
        """Ask one choice question. Usage: /choose question :: option | option"""
        text = (event.message_str or "").strip()
        if text.startswith("/"):
            text = text[1:].lstrip()
        command, _, argument = text.partition(" ")
        if command.lower() == "choose":
            text = argument.strip()

        question, separator, raw_options = text.partition("::")
        options = [item.strip() for item in raw_options.split("|") if item.strip()]
        if not separator or not question.strip() or len(options) < 2:
            yield event.plain_result(self._t("usage"))
            return

        try:
            result = await self.service.choose(question.strip(), options)
        except Exception as exc:
            yield event.plain_result(self._t("failed", error=exc))
            return
        yield event.plain_result(
            self._t(
                "result",
                choice=result.choice,
                probability=f"{result.probability:.3f}",
                confidence=f"{result.confidence:.3f}",
                latency=result.latency_ms,
            )
        )

    async def terminate(self) -> None:
        await self.service.close()
