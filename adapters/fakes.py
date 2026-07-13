"""Deterministic in-memory adapters. No network, no model.

Used by the tests and the demo, and a template for real adapters. Note that all
three seams are satisfiable in about eighty lines: that small surface is the
whole point of keeping the core clean.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

from grounding.model import Claim, Source, Unit


class FakeLoader:
    """SourceLoader over a fixed dict of units."""

    def __init__(self, uri: str, units: dict[str, str]) -> None:
        self._uri = uri
        self._units = units

    def load(self, uri: str) -> Source:
        text = "\n".join(f"{k}:{v}" for k, v in self._units.items())
        version = hashlib.sha256(text.encode()).hexdigest()
        units = tuple(Unit(id=k, text=v) for k, v in self._units.items())
        return Source(uri=self._uri, version_hash=version, units=units)


class ScriptedGen:
    """Generator that replays a fixed list of claims, so the verifier can be
    tested in isolation. `revise` is a no-op here."""

    def __init__(self, claims: list[Claim]) -> None:
        self._claims = claims

    def generate(self, source: Source, ask: str) -> list[Claim]:
        return list(self._claims)

    def revise(self, source: Source, claim: Claim, reason: str) -> Optional[Claim]:
        return None


class SubsetEntailer:
    """EntailmentChecker faked as a content-word subset test. Stands in for a
    real model call; same signature, drop-in replaceable."""

    _STOP = {"the", "a", "an", "is", "are", "of", "to", "and", "in", "on", "at",
             "be", "by", "it", "that", "this", "with", "for", "as", "not"}

    def _content(self, s: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in self._STOP}

    def entails(self, quote: str, claim_text: str) -> tuple[bool, str]:
        missing = self._content(claim_text) - self._content(quote)
        if missing:
            return False, f"claim words not in quote: {sorted(missing)}"
        return True, "all claim content words present in quote"
