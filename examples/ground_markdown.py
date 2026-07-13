"""Ground a real markdown file. No network, no API key, no fixtures.

    python examples/ground_markdown.py tests/fixtures/sample.md
    python examples/ground_markdown.py docs/ --mode gist
    python examples/ground_markdown.py README.md --generator claude --mode gist

This is the end-to-end proof: a real loader reading a real file from disk, a real
verifier, and a report with real receipts.

The default generator is deterministic. It quotes sentences verbatim, so its
claims ground by construction and the whole run is offline.

Pass `--generator claude` to use the Claude Code CLI, which needs no API key, only
the `claude` binary on PATH. Pass `--generator api` to use the Anthropic API, which
needs a key. Both reach a real model, so both can be wrong, and the drops are where
the harness earns its keep.

The exit code is where the bindingness lives. Non-zero when anything failed to
ground, so this script is directly usable as a CI step or an agent hook.
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from grounding import Mode, SeamViolation, run
from adapters.extractive_gen import ExtractiveGenerator
from adapters.fakes import SubsetEntailer
from adapters.markdown import MarkdownLoader


def _seams(kind: str):
    """Pick the generator and entailment checker.

    extractive  no model at all. Claims ground by construction, run is offline.
    claude      the Claude Code CLI. No API key. A generator that CAN be wrong.
    api         the Anthropic API. Needs ANTHROPIC_API_KEY.

    The last two share every line of their prompts and parsing (see
    model_seams.py). Only the transport differs.
    """
    if kind == "extractive":
        return ExtractiveGenerator(), SubsetEntailer()
    if kind == "claude":
        from adapters.claude_code import ClaudeCodeEntailer, ClaudeCodeGenerator
        return ClaudeCodeGenerator(), ClaudeCodeEntailer()

    from adapters.anthropic_api import AnthropicEntailer, AnthropicGenerator
    return AnthropicGenerator(), AnthropicEntailer()


def main() -> int:
    ap = argparse.ArgumentParser(description="Ground claims against a markdown source.")
    ap.add_argument("path", help="a .md file or a directory of them")
    ap.add_argument("--ask", default="summarize this document")
    ap.add_argument("--mode", choices=[m.value for m in Mode], default=Mode.VERBATIM.value)
    ap.add_argument("--generator", choices=["extractive", "claude", "api"],
                    default="extractive",
                    help="extractive: no model, always grounds. "
                         "claude: the Claude Code CLI, no API key. "
                         "api: the Anthropic API, needs ANTHROPIC_API_KEY.")
    args = ap.parse_args()

    generator, entailment = _seams(args.generator)

    try:
        result = run(
            uri=args.path,
            ask=args.ask,
            loader=MarkdownLoader(),
            generator=generator,
            entailment=entailment,
            mode=Mode(args.mode),
        )
    except SeamViolation as e:
        # An adapter broke its contract. This is a bug in the adapter, not a bad
        # claim, so it is loud and distinct from an ungrounded result.
        print(f"SEAM VIOLATION: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        # The CLI was missing, timed out, or returned something unusable. Also an
        # adapter problem, and also not an ungrounded result.
        print(f"GENERATOR ERROR: {e}", file=sys.stderr)
        return 2

    print(result.report)

    if result.dropped:
        print(f"\n{len(result.dropped)} claim(s) did not ground.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
