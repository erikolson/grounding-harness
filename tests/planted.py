"""Shared fixture: a known doc plus six planted claims.

Three ground; three are planted-false and each dies at a DIFFERENT tier, so the
deterministic tiers do the discriminating work. Imported by both the pytest
suite and the human-readable demo.
"""
from grounding import Claim, Mode

DOC = {
    "u1": "The retry budget is capped at three attempts per claim.",
    "u2": "Sources are read live and stamped with a version hash before generation.",
    "u3": "Ungrounded claims are dropped and reported, never backfilled.",
}

CLAIMS = [
    Claim("c1", "The retry budget is capped at three attempts per claim.",
          "u1", "The retry budget is capped at three attempts per claim."),
    Claim("c2", "Sources are read live and stamped with a version hash before generation.",
          "u2", "Sources are read live and stamped with a version hash before generation."),
    Claim("c3", "ungrounded claims are never backfilled",
          "u3", "Ungrounded claims are dropped and reported, never backfilled"),
    Claim("c4", "The system supports unlimited parallel workers.",
          "u9", "unlimited parallel workers"),
    Claim("c5", "The retry budget is capped at ten attempts.",
          "u1", "capped at ten attempts"),
    Claim("c6", "the retry budget is unlimited",
          "u1", "The retry budget is capped at three attempts per claim."),
]

EXPECT = {
    Mode.GIST: {"c1", "c2", "c3"},
    Mode.VERBATIM: {"c1", "c2"},
}
