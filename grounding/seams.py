"""The pluggable seams.

The spine (model + verifier + loop) is domain-independent. Everything that
varies by domain lives behind these three Protocols. Swap the implementations,
keep the skeleton.
"""
from __future__ import annotations

from typing import Optional, Protocol

from .model import Claim, Source


class SourceLoader(Protocol):
    """Domain seam #1.

    Reads a source LIVE, stamps a version hash, and splits it into ADDRESSABLE
    units. YouTube transcript (unit = segment range), Confluence page (unit =
    heading path), caselaw doc (unit = reporter + pinpoint), repo file (unit =
    line range) -- all implement this one method.

    Reading live is deliberate. Ingesting a frozen copy into a store is the
    second-source-of-truth trap. The version_hash is how drift becomes visible
    instead of silent.
    """

    def load(self, uri: str) -> Source: ...


class Generator(Protocol):
    """The stochastic step.

    Emits claims that each carry a citation AND a support_quote. The quote is
    mandatory: a claim without one is malformed and fails before the verifier
    runs. `revise` is the bounded feedback hook -- fix one claim given the
    reason it failed, or return None to give up on it.
    """

    def generate(self, source: Source, ask: str) -> list[Claim]: ...

    def revise(self, source: Source, claim: Claim, reason: str) -> Optional[Claim]: ...


class EntailmentChecker(Protocol):
    """Domain seam #2 -- the ONLY soft check in the whole system.

    Does `quote` entail `claim_text`? A narrow judgment over a few sentences,
    which is where models are most reliable. Reached only in gist mode, and only
    by claims that already passed the structural and verbatim tiers, so its
    blast radius is small and every call it makes is logged.
    """

    def entails(self, quote: str, claim_text: str) -> tuple[bool, str]: ...
