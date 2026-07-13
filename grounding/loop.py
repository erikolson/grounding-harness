"""The loop: Constrain -> Generate -> Verify -> Feedback.

Wraps the verifier in bounded retries and produces a grounded claim set plus an
audit report. The report is the honesty principle made mechanical: every
dropped claim is named, with the tier it reached and why it died.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .contract import check_claim, check_source
from .model import Claim, Mode, Source, Tier, Verdict
from .seams import EntailmentChecker, Generator, SourceLoader
from .verify import verify_claim


@dataclass
class Result:
    source: Source
    mode: Mode
    grounded: list[Claim]
    dropped: list[Verdict]
    report: str
    # The verdict for EVERY claim, kept or dropped, keyed by claim id. This is
    # what makes the tier hierarchy legible: a grounded claim that settled at
    # tier 1 never touched a model, and a caller should be able to see that
    # rather than take it on faith.
    verdicts: dict[str, Verdict] = field(default_factory=dict)

    def settled_in_code(self) -> list[Claim]:
        """Grounded claims that never reached the model. The cheap, safe ones."""
        return [c for c in self.grounded
                if self.verdicts[c.id].tier_reached is not Tier.ENTAILMENT]

    def settled_by_model(self) -> list[Claim]:
        """Grounded claims that required the one soft check."""
        return [c for c in self.grounded
                if self.verdicts[c.id].tier_reached is Tier.ENTAILMENT]


def run(
    uri: str,
    ask: str,
    loader: SourceLoader,
    generator: Generator,
    entailment: EntailmentChecker,
    mode: Mode = Mode.GIST,
    max_retries: int = 2,
) -> Result:
    # --- Constrain ----------------------------------------------------------
    # Read live, stamp the version, make the source addressable. Freshness and
    # provenance are fixed here, before a single claim is generated.
    source = loader.load(uri)

    # Enforce the SourceLoader contract at the boundary. The Protocol is
    # static-only; this is what makes the seam binding at runtime. A loader that
    # returns an unstamped or unaddressable source fails HERE, loudly, instead of
    # producing claims that quietly cannot ground.
    check_source(source)

    # --- Generate -----------------------------------------------------------
    # The stochastic step. Each claim must arrive with a citation + quote.
    claims = generator.generate(source, ask)

    grounded: list[Claim] = []
    dropped: list[Verdict] = []
    verdicts: dict[str, Verdict] = {}

    for claim in claims:
        # A claim with no receipt is MALFORMED, not merely wrong. That is a bug
        # in the Generator adapter, so it raises rather than dropping: a drop
        # would silently hide a broken seam behind a plausible-looking report.
        check_claim(claim)

        current = claim
        verdict: Verdict | None = None

        for _ in range(max_retries + 1):
            verdict = verify_claim(source, current, entailment, mode)
            if verdict.passed:
                break

            # --- Feedback: bounded. Fix this one claim, or give up. ----------
            revised = generator.revise(source, current, verdict.reason)
            if revised is None:
                break
            check_claim(revised)   # a revision must still carry its receipt
            current = revised

        # Grounded claims keep. Everything else is DROPPED and reported --
        # never backfilled by the model's guess. Abstention is a valid outcome.
        assert verdict is not None
        verdicts[current.id] = verdict
        if verdict.passed:
            grounded.append(current)
        else:
            dropped.append(verdict)

    return Result(source, mode, grounded, dropped,
                  _render_report(source, mode, grounded, dropped, verdicts),
                  verdicts)


_TIER_LABEL = {
    Tier.STRUCTURAL: "tier 0, code",
    Tier.VERBATIM: "tier 1, code",
    Tier.ENTAILMENT: "tier 2, MODEL",
}


def _render_report(source: Source, mode: Mode, grounded: list[Claim],
                   dropped: list[Verdict], verdicts: dict[str, Verdict]) -> str:
    by_model = sum(1 for c in grounded
                   if verdicts[c.id].tier_reached is Tier.ENTAILMENT)
    in_code = len(grounded) - by_model

    lines = [
        "GROUNDING REPORT",
        f"source : {source.uri}",
        f"version: {source.version_hash[:8]}",
        f"mode   : {mode.value}",
        f"grounded: {len(grounded)}   dropped: {len(dropped)}",
        # The number that matters. Every claim settled in code is a claim whose
        # grounding involved no stochastic judgment at all.
        f"settled in code: {in_code}   required the model: {by_model}",
        "",
        "GROUNDED",
    ]
    for c in grounded:
        tier = _TIER_LABEL[verdicts[c.id].tier_reached]
        lines.append(f"  [{tier}] {c.id}: {c.text}")
        lines.append(f"       -> {c.citation}: \"{c.support_quote}\"")
    lines.append("")
    lines.append("DROPPED (surfaced, not smuggled)")
    for v in dropped:
        lines.append(f"  [tier {v.tier_reached.value}] {v.claim_id}: {v.reason}")
    return "\n".join(lines)
