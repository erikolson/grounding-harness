# grounding

[![ci](https://github.com/erikolson/grounding-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/erikolson/grounding-harness/actions/workflows/ci.yml)

A grounding harness for LLM output. Every claim the model makes carries a
citation, and only the claims a verifier can trace back to the source survive.
Everything else is dropped and reported, never smuggled into the answer.

The thesis, in one line: a harness is only as good as its verifier, so build the
verifier first.

## The problem

Language models assert things without giving an account of why. Ask a tool for a
summary and you get fluent prose with no way to check any single claim against
its source. The failure that matters most, a citation to something that does not
exist, is exactly the one a model grading its own output waves through.

Grounding fixes this with structure rather than a bigger model. Force every claim
to carry the specific span it rests on, then verify that pairing. Generation
stays stochastic. The certainty comes from the filter after it, not the guess.

## How it works

The loop is domain independent:

```
Constrain  read the source live, stamp a version, split into addressable units
Generate   the model emits claims, each with a citation and a verbatim quote
Verify     a tiered verifier checks each claim, hardest check first
Feedback   ungrounded claims retry within a budget, then drop and report
```

## What the output looks like

```
GROUNDING REPORT
source : doc://harness-spec
version: 576dccdd
mode   : gist
grounded: 3   dropped: 3

GROUNDED
  c1: The retry budget is capped at three attempts per claim.
       -> u1: "The retry budget is capped at three attempts per claim."
  ...

DROPPED (surfaced, not smuggled)
  [tier 0] c4: cited unit 'u9' absent from doc://harness-spec@576dccdd
  [tier 1] c5: support_quote not found verbatim in unit 'u1'
  [tier 2] c6: entailment: claim words not in quote: ['unlimited']
```

Every kept claim carries its receipt: the claim, the unit it came from, and the
verbatim span it rests on. Every dropped claim states the tier it failed and why.
That report is a machine-readable audit trail, not just a log.

## The verifier is the point

A claim is settled by the hardest check that can settle it, and short-circuits
upward.

| Tier | Check                                   | Cost       | Catches                           |
|------|-----------------------------------------|------------|-----------------------------------|
| 0    | does the cited unit exist at this version? | pure code  | fabricated citations, stale drift |
| 1    | does the support quote appear verbatim? | pure code  | "unit exists but does not say it" |
| 2    | does the quote entail the claim?        | model call | abstractive overreach             |

Most of the work happens in code. The one soft check is fenced behind two
deterministic ones and only runs on the claims that actually need it. A claim
whose text is its quote never reaches the model at all.

## Two modes: a certainty knob

The support quote is checked verbatim in **both** modes. That is the
anti-fabrication guarantee and it never turns off. The mode only sets how far a
claim may restate its quote.

- **verbatim** the claim must equal its quote. Deterministic, no model call, the
  assertion is literally source text. Maximum certainty, and the right setting
  when another agent is composing this harness and you want to deny it any room
  to drift.
- **gist** the claim may restate the quote, and the entailment tier decides
  whether the restatement is faithful. Synthesis, anchored to spans.

This knob exists for a reason. Verbatim is an attractor: under retry pressure a
generator will collapse toward quoting to avoid getting dropped, and synthesis
quietly dies. Making the abstraction budget an explicit setting stops that
collapse from happening by accident.

## Domain-specific agents, one spine

The loop, the verifier, and the report never change. A domain is three small
plugins: how you load and address a source, how you generate claims, and how you
judge entailment. Swap those, keep the skeleton.

| Domain                    | Source loader          | A "unit" is              | Status  |
|---------------------------|------------------------|--------------------------|---------|
| Markdown docs             | file or directory read | a heading path           | working |
| Video and talks           | transcript API         | a timestamped segment    | stub    |
| Product docs / Confluence | live page read         | a heading path           | stub    |
| Legal research            | supplied case text     | a case plus a pinpoint   | sketch  |
| Code and its docs         | repo read              | a file line range        | sketch  |

Because the output is already verified, a grounding domain is a callable that
other agents can invoke and trust without re-checking. That is the composability
payoff: a small, single-purpose agent that hands back claims with receipts
attached, so the caller can build on them instead of re-auditing them. The
harness is designed to be a node in a larger agent graph, not just a tool a human
runs.

A couple of concrete uses:

- Point it at a folder of engineering docs so an agent answering questions has to
  cite the current page, not an ingested and now-stale copy.
- Point it at the cases a researcher has already selected so the summary cannot
  misquote or misattribute anything within those sources.

## Hooking it in

The harness is a callable. `run(...)` returns a `Result` with `.grounded` (kept
claims, each with its citation and quote), `.dropped` (verdicts with reasons),
and `.report` (the audit trail). Four common ways to wire it in:

**1. In-process, as a library.** The base case. Write the three adapters, call
`run`, use the grounded claims.

```python
from grounding import run, Mode
from adapters.youtube import YouTubeTranscriptLoader
from my_app.seams import AnthropicGenerator, AnthropicEntailer

result = run(
    uri="https://youtu.be/...",
    ask="summarize the argument",
    loader=YouTubeTranscriptLoader(),
    generator=AnthropicGenerator(),
    entailment=AnthropicEntailer(),
    mode=Mode.GIST,
)
for claim in result.grounded:
    print(claim.text, "->", f"{claim.citation}: {claim.support_quote!r}")
```

**2. As a tool an agent calls.** Instead of letting an agent summarize sources
freely, give it a `ground` tool. It gets back only grounded claims plus their
receipts, so it has to build on cited material rather than invent.

```python
def ground(uri: str, ask: str) -> str:
    result = run(uri, ask, loader, generator, entailment, mode=Mode.GIST)
    return result.report   # cited claims in, nothing ungrounded escapes

# register `ground` as a tool in your agent framework
```

**3. As a CI gate.** Drift as a build failure. Run the harness over generated
content (docs answers, release notes, a RAG reply) and fail the build if
anything will not ground. Verbatim mode when you want zero interpretation.

```python
import sys
result = run(doc_uri, ask, loader, generator, entailment, mode=Mode.VERBATIM)
if result.dropped:
    print(result.report)
    sys.exit(1)   # the pipeline stops on an ungrounded claim
```

**4. As an MCP server.** Wrap `run` behind an MCP tool so any agent can call the
harness as a connector. This is the recursive-composition path: a small,
single-purpose grounding node other agents invoke and trust, because its output
is pre-verified.

## What is binding, and what is not

A verifier that self-enforces everywhere is a verifier nobody can compose. This
harness draws the line deliberately, and it is worth being explicit about where.

**Binding, inside the loop.** These are mechanical. There is no override flag, no
"the model seemed confident," no discretion.

- A claim that does not ground is not in `.grounded`. Full stop.
- `Claim` is a frozen type that *requires* a citation and a support quote. A claim
  with no receipt cannot structurally exist.
- The extractive fast path is derived from `text == quote`, not read off a label
  the generator supplies. The generator cannot talk its way into skipping a tier.
- The seam contracts are enforced at runtime (`grounding/contract.py`). A loader
  that returns an unstamped source, duplicate unit ids, or no addressable units
  raises `SeamViolation` at the boundary. A generator that omits a citation or a
  quote raises too: that is a malformed claim, which is a bug in the adapter, not
  a bad claim to be quietly dropped. Dropping it would hide a broken seam behind a
  normal-looking report.

**Not binding, at the edges.** These are the caller's job, and pretending
otherwise would be dishonest.

- Nothing forces a host to call the harness, or to honor `.grounded` rather than
  ignoring it and printing whatever a model said elsewhere. The harness cannot
  bind its host.
- The entailment tier is a model call. It is fenced (narrow span, single judgment,
  deterministic pre-filter, logged verdict) but it is not deterministic.
- Whether an ungrounded claim is *fatal* is a deployment decision, not a library
  decision.

**Where the teeth come from.** The harness supplies the judgment; the host supplies
the bindingness by wiring that judgment to something that fails. In practice that
is an exit code:

```python
result = run(uri, ask, loader, generator, entailment, mode=Mode.VERBATIM)
if result.dropped:
    print(result.report)
    sys.exit(1)          # now an ungrounded claim stops the pipeline
```

That nonzero exit is what turns a report into a gate when it is wired into a CI
step or an agent hook. This is the same division a compiler makes: it reports
errors mechanically, and it does not decide whether your pipeline blocks on them.

## Honest boundary

The tiers prove a claim matches the doc it cites. They do not prove you fetched
the right docs, or that a relevant source was missed. That is a
retrieval-coverage problem, it stays soft, and it is the line between "grounded"
and "correct." The entailment tier is itself a model call and can be wrong; the
design fences that risk with a narrow span, a single judgment, a deterministic
pre-filter, and a logged verdict, but it does not erase it.

Stating that boundary is deliberate. A grounding tool that oversells what it
guarantees is the exact failure it is supposed to prevent.

## Layout

```
grounding/     the harness. spine only, zero third-party dependencies.
               model, seams (the Protocols), contract (runtime seam
               enforcement), verify, loop.
adapters/      EXAMPLE implementations of the seams. Not part of the harness and
               not shipped with it. A host project writes its own.
               markdown       a real SourceLoader over .md files on disk
               model_seams    the model-backed Generator and EntailmentChecker.
                              Prompts and parsing live here, once.
               claude_code    transport: the Claude Code CLI. No API key.
               anthropic_api  transport: the Anthropic API. Needs a key.
               extractive_gen a Generator that uses no model at all
               fakes          in-memory doubles, used by the tests
               youtube        stub
               confluence     stub
tests/         the falsifiable eval, tests that a lying adapter is refused, and
               tests of the markdown adapter against real files.
examples/      demo.py (planted claims) and ground_markdown.py (real files).
```

The boundary is the point: another app depends on `grounding` and gets only the
spine. Adapters live in the repo as examples of how to satisfy the seams, not as
things you are forced to ship.

## Quickstart

```
python examples/ground_markdown.py tests/fixtures/sample.md   # offline, no model
python examples/ground_markdown.py README.md --generator claude --mode gist
python examples/ground_markdown.py README.md --generator api  # needs a key
python examples/demo.py                                       # the planted eval
pytest -q                                                     # the whole suite
```

The default generator uses no model, so its claims ground by construction and the
run is fully offline. `--generator claude` drives the Claude Code CLI as a
subprocess and needs no API key, only the `claude` binary on PATH. `--generator
api` uses the Anthropic API and needs `ANTHROPIC_API_KEY`. The last two reach a
real model, so both can be wrong, which is the only setting in which the drops
mean anything.

There is something fitting about the CLI transport: the harness's stochastic step
is performed by another agent, invoked as a subprocess, with a deterministic
verifier standing between them. One harness calling another.

`ground_markdown.py` runs the full loop against a real markdown file with no
network and no API key: a real loader splitting the document into heading-path
units, a real verifier, and a report where every kept claim carries the section
and the verbatim span it rests on. It exits non-zero when anything fails to
ground, so it drops straight into CI or an agent hook.

`demo.py` is the falsifiable eval: six planted claims against a known doc, three
grounded and three planted-false, each dying at a different tier. If a false
claim survives, the harness is broken and the tier tells you where.

## Status

The spine (model, tiered verifier, contract enforcement, loop, report) is
complete and covered by the test suite: the planted-claim eval proves the
verifier discriminates, and the contract tests prove a shape-correct but
contract-violating adapter is refused at the boundary.

The adapters are examples, not the product. `markdown` and `extractive_gen` are
real and run end to end against files on disk, which is what proves the seam
contract holds outside a fixture: the loader handles fenced code, empty parent
sections, and repeated headings, and a test shows a claim grounded against one
version of a document dropping at Tier 1 once that document changes. `youtube`
and `confluence` are stubs showing the shape a host would fill in.

The model-backed seams are real. `model_seams` holds the prompts, the parsing, and
the Generator and EntailmentChecker; `claude_code` and `anthropic_api` are thin
transports over it. Keeping one implementation and two transports is the same
instinct the harness applies to everything else: a second copy of a source of truth
is a bug waiting to happen.

Their parsing and contract compliance are tested against a stubbed transport. The
subprocess invocation and the HTTP call themselves are NOT covered by the tests, so
they are the first things to check if something misbehaves. The Claude Code CLI's
flags drift between releases, so that invocation is isolated in `ClaudeCodeCLI` and
changeable in one line.

`extractive_gen` and `SubsetEntailer` remain as offline stand-ins. The former quotes
sentences verbatim, so its claims ground by construction; the latter is a word
overlap test rather than a judgment. They exist so the whole loop runs with no
network at all, which is what keeps the eval falsifiable by anyone who clones this.

Open work, and the rules that keep the deterministic tiers deterministic, are in
[AGENTS.md](./AGENTS.md).
