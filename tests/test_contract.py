"""The seams are binding at runtime, not just statically.

Each test here supplies an adapter that satisfies the Protocol's SHAPE while
violating its CONTRACT, and asserts the harness refuses it at the boundary
instead of producing a plausible-looking but ungroundable report.
"""
import pytest

from grounding import Mode, SeamViolation
from grounding.loop import run
from grounding.model import Claim, Source, Unit
from adapters.fakes import FakeLoader, ScriptedGen, SubsetEntailer

GOOD_CLAIM = Claim("c1", "alpha beta", "u1", "alpha beta")


class _BadLoader:
    """Shape-correct SourceLoader. Contract-violating output, supplied per test."""

    def __init__(self, source: Source) -> None:
        self._source = source

    def load(self, uri: str) -> Source:
        return self._source


def _run_with(loader, claims=(GOOD_CLAIM,)):
    return run("x://doc", "ask", loader, ScriptedGen(list(claims)), SubsetEntailer(),
               mode=Mode.GIST)


def test_unstamped_source_is_rejected():
    # No version_hash: the report would claim grounding "at a version" that does
    # not exist. That makes the audit trail a lie, so it must not run.
    bad = Source(uri="x://doc", version_hash="", units=(Unit("u1", "alpha beta"),))
    with pytest.raises(SeamViolation, match="version_hash"):
        _run_with(_BadLoader(bad))


def test_duplicate_unit_ids_are_rejected():
    # Tier 0 resolves a citation by unit id. A duplicate id is not an address.
    bad = Source(uri="x://doc", version_hash="abc",
                 units=(Unit("u1", "alpha beta"), Unit("u1", "gamma delta")))
    with pytest.raises(SeamViolation, match="duplicate unit id"):
        _run_with(_BadLoader(bad))


def test_source_with_no_units_is_rejected():
    bad = Source(uri="x://doc", version_hash="abc", units=())
    with pytest.raises(SeamViolation, match="zero units"):
        _run_with(_BadLoader(bad))


def test_claim_without_support_quote_is_rejected():
    # A claim with no receipt is malformed, not merely wrong. Dropping it would
    # hide a broken Generator behind a normal-looking report, so it raises.
    naked = Claim("c1", "alpha beta", "u1", "")
    with pytest.raises(SeamViolation, match="support_quote"):
        _run_with(FakeLoader("x://doc", {"u1": "alpha beta"}), claims=(naked,))


def test_claim_without_citation_is_rejected():
    uncited = Claim("c1", "alpha beta", "", "alpha beta")
    with pytest.raises(SeamViolation, match="citation"):
        _run_with(FakeLoader("x://doc", {"u1": "alpha beta"}), claims=(uncited,))


def test_wellformed_adapters_still_pass():
    # The checks are narrow: they enforce what the verifier relies on, and let
    # everything else through untouched.
    result = _run_with(FakeLoader("x://doc", {"u1": "alpha beta"}))
    assert {c.id for c in result.grounded} == {"c1"}
