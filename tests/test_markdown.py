"""The markdown adapter, against real files on disk.

These are the tests that prove the seam contract survives contact with real data
rather than a fixture dict. The last one is the important one: it shows a claim
that grounded against an earlier version of a document failing once the document
changes. That is drift, caught mechanically, by a deterministic tier.
"""
from pathlib import Path

import pytest

from grounding import Mode, SeamViolation, run
from grounding.contract import check_source
from adapters.extractive_gen import ExtractiveGenerator
from adapters.fakes import SubsetEntailer
from adapters.markdown import MarkdownLoader
from grounding.model import Claim

FIXTURE = str(Path(__file__).parent / "fixtures" / "sample.md")


def _load(path=FIXTURE):
    return MarkdownLoader().load(path)


def test_real_file_satisfies_the_source_contract():
    # The whole point of this adapter: real data, contract holds.
    check_source(_load())


def test_units_are_addressed_by_heading_path():
    ids = {u.id for u in _load().units}
    assert "Deployment Guide > Setup > Credentials" in ids


def test_headings_inside_code_fences_are_not_headings():
    # The fixture has `# This is a shell comment` inside a bash fence. If it were
    # treated as a heading it would open a bogus unit and swallow the code.
    src = _load()
    assert not any("shell comment" in u.id for u in src.units)
    rollback = src.unit("Deployment Guide > Rollback")
    assert rollback is not None and "./deploy.sh --rollback" in rollback.text


def test_section_with_only_subheadings_is_skipped():
    # `## Notes` has no direct body. A blank unit would violate check_source, and
    # there would be nothing to quote from it anyway.
    ids = {u.id for u in _load().units}
    assert "Deployment Guide > Notes" not in ids
    assert "Deployment Guide > Notes > Example" in ids


def test_duplicate_heading_paths_are_disambiguated():
    # Two `### Example` sections under the same parent. Duplicate unit ids are a
    # SeamViolation, because Tier 0 resolves a citation by id.
    ids = [u.id for u in _load().units]
    assert "Deployment Guide > Notes > Example" in ids
    assert "Deployment Guide > Notes > Example (2)" in ids
    assert len(ids) == len(set(ids))


def test_version_hash_tracks_content(tmp_path):
    p = tmp_path / "d.md"
    p.write_text("# T\n\nalpha beta gamma delta.\n")
    first = MarkdownLoader().load(str(p)).version_hash
    p.write_text("# T\n\nalpha beta gamma epsilon.\n")
    second = MarkdownLoader().load(str(p)).version_hash
    assert first != second


def test_empty_directory_is_refused_by_the_contract(tmp_path):
    with pytest.raises(SeamViolation, match="zero units"):
        run(str(tmp_path), "ask", MarkdownLoader(), ExtractiveGenerator(),
            SubsetEntailer(), mode=Mode.VERBATIM)


def test_end_to_end_grounds_real_claims():
    result = run(FIXTURE, "summarize the guide", MarkdownLoader(),
                 ExtractiveGenerator(), SubsetEntailer(), mode=Mode.VERBATIM)
    assert result.grounded and not result.dropped
    # every kept claim carries a real receipt into a real section
    for claim in result.grounded:
        unit = result.source.unit(claim.citation)
        assert unit is not None
        assert claim.support_quote in unit.text


def test_a_claim_grounded_against_an_older_version_drops_when_the_doc_changes(tmp_path):
    """Drift, caught mechanically.

    A claim is grounded against v1 of a document. The document is then edited.
    Re-run against v2 and the claim no longer grounds: the quote it rests on is
    gone. No model is involved in catching this. It is a string match at Tier 1.
    """
    doc = tmp_path / "policy.md"
    doc.write_text("# Policy\n\nThe retry budget is capped at three attempts.\n")

    v1 = MarkdownLoader().load(str(doc))
    claim = Claim("c1", "The retry budget is capped at three attempts.",
                  "Policy", "The retry budget is capped at three attempts.")

    # Against v1 it grounds.
    class _Fixed:
        def generate(self, source, ask): return [claim]
        def revise(self, source, c, reason): return None

    ok = run(str(doc), "ask", MarkdownLoader(), _Fixed(), SubsetEntailer(),
             mode=Mode.VERBATIM)
    assert {c.id for c in ok.grounded} == {"c1"}

    # The policy changes.
    doc.write_text("# Policy\n\nThe retry budget is capped at five attempts.\n")

    stale = run(str(doc), "ask", MarkdownLoader(), _Fixed(), SubsetEntailer(),
                mode=Mode.VERBATIM)
    assert not stale.grounded
    assert len(stale.dropped) == 1
    verdict = stale.dropped[0]
    assert verdict.tier_reached.value == 1          # verbatim tier, pure code
    assert "not found verbatim" in verdict.reason
    assert stale.source.version_hash != v1.version_hash   # and the stamp proves why
