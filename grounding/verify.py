"""The tiered verifier -- the actual composition.

A claim is settled by the hardest check that can settle it, and only falls to a
softer one if it must. Short-circuit upward: fail a tier, never pay for the
tiers above it.

The support_quote is checked verbatim in BOTH modes (Tier 0 + Tier 1). That is
the free anti-fabrication guarantee and it is never given up. The Mode only
governs what happens when the claim text differs from its quote.
"""
from __future__ import annotations

from .model import Claim, Mode, Source, Tier, Verdict
from .seams import EntailmentChecker


def _norm(s: str) -> str:
    return " ".join(s.split())


def verify_claim(
    source: Source,
    claim: Claim,
    entailment: EntailmentChecker,
    mode: Mode = Mode.GIST,
) -> Verdict:
    # --- Tier 0: structural. Pure code. Both modes. -------------------------
    # Does the cited unit exist in THIS version of the source? Kills fabricated
    # citations and stale-version drift. The failure that gets people sanctioned.
    unit = source.unit(claim.citation)
    if unit is None:
        return Verdict(
            claim.id, Tier.STRUCTURAL, False,
            f"cited unit '{claim.citation}' absent from {source.uri}@{source.version_hash[:8]}",
        )

    # --- Tier 1: verbatim quote. Pure code. Both modes. ---------------------
    # Does the support quote literally appear in that unit? Kills the sneaky
    # "unit exists but doesn't say it" failure before any model call.
    if claim.support_quote not in unit.text:
        return Verdict(
            claim.id, Tier.VERBATIM, False,
            f"support_quote not found verbatim in unit '{claim.citation}'",
        )

    # Extractive fast path, DERIVED not declared: if the claim is its quote,
    # it is settled here in either mode and never pays for the model.
    if _norm(claim.text) == _norm(claim.support_quote):
        return Verdict(claim.id, Tier.VERBATIM, True, "claim equals its verbatim quote")

    # The claim restates its quote. Now the mode decides.
    if mode is Mode.VERBATIM:
        return Verdict(
            claim.id, Tier.VERBATIM, False,
            "verbatim mode: claim restates its quote (allowed only in gist mode)",
        )

    # --- Tier 2: entailment. Model call. Gist mode only. --------------------
    # The one soft judgment, reached only by restating claims that already have
    # a verbatim anchor. Fenced by everything above it.
    ok, reason = entailment.entails(claim.support_quote, claim.text)
    return Verdict(claim.id, Tier.ENTAILMENT, ok, f"entailment: {reason}")
