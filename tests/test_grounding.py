"""The falsifiable eval, as pytest. Green means the verifier holds."""
import pytest

from grounding import Mode
from grounding.loop import run
from adapters.fakes import FakeLoader, ScriptedGen, SubsetEntailer
from tests.planted import DOC, CLAIMS, EXPECT


def _run(mode: Mode):
    return run("doc://harness-spec", "summarize the spec",
               FakeLoader("doc://harness-spec", DOC),
               ScriptedGen(CLAIMS), SubsetEntailer(), mode=mode)


@pytest.mark.parametrize("mode", [Mode.GIST, Mode.VERBATIM])
def test_grounded_set_is_exact(mode):
    result = _run(mode)
    assert {c.id for c in result.grounded} == EXPECT[mode]


def test_planted_false_claims_all_drop():
    result = _run(Mode.GIST)
    dropped = {v.claim_id for v in result.dropped}
    assert {"c4", "c5", "c6"} <= dropped


def test_each_false_claim_dies_at_a_distinct_tier():
    result = _run(Mode.GIST)
    tiers = {v.claim_id: v.tier_reached.value for v in result.dropped}
    assert tiers["c4"] == 0  # fabricated citation
    assert tiers["c5"] == 1  # misquote
    assert tiers["c6"] == 2  # abstractive contradiction


def test_verbatim_mode_drops_faithful_restatement():
    # c3 is a faithful restatement: kept in gist, dropped in verbatim.
    result = _run(Mode.VERBATIM)
    assert "c3" not in {c.id for c in result.grounded}
