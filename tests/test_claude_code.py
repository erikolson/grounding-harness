"""The Claude Code adapter, tested without invoking Claude Code.

The subprocess call itself cannot be tested offline, so it is isolated in `_CLI`
and replaced here by a stub that returns canned responses. What IS tested is
everything that can actually be wrong in the adapter: parsing a model's untidy
JSON, building well-formed Claims from it, honoring a give-up, and surviving
garbage. Those are the failure modes that would otherwise show up as confusing
drops at run time.
"""
import pytest

from grounding import Mode, SeamViolation, run
from grounding.model import Source, Unit
from adapters.claude_code import (
    ClaudeCodeEntailer,
    ClaudeCodeError,
    ClaudeCodeGenerator,
)
from adapters.fakes import FakeLoader

SOURCE = Source(
    uri="doc://x",
    version_hash="abc123",
    units=(Unit("u1", "The retry budget is capped at three attempts."),),
)


class StubCLI:
    """Stands in for one headless `claude` invocation. Returns canned text."""

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._responses.pop(0) if self._responses else "[]"


def test_parses_a_clean_json_array():
    cli = StubCLI('[{"text": "capped at three", "citation": "u1", '
                  '"support_quote": "capped at three attempts"}]')
    claims = ClaudeCodeGenerator(cli=cli).generate(SOURCE, "summarize")
    assert len(claims) == 1
    assert claims[0].citation == "u1"
    assert claims[0].support_quote == "capped at three attempts"


def test_parses_json_wrapped_in_fences_and_prose():
    # Models do this constantly no matter how firmly the prompt forbids it.
    cli = StubCLI('Sure, here are the claims:\n```json\n'
                  '[{"text": "t", "citation": "u1", "support_quote": "capped"}]\n```\n')
    claims = ClaudeCodeGenerator(cli=cli).generate(SOURCE, "summarize")
    assert len(claims) == 1 and claims[0].support_quote == "capped"


def test_empty_array_is_a_valid_answer():
    # Abstention is correct behavior, not a failure. The source may not support
    # anything worth claiming.
    claims = ClaudeCodeGenerator(cli=StubCLI("[]")).generate(SOURCE, "summarize")
    assert claims == []


def test_unparseable_response_raises_rather_than_inventing():
    cli = StubCLI("I'm afraid I can't help with that.")
    with pytest.raises(ClaudeCodeError, match="no JSON"):
        ClaudeCodeGenerator(cli=cli).generate(SOURCE, "summarize")


def test_the_prompt_shows_the_model_the_unit_ids_it_must_cite():
    cli = StubCLI("[]")
    ClaudeCodeGenerator(cli=cli).generate(SOURCE, "summarize")
    assert "u1" in cli.prompts[0]
    assert "VERBATIM" in cli.prompts[0]


def test_revise_honors_a_give_up():
    # Giving up is legitimate. The loop then drops the claim and reports it,
    # which is the honest outcome, rather than the model reaching for a span
    # that only looks close.
    cli = StubCLI('{"give_up": true}')
    from grounding.model import Claim
    bad = Claim("c1", "unlimited retries", "u1", "unlimited")
    assert ClaudeCodeGenerator(cli=cli).revise(SOURCE, bad, "not verbatim") is None


def test_revise_returns_a_repaired_claim():
    cli = StubCLI('{"text": "capped at three attempts", "citation": "u1", '
                  '"support_quote": "capped at three attempts"}')
    from grounding.model import Claim
    bad = Claim("c1", "capped at ten attempts", "u1", "capped at ten attempts")
    fixed = ClaudeCodeGenerator(cli=cli).revise(SOURCE, bad, "not verbatim")
    assert fixed is not None
    assert fixed.id == "c1"                        # identity is preserved
    assert fixed.support_quote == "capped at three attempts"


def test_a_malformed_repair_is_treated_as_a_give_up():
    # Better to drop and report than to crash the run on a sloppy repair.
    cli = StubCLI('{"text": "", "citation": "", "support_quote": ""}')
    from grounding.model import Claim
    bad = Claim("c1", "x", "u1", "capped")
    assert ClaudeCodeGenerator(cli=cli).revise(SOURCE, bad, "reason") is None


def test_entailer_parses_a_verdict():
    e = ClaudeCodeEntailer(cli=StubCLI('{"entailed": false, "reason": "claim reverses the quote"}'))
    ok, reason = e.entails("capped at three attempts", "unlimited retries")
    assert ok is False and "reverses" in reason


def test_entailer_defaults_to_not_entailed_on_a_vague_answer():
    # Absence of an explicit true is a false. A grounding harness does not get to
    # round an ambiguous judgment up into a pass.
    e = ClaudeCodeEntailer(cli=StubCLI('{"reason": "unclear"}'))
    ok, _ = e.entails("q", "c")
    assert ok is False


def test_a_claim_with_no_quote_raises_a_seam_violation_through_the_loop():
    # The generator returned a claim with no receipt. That is a malformed claim,
    # which is a bug in the adapter, so the harness refuses it loudly instead of
    # hiding it behind a normal-looking drop.
    cli = StubCLI('[{"text": "something", "citation": "u1", "support_quote": ""}]')
    with pytest.raises(SeamViolation, match="support_quote"):
        run("doc://x", "ask",
            FakeLoader("doc://x", {"u1": "The retry budget is capped at three attempts."}),
            ClaudeCodeGenerator(cli=cli), ClaudeCodeEntailer(cli=StubCLI()),
            mode=Mode.VERBATIM)


def test_the_api_transport_shares_the_same_generator():
    # Same prompts, same parsing, same Claim construction. Only the transport
    # differs. If this drifts from the CLI behavior, model_seams.py has been
    # duplicated somewhere and the single source of truth is gone.
    from adapters.anthropic_api import AnthropicGenerator

    cli = StubCLI('[{"text": "t", "citation": "u1", "support_quote": "capped"}]')
    claims = AnthropicGenerator(api=cli).generate(SOURCE, "summarize")
    assert len(claims) == 1 and claims[0].support_quote == "capped"


def test_api_transport_without_key_or_package_fails_as_a_transport_error():
    # Not a SeamViolation and not an ungrounded claim. A third, distinct failure.
    from adapters.anthropic_api import AnthropicAPI
    from adapters.model_seams import ModelSeamError

    api = AnthropicAPI(api_key="")
    with pytest.raises(ModelSeamError):
        api.ask("hello")


def test_end_to_end_with_a_stubbed_cli_grounds_and_drops_correctly():
    # One good claim, one fabricated citation, one misquote. The verifier does not
    # care that the "model" is a stub: the tiers are the same.
    cli = StubCLI(
        '['
        ' {"text": "The retry budget is capped at three attempts.", "citation": "u1",'
        '  "support_quote": "The retry budget is capped at three attempts."},'
        ' {"text": "Workers are unlimited.", "citation": "u9",'
        '  "support_quote": "unlimited workers"},'
        ' {"text": "Capped at ten.", "citation": "u1",'
        '  "support_quote": "capped at ten attempts"}'
        ']',
        '{"give_up": true}',   # revise for the fabricated citation
        '{"give_up": true}',   # revise for the misquote
    )
    result = run(
        "doc://x", "summarize",
        FakeLoader("doc://x", {"u1": "The retry budget is capped at three attempts."}),
        ClaudeCodeGenerator(cli=cli), ClaudeCodeEntailer(cli=StubCLI()),
        mode=Mode.VERBATIM,
    )
    assert {c.id for c in result.grounded} == {"c1"}
    tiers = {v.claim_id: v.tier_reached.value for v in result.dropped}
    assert tiers == {"c2": 0, "c3": 1}   # fabricated citation, then misquote
