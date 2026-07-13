"""Human-readable demo. Prints the grounding report under both modes.

This is the artifact to point someone at: falsifiable in one run, no network,
no model. Run from the repo root:  python examples/demo.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from grounding import Mode
from grounding.loop import run
from adapters.fakes import FakeLoader, ScriptedGen, SubsetEntailer
from tests.planted import DOC, CLAIMS, EXPECT


def main() -> int:
    ok = True
    for mode in (Mode.GIST, Mode.VERBATIM):
        result = run("doc://harness-spec", "summarize the spec",
                     FakeLoader("doc://harness-spec", DOC),
                     ScriptedGen(CLAIMS), SubsetEntailer(), mode=mode)
        print(result.report)
        got = {c.id for c in result.grounded}
        status = "PASS" if got == EXPECT[mode] else "FAIL"
        print(f"{status} ({mode.value}): grounded {sorted(got)}\n")
        ok = ok and got == EXPECT[mode]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
