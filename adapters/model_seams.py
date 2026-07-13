"""Model-backed Generator and EntailmentChecker, independent of how the model is reached.

The prompts and the parsing are the same whether the model is reached through the
Claude Code CLI or through the Anthropic API. Only the TRANSPORT differs. Keeping
one implementation here and two thin transports elsewhere means there is a single
place where the prompt rules live, which is the same reason this whole harness
exists: a second copy of a source of truth is a bug waiting to happen.

A transport is anything with `ask(prompt) -> str`. That is the entire contract.
See `claude_code.py` (a subprocess) and `anthropic_api.py` (an HTTP client).
"""
from __future__ import annotations

import json
import re
from typing import Optional, Protocol

from grounding.model import Claim, Source

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


class ModelSeamError(RuntimeError):
    """The model could not be reached, or returned something unusable.

    Distinct from a SeamViolation (an adapter breaking its contract) and from an
    ungrounded claim (the verifier doing its job). Three different failures, three
    different meanings, and collapsing them would make the report a liar.
    """


class Transport(Protocol):
    """Anything that can turn a prompt into text. A CLI, an API, a local model."""

    def ask(self, prompt: str) -> str: ...


def parse_json(raw: str, expect: type) -> object:
    """Pull a JSON value out of a model response.

    Models wrap JSON in fences and prose no matter how firmly the prompt forbids
    it, so this strips fences and then falls back to slicing from the first bracket
    to the last. Being forgiving HERE is fine: it is a parsing convenience, not a
    verification shortcut. Nothing about it loosens a tier.
    """
    text = _FENCE.sub("", raw).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        open_ch, close_ch = ("[", "]") if expect is list else ("{", "}")
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start == -1 or end == -1 or end < start:
            raise ModelSeamError(f"no JSON {expect.__name__} in response: {text[:300]!r}")
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            raise ModelSeamError(f"malformed JSON in response: {text[:300]!r}") from e

    if not isinstance(value, expect):
        raise ModelSeamError(f"expected a JSON {expect.__name__}, got {type(value).__name__}")
    return value


def render_units(source: Source, max_chars: int) -> str:
    """Serialize the source for the prompt, with the unit ids the model must cite by.

    Truncation is per unit and is ANNOUNCED in the text. A silently truncated
    section would still fail Tier 1 when quoted from, but the failure would look
    like a model error rather than a prompt-budget error, and a misleading verdict
    is worse than a loud one.
    """
    out = []
    for unit in source.units:
        text = unit.text
        if len(text) > max_chars:
            text = text[:max_chars] + "\n[... this section was truncated ...]"
        out.append(f"<unit id={unit.id!r}>\n{text}\n</unit>")
    return "\n\n".join(out)


GENERATE_PROMPT = """\
You are the generation step inside a grounding harness. Read the source below and
produce claims that answer the request. Every claim you make will be mechanically
verified against the source, and any claim that cannot be verified will be thrown
away, so there is no benefit to guessing.

REQUEST: {ask}

SOURCE:
{units}

Return ONLY a JSON array. No prose, no code fences, no commentary. Each element:

  {{"text": "<the claim>",
    "citation": "<the exact id of the unit it rests on>",
    "support_quote": "<a span copied character for character from that unit>"}}

Rules, each of which is checked by code:
1. "citation" must be one of the unit ids above, copied exactly.
2. "support_quote" must appear VERBATIM in that unit. Copy it character for
   character. Do not fix typos, do not change whitespace, do not paraphrase, and
   do not join text across a line break unless it is joined that way in the source.
3. The support_quote must actually support the claim. Do not cite a nearby span
   that merely sounds related.
4. Prefer a claim whose text IS its quote. Such claims are verified without a
   model at all, which is strictly cheaper and safer.
5. If the source does not support a claim, do not make it. Returning fewer claims
   is correct behavior, not a failure. An empty array is a valid answer.

Produce at most {max_claims} claims.
"""

REVISE_PROMPT = """\
You are the repair step inside a grounding harness. A claim you produced failed
verification. Fix it, or give up.

THE CLAIM:
  text:          {text}
  citation:      {citation}
  support_quote: {quote}

WHY IT FAILED: {reason}

THE UNIT IT CITED (id={citation!r}):
{unit_text}

THE FULL SOURCE:
{units}

Return ONLY a JSON object, no prose and no fences, in one of two forms.

To repair it:
  {{"text": "...", "citation": "...", "support_quote": "..."}}

To give up, which is a legitimate and often correct answer:
  {{"give_up": true}}

The same rules apply: the citation must be a real unit id, and the support_quote
must appear VERBATIM in that unit, copied character for character. If the source
genuinely does not support this claim, give up rather than reaching for a span
that only looks close.
"""

ENTAIL_PROMPT = """\
Answer one narrow question. Consider ONLY the quote below. Ignore anything you
know about the world, and ignore any wider context.

QUOTE:
{quote}

CLAIM:
{claim}

Does the quote, on its own, support the claim?

Return ONLY a JSON object, no prose and no fences:
  {{"entailed": true|false, "reason": "<one short sentence>"}}

Say false if the claim adds anything the quote does not state, overstates it,
reverses it, or generalizes beyond it. A claim that is merely CONSISTENT with the
quote is not supported by it.
"""


class ModelGenerator:
    """The stochastic step, performed by whatever model the transport reaches.

    Satisfies the Generator Protocol. Every claim it returns carries a citation and
    a support quote, because `grounding.contract.check_claim` refuses any that do
    not: a claim with no receipt is a bug in this adapter, not a bad claim, so the
    harness raises rather than quietly dropping it.
    """

    def __init__(
        self,
        transport: Transport,
        max_claims: int = 10,
        max_unit_chars: int = 4000,
    ) -> None:
        self._t = transport
        self._max_claims = max_claims
        self._max_unit_chars = max_unit_chars

    def generate(self, source: Source, ask: str) -> list[Claim]:
        raw = self._t.ask(
            GENERATE_PROMPT.format(
                ask=ask,
                units=render_units(source, self._max_unit_chars),
                max_claims=self._max_claims,
            )
        )
        items = parse_json(raw, list)

        claims: list[Claim] = []
        for i, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            claims.append(
                Claim(
                    id=f"c{i}",
                    text=str(item.get("text", "")).strip(),
                    citation=str(item.get("citation", "")).strip(),
                    support_quote=str(item.get("support_quote", "")),
                )
            )
        return claims

    def revise(self, source: Source, claim: Claim, reason: str) -> Optional[Claim]:
        unit = source.unit(claim.citation)
        raw = self._t.ask(
            REVISE_PROMPT.format(
                text=claim.text,
                citation=claim.citation,
                quote=claim.support_quote,
                reason=reason,
                unit_text=unit.text if unit else "[the cited unit does not exist]",
                units=render_units(source, self._max_unit_chars),
            )
        )
        obj = parse_json(raw, dict)

        if obj.get("give_up") is True:
            return None

        text = str(obj.get("text", "")).strip()
        citation = str(obj.get("citation", "")).strip()
        quote = str(obj.get("support_quote", ""))
        if not (text and citation and quote.strip()):
            # A malformed repair is treated as a give-up, not a crash. The loop then
            # drops the claim and reports it, which is the honest outcome.
            return None

        return Claim(id=claim.id, text=text, citation=citation, support_quote=quote)


class ModelEntailer:
    """The one soft check, performed by whatever model the transport reaches.

    Reached only in gist mode, and only by claims that already passed the structural
    and verbatim tiers. Narrow by construction: one quote, one claim, one judgment.
    It can still be wrong, which is why the deterministic tiers do the discriminating
    work and why this is the only place a model is consulted at all.
    """

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def entails(self, quote: str, claim_text: str) -> tuple[bool, str]:
        raw = self._t.ask(ENTAIL_PROMPT.format(quote=quote, claim=claim_text))
        obj = parse_json(raw, dict)
        # Absence of an explicit true is a false. A grounding harness does not get
        # to round an ambiguous judgment up into a pass.
        entailed = obj.get("entailed") is True
        reason = str(obj.get("reason", "")).strip() or "no reason given"
        return entailed, reason
