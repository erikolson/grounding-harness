"""Model seams reached through the Anthropic API. Requires an API key.

The counterpart to `claude_code.py`. Same prompts, same parsing, same Generator
and EntailmentChecker: only the transport differs. That is the point of keeping
`model_seams.py` separate, and it is the same instinct the harness applies to
everything else. One source of truth, many bindings.

Install the optional dependency and set a key:

    pip install "grounding-harness[anthropic]"
    export ANTHROPIC_API_KEY=...

If you do not have a key, use `claude_code.py` instead. It needs only the `claude`
binary on PATH and does the same job.
"""
from __future__ import annotations

import os
from typing import Optional

from .model_seams import ModelEntailer, ModelGenerator, ModelSeamError

DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicAPI:
    """One Messages API call. The only API-specific code here.

    The `anthropic` package is imported lazily so that the rest of the repo, and
    every offline test in it, keeps working without the dependency installed.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        max_tokens: int = 2048,
        client: object = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = client
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    def _ensure_client(self) -> object:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as e:
            raise ModelSeamError(
                "the `anthropic` package is not installed. Run "
                '`pip install "grounding-harness[anthropic]"`, or use the Claude Code '
                "transport instead, which needs no API key."
            ) from e
        if not self._api_key:
            raise ModelSeamError(
                "no API key. Set ANTHROPIC_API_KEY, or use the Claude Code transport "
                "instead, which needs no API key."
            )
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def ask(self, prompt: str) -> str:
        client = self._ensure_client()
        try:
            response = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            # Network, auth, and rate-limit failures are transport failures. They
            # are not ungrounded claims, and the report must not confuse the two.
            raise ModelSeamError(f"Anthropic API call failed: {e}") from e

        # Concatenate the text blocks. Assemble by TYPE rather than by position,
        # since a response may interleave block kinds.
        parts = [
            block.text
            for block in getattr(response, "content", [])
            if getattr(block, "type", None) == "text"
        ]
        if not parts:
            raise ModelSeamError("the API returned no text content")
        return "\n".join(parts)


class AnthropicGenerator(ModelGenerator):
    """ModelGenerator over the API transport."""

    def __init__(self, api: Optional[AnthropicAPI] = None, **kw) -> None:
        super().__init__(transport=api or AnthropicAPI(), **kw)


class AnthropicEntailer(ModelEntailer):
    """ModelEntailer over the API transport."""

    def __init__(self, api: Optional[AnthropicAPI] = None) -> None:
        super().__init__(transport=api or AnthropicAPI())
