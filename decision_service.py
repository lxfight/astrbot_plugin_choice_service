"""System One compatible decision questions exposed as a reusable service."""

from __future__ import annotations

import time
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_PROVIDER = "typesafe"
DEFAULT_BASE_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    """A known System One compatible endpoint."""

    base_url: str
    model: str


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "typesafe": ProviderPreset(DEFAULT_BASE_URL, DEFAULT_MODEL),
    "openrouter": ProviderPreset(
        "https://openrouter.ai/api/v1/systemone",
        "jev-latest",
    ),
    "vercel": ProviderPreset(
        "https://ai-gateway.vercel.sh/typesafe/v1/systemone",
        "typesafe-ai/jev",
    ),
}


class DecisionError(RuntimeError):
    """Raised when the decision endpoint cannot answer a question."""


def resolve_endpoint(
    provider: str,
    base_url: str,
    model: str,
) -> tuple[str, str, str]:
    """Resolve a provider preset against optional endpoint overrides.

    Args:
        provider: Preset name, or ``custom`` for another compatible endpoint.
        base_url: Explicit endpoint; an empty value uses the preset.
        model: Explicit model; an empty value uses the preset.

    Returns:
        Normalized ``(provider, base_url, model)``.

    Raises:
        ValueError: A custom endpoint is missing its URL or model.
    """
    provider = provider.strip().lower() or DEFAULT_PROVIDER
    preset = PROVIDER_PRESETS.get(provider)
    resolved_base = base_url.strip().rstrip("/")
    resolved_model = model.strip()
    if preset is not None:
        resolved_base = resolved_base or preset.base_url
        resolved_model = resolved_model or preset.model
    if not resolved_base:
        raise ValueError("base_url is required for a custom provider")
    if not resolved_model:
        raise ValueError("model is required for a custom provider")
    return provider, resolved_base, resolved_model


@dataclass(slots=True)
class DecisionStats:
    """In-memory counters for the plugin dashboard."""

    started_at: float = field(default_factory=time.time)
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    choice_calls: int = 0
    bool_calls: int = 0
    total_latency_ms: int = 0
    choice_counts: Counter[str] = field(default_factory=Counter)
    recent: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=30))
    last_error: str | None = None

    def record_success(
        self,
        *,
        kind: str,
        question: str,
        result: str,
        probability: float,
        confidence: float | None,
        latency_ms: int,
        model: str,
    ) -> None:
        """Record one successful decision."""
        self.total += 1
        self.succeeded += 1
        self.total_latency_ms += latency_ms
        if kind == "choice":
            self.choice_calls += 1
            self.choice_counts[result] += 1
        else:
            self.bool_calls += 1
        self.recent.append(
            {
                "at": int(time.time() * 1000),
                "kind": kind,
                "question": question[:120],
                "result": result,
                "probability": round(probability, 4),
                "confidence": None if confidence is None else round(confidence, 4),
                "latency_ms": latency_ms,
                "model": model,
                "ok": True,
            }
        )

    def record_failure(
        self,
        *,
        kind: str,
        question: str,
        error: str,
        latency_ms: int,
    ) -> None:
        """Record one failed decision."""
        self.total += 1
        self.failed += 1
        self.last_error = error[:300]
        self.recent.append(
            {
                "at": int(time.time() * 1000),
                "kind": kind,
                "question": question[:120],
                "result": None,
                "probability": None,
                "confidence": None,
                "latency_ms": latency_ms,
                "model": None,
                "ok": False,
                "error": self.last_error,
            }
        )

    def reset(self) -> None:
        """Clear counters and recent decisions."""
        self.started_at = time.time()
        self.total = 0
        self.succeeded = 0
        self.failed = 0
        self.choice_calls = 0
        self.bool_calls = 0
        self.total_latency_ms = 0
        self.choice_counts.clear()
        self.recent.clear()
        self.last_error = None

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-safe view for the plugin page."""
        return {
            "started_at": int(self.started_at * 1000),
            "uptime_sec": int(time.time() - self.started_at),
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "success_rate": (
                round(self.succeeded / self.total, 4) if self.total else 0.0
            ),
            "choice_calls": self.choice_calls,
            "bool_calls": self.bool_calls,
            "average_latency_ms": (
                round(self.total_latency_ms / self.succeeded) if self.succeeded else 0
            ),
            "choice_counts": dict(self.choice_counts.most_common()),
            "recent": list(reversed(self.recent)),
            "last_error": self.last_error,
        }


@dataclass(frozen=True, slots=True)
class ChoiceResult:
    """One selected option and the distribution assigned to all options."""

    choice: str
    probability: float
    confidence: float
    probabilities: dict[str, float]
    model: str
    latency_ms: int


@dataclass(frozen=True, slots=True)
class BoolResult:
    """A yes/no answer reduced to a boolean at the caller's threshold."""

    value: bool
    probability: float
    model: str
    latency_ms: int


class DecisionService:
    """Call a System One compatible model for arbitrary decisions.

    Args:
        api_key: API key for the selected endpoint.
        provider: Provider preset name or ``custom``.
        base_url: Explicit endpoint, or empty for the preset.
        model: Explicit model, or empty for the preset.
        timeout_sec: Total timeout for one HTTP request.
        transport: Optional httpx transport, used by tests.
    """

    def __init__(
        self,
        *,
        api_key: str,
        provider: str = DEFAULT_PROVIDER,
        base_url: str = "",
        model: str = "",
        timeout_sec: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.provider, self.base_url, self.model = resolve_endpoint(
            provider,
            base_url,
            model,
        )
        self.timeout_sec = float(timeout_sec)
        self.stats = DecisionStats()
        self._client = httpx.AsyncClient(
            timeout=self.timeout_sec,
            transport=transport,
        )

    async def choose(
        self,
        question: str,
        options: Mapping[str, Any] | Sequence[str],
        *,
        state: Any = None,
    ) -> ChoiceResult:
        """Choose exactly one option for ``question``.

        Args:
            question: The decision question.
            options: Either ``{value: description}`` or a sequence of values.
            state: Text, object, or array evaluated by the model.

        Returns:
            The selected original value, its probability, confidence, and the
            full distribution keyed by the original values.

        Raises:
            ValueError: The question or option list is unusable.
            DecisionError: The endpoint rejected the request or returned no answer.
        """
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        normalized = self._normalize_options(options)
        option_ids = {
            f"o{index}": value for index, (value, _) in enumerate(normalized, 1)
        }
        criteria = {
            f"o{index}": description
            for index, (_, description) in enumerate(normalized, 1)
        }
        started = time.monotonic()
        try:
            answer, model, latency_ms = await self._ask(
                {
                    "answer": {
                        "type": "choice",
                        "instructions": question,
                        "criteria": criteria,
                    }
                },
                state,
            )
            try:
                choice_id = str(answer["choice"])
                raw_probabilities = answer["probabilities"]
                confidence = float(answer["confidence"])
            except (KeyError, TypeError, ValueError):
                raise DecisionError(
                    "endpoint returned an invalid choice answer"
                ) from None
            if choice_id not in option_ids:
                raise DecisionError("endpoint selected an option that was not offered")
            try:
                probability = float(raw_probabilities[choice_id])
            except (KeyError, TypeError, ValueError):
                raise DecisionError(
                    "endpoint returned an invalid choice answer"
                ) from None
            result = ChoiceResult(
                choice=option_ids[choice_id],
                probability=probability,
                confidence=confidence,
                probabilities={
                    value: float(raw_probabilities.get(option_id, 0.0))
                    for option_id, value in option_ids.items()
                },
                model=model,
                latency_ms=latency_ms,
            )
        except DecisionError as exc:
            self.stats.record_failure(
                kind="choice",
                question=question,
                error=str(exc),
                latency_ms=round((time.monotonic() - started) * 1000),
            )
            raise
        self.stats.record_success(
            kind="choice",
            question=question,
            result=result.choice,
            probability=result.probability,
            confidence=result.confidence,
            latency_ms=result.latency_ms,
            model=result.model,
        )
        return result

    async def yes_no(
        self,
        question: str,
        *,
        state: Any = None,
        threshold: float = 0.5,
    ) -> BoolResult:
        """Return the probability that ``question`` is true.

        Args:
            question: A yes/no statement or question.
            state: Text, object, or array evaluated by the model.
            threshold: Probability at which ``value`` becomes ``True``.

        Returns:
            The thresholded value plus the unrounded probability.

        Raises:
            ValueError: The question or threshold is unusable.
            DecisionError: The endpoint rejected the request or returned no answer.
        """
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        started = time.monotonic()
        try:
            answer, model, latency_ms = await self._ask(
                {"answer": {"type": "noul", "instructions": question}},
                state,
            )
            try:
                probability = float(answer["noul"])
            except (KeyError, TypeError, ValueError):
                raise DecisionError(
                    "endpoint returned an invalid yes/no answer"
                ) from None
            result = BoolResult(
                value=probability >= threshold,
                probability=probability,
                model=model,
                latency_ms=latency_ms,
            )
        except DecisionError as exc:
            self.stats.record_failure(
                kind="bool",
                question=question,
                error=str(exc),
                latency_ms=round((time.monotonic() - started) * 1000),
            )
            raise
        self.stats.record_success(
            kind="bool",
            question=question,
            result="yes" if result.value else "no",
            probability=result.probability,
            confidence=None,
            latency_ms=result.latency_ms,
            model=result.model,
        )
        return result

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    @staticmethod
    def _normalize_options(
        options: Mapping[str, Any] | Sequence[str],
    ) -> list[tuple[str, Any]]:
        if isinstance(options, str):
            raise ValueError("options must contain at least two values")
        if isinstance(options, Mapping):
            normalized = [
                (str(value), description) for value, description in options.items()
            ]
        else:
            normalized = [(str(value), str(value)) for value in options]
        if len(normalized) < 2:
            raise ValueError("options must contain at least two values")
        values = [value for value, _ in normalized]
        if len(set(values)) != len(values):
            raise ValueError("options must be unique")
        return normalized

    async def _ask(
        self,
        questions: dict[str, dict[str, Any]],
        state: Any,
    ) -> tuple[Mapping[str, Any], str, int]:
        if not self.api_key:
            raise DecisionError("API key is not configured")

        started = time.monotonic()
        try:
            response = await self._client.post(
                self.base_url,
                json={
                    "model": self.model,
                    "state": {} if state is None else state,
                    "questions": questions,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except httpx.HTTPError as exc:
            raise DecisionError(
                f"decision endpoint request failed: {type(exc).__name__}"
            ) from None
        if response.status_code != 200:
            raise DecisionError(
                f"decision endpoint returned HTTP {response.status_code}"
            )
        try:
            body = response.json()
            answer = body["answers"]["answer"]
            model = str(body["model"])
        except (KeyError, TypeError, ValueError):
            raise DecisionError(
                "decision endpoint returned an invalid response"
            ) from None
        return answer, model, round((time.monotonic() - started) * 1000)
