"""A Generator that uses no model at all.

It pulls sentences verbatim out of the source and emits them as extractive
claims, each citing the unit it came from and carrying itself as the support
quote. That makes every claim it produces ground by construction.

Why this exists: it lets the whole loop run end to end against a REAL source with
no API key, which is what proves the seam contract holds outside a fixture. It is
a floor, not a product. A real generator is a model call whose output schema
forces a citation and a support quote on every claim, and its claims will NOT all
ground, which is the entire reason the verifier is there.

Read it as: "here is the trivial generator that the verifier cannot catch out."
Everything interesting happens when you swap it for one that can be wrong.
"""
from __future__ import annotations

import re
from typing import Optional

from grounding.model import Claim, Source

# Split on sentence enders followed by whitespace. Deliberately simple; this is a
# stand-in, and a smarter splitter would not make it any less of a stand-in.
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_PROSE = re.compile(r"^[A-Za-z(`*\"']")


class ExtractiveGenerator:
    """Emits the first N prose sentences of each unit as extractive claims."""

    def __init__(self, per_unit: int = 1, max_claims: int = 12) -> None:
        self._per_unit = per_unit
        self._max_claims = max_claims

    def generate(self, source: Source, ask: str) -> list[Claim]:
        claims: list[Claim] = []
        for unit in source.units:
            taken = 0
            for sentence in _candidates(unit.text):
                if taken >= self._per_unit or len(claims) >= self._max_claims:
                    break
                claims.append(
                    Claim(
                        id=f"c{len(claims) + 1}",
                        text=sentence,          # the claim IS the span, so it is
                        citation=unit.id,       # extractive: settled at Tier 1,
                        support_quote=sentence,  # never reaching the model.
                    )
                )
                taken += 1
        return claims

    def revise(self, source: Source, claim: Claim, reason: str) -> Optional[Claim]:
        # Nothing to revise: this generator cannot be wrong by construction. A
        # real one re-prompts with `reason` and returns a corrected claim.
        return None


def _candidates(text: str) -> list[str]:
    """Prose sentences from a unit body, skipping code, tables, and list markup.

    Quoting a table row or a fence line as a "claim" would be noise, and the
    point of the demo is to show real claims grounding against real sections.
    """
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped:
            continue
        if stripped.startswith(("|", ">", "-", "*", "#")):
            continue
        for sentence in _SENTENCE.split(stripped):
            s = sentence.strip()
            # A claim needs enough substance to be worth verifying.
            if len(s) >= 40 and _PROSE.match(s):
                out.append(s)
    return out
