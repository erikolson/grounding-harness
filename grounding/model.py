"""Data model for the grounding spine.

Everything the verifier needs is a field here. You can only verify against what
you can address, so the model's whole job is to make sources addressable and
claims pointer-carrying.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Mode(str, Enum):
    """The abstraction budget, set per run. Governs how far a claim may drift
    from its verbatim quote -- NOT whether the quote is checked. The quote is
    always verbatim in both modes; that is the free anti-fabrication guarantee.

    VERBATIM: the claim must equal its quote. Deterministic, no model call.
    GIST:     the claim may restate the quote; entailment gates the restatement.
    """
    VERBATIM = "verbatim"
    GIST = "gist"


class Tier(int, Enum):
    STRUCTURAL = 0   # does the cited unit exist at this version?      (pure code)
    VERBATIM = 1     # does the support quote appear verbatim in it?    (pure code)
    ENTAILMENT = 2   # does the quote entail the claim?                 (model call)


@dataclass(frozen=True)
class Unit:
    """An addressable, citeable chunk of a source.

    `id` is a STABLE address: a heading path, line range, segment index, page
    anchor. Every domain defines what a unit is, but every domain must produce
    addressable ones.
    """
    id: str
    text: str


@dataclass(frozen=True)
class Source:
    uri: str
    version_hash: str        # stamped at load time -> freshness + audit
    units: tuple[Unit, ...]

    def unit(self, unit_id: str) -> Optional[Unit]:
        for u in self.units:
            if u.id == unit_id:
                return u
        return None


@dataclass(frozen=True)
class Claim:
    id: str
    text: str                # what is asserted to the caller
    citation: str            # the unit id this claim rests on
    support_quote: str       # the verbatim substring it relies on (mandatory)


@dataclass(frozen=True)
class Verdict:
    claim_id: str
    tier_reached: Tier       # the hardest tier that touched this claim
    passed: bool
    reason: str
