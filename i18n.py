"""Locale resources shared by chat replies and the plugin page."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_LOCALE = "zh-CN"
SUPPORTED_LOCALES = ("zh-CN", "en-US", "ja-JP", "ru-RU")
I18N_SUBDIR = Path(".astrbot-plugin") / "i18n"

_LOCALE_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-hans": "zh-CN",
    "en": "en-US",
    "en-us": "en-US",
    "en-gb": "en-US",
    "ja": "ja-JP",
    "ja-jp": "ja-JP",
    "ru": "ru-RU",
    "ru-ru": "ru-RU",
}


def load_i18n(plugin_dir: str | Path) -> dict[str, dict[str, Any]]:
    """Read all bundled locale files."""
    directory = Path(plugin_dir) / I18N_SUBDIR
    resources: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        resources[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return resources


def normalize_locale(value: Any) -> str | None:
    """Map a language tag onto a bundled locale name."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("_", "-").lower()
    return _LOCALE_ALIASES.get(raw, value.strip())


def resolve_locale(configured: Any, bot_language: Any = None) -> str:
    """Resolve the plugin locale, following AstrBot when set to auto."""
    explicit = normalize_locale(configured)
    if explicit is not None and explicit.lower() != "auto":
        return explicit
    return normalize_locale(bot_language) or DEFAULT_LOCALE


class Translator:
    """Read ``messages.<key>`` with a default-locale fallback."""

    def __init__(
        self,
        locale: str,
        resources: Mapping[str, Any],
        *,
        default_locale: str = DEFAULT_LOCALE,
    ) -> None:
        self.locale = locale
        self._resources = resources
        self._default_locale = default_locale

    def t(self, key: str, **kwargs: Any) -> str:
        """Return a localized message."""
        for locale in (self.locale, self._default_locale):
            data = self._resources.get(locale, {})
            messages = data.get("messages", {})
            template = messages.get(key)
            if isinstance(template, str):
                return template.format(**kwargs)
        return key
