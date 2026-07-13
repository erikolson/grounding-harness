"""A domain-independent grounding spine.

Point it at a source, generate claims that each carry a citation, and only keep
the ones a tiered verifier can ground. The domain is a plugin; the skeleton
never changes.
"""
from .contract import SeamViolation, check_claim, check_source
from .loop import Result, run
from .model import Claim, Mode, Source, Tier, Unit, Verdict
from .seams import EntailmentChecker, Generator, SourceLoader
from .verify import verify_claim

__all__ = [
    "run", "Result",
    "Source", "Unit", "Claim", "Verdict", "Tier", "Mode",
    "SourceLoader", "Generator", "EntailmentChecker",
    "SeamViolation", "check_source", "check_claim",
    "verify_claim",
]
