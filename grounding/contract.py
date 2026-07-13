"""Runtime enforcement of the seam contracts.

The Protocols in seams.py are static-only: a type checker sees them, the
interpreter does not. That makes the seams a suggestion at runtime, and a badly
written adapter can satisfy the shape while violating the meaning. A loader that
returns an empty version_hash, or duplicate unit ids, produces claims that cannot
be honestly grounded, and it would do so silently.

These checks close that gap. They are deliberately narrow: they enforce the
properties the VERIFIER RELIES ON, and nothing else. An adapter that breaks one
of them fails loudly at the boundary rather than quietly downstream.

This is the substrate-to-binding move. The Protocol suggests; SeamViolation binds.
"""
from __future__ import annotations

from .model import Claim, Source


class SeamViolation(Exception):
    """An adapter satisfied the shape of a seam but violated its contract.

    Raised at the boundary, before any claim is generated or verified, so the
    failure names the adapter rather than surfacing later as a mysterious drop.
    """


def check_source(source: Source) -> None:
    """Validate a SourceLoader's output.

    Each rule exists because a verifier tier depends on it:

    * units must be non-empty      -> nothing to cite means nothing can ground
    * unit ids must be unique      -> Tier 0 resolves a citation by id; duplicate
                                      ids make that resolution ambiguous, and an
                                      ambiguous address is not an address
    * unit ids must be non-blank   -> a blank id is not a citeable address
    * version_hash must be present -> Tier 0 reports grounding AT a version; a
                                      missing stamp makes the audit trail a lie
    * unit text must be non-blank  -> Tier 1 matches a quote against unit text
    """
    if not isinstance(source.uri, str) or not source.uri.strip():
        raise SeamViolation("SourceLoader returned a Source with a blank uri")

    if not source.version_hash or not source.version_hash.strip():
        raise SeamViolation(
            f"SourceLoader returned no version_hash for {source.uri!r}. "
            "Grounding is reported at a version; an unstamped source cannot be audited."
        )

    if not source.units:
        raise SeamViolation(
            f"SourceLoader returned zero units for {source.uri!r}. "
            "A source with no addressable units has nothing to cite."
        )

    seen: set[str] = set()
    for unit in source.units:
        if not unit.id or not unit.id.strip():
            raise SeamViolation(f"SourceLoader returned a unit with a blank id in {source.uri!r}")
        if unit.id in seen:
            raise SeamViolation(
                f"SourceLoader returned duplicate unit id {unit.id!r} in {source.uri!r}. "
                "Tier 0 resolves a citation by id; a duplicate id is not an address."
            )
        seen.add(unit.id)
        if not unit.text or not unit.text.strip():
            raise SeamViolation(
                f"SourceLoader returned unit {unit.id!r} with blank text in {source.uri!r}. "
                "Tier 1 matches the support quote against unit text."
            )


def check_claim(claim: Claim) -> None:
    """Validate a single Generator-produced claim.

    A claim without a citation or a support quote carries no receipt, and a
    receipt is what the whole harness is for. This is not a verification failure
    (the claim is not wrong, it is malformed), so it raises rather than dropping:
    a generator that omits receipts is a bug in the adapter, not a bad claim.
    """
    if not claim.id or not claim.id.strip():
        raise SeamViolation("Generator returned a claim with a blank id")
    if not claim.text or not claim.text.strip():
        raise SeamViolation(f"Generator returned claim {claim.id!r} with blank text")
    if not claim.citation or not claim.citation.strip():
        raise SeamViolation(
            f"Generator returned claim {claim.id!r} with no citation. "
            "Every claim must name the unit it rests on."
        )
    if not claim.support_quote or not claim.support_quote.strip():
        raise SeamViolation(
            f"Generator returned claim {claim.id!r} with no support_quote. "
            "Every claim must carry the verbatim span it rests on."
        )
