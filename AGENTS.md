# AGENTS.md

Instructions for any coding agent working in this repo, and for a human picking it
up cold. The spine is done, tested, and not the thing that needs work. What remains
is listed at the bottom.

The rules below are not style preferences. Several of them exist because this repo
is a verifier, and a verifier that quietly relaxes its own checks is worse than no
verifier at all. Read the house rules before changing anything under `grounding/`.

## House rules

- No em-dashes anywhere in code, comments, or docs.
- Strict honesty. Do not claim a check does more than it does. The entailment
  tier is a model call and can be wrong. This harness reduces unsupported claims
  and surfaces its own decisions. It does not guarantee truth. Keep the language
  at that level, in code comments as much as in the README.
- **Do not weaken the deterministic tiers to make more claims pass.** Tier 0 and
  Tier 1 are pure code, and they are the reason any of this is worth anything. If
  claims are being dropped for a silly reason, fix the PROMPT, not the tier. The
  moment you start normalizing away differences the verifier considers real, you
  are negotiating with the verifier and the guarantee is gone.
- Small, reviewable commits.

## Architecture you must preserve

- `grounding/` is the harness. It has zero third-party dependencies and it stays
  that way. Nothing domain-specific goes in here.
- `grounding/model.py` types: Source, Unit, Claim, Verdict, Mode, Tier. Do not
  change these signatures without a good reason.
- `grounding/verify.py` the tiered verifier. Tier 0 structural, Tier 1 verbatim
  quote, Tier 2 entailment, short-circuiting upward. The extractive fast path is
  DERIVED from `text == quote`, never read off a label the generator supplies. Do
  not reintroduce a claim-kind field; the generator does not get to declare which
  tier its own output skips.
- `grounding/contract.py` runtime enforcement of the seams. The Protocols in
  `seams.py` are static-only, so these checks are what make the seams binding at
  run time. An adapter that breaks one raises `SeamViolation` at the boundary.
- `grounding/loop.py` Constrain, Generate, Verify, Feedback, plus the report.
- Modes: VERBATIM (the claim must equal its quote, so Tier 2 is unreachable) and
  GIST (the claim may restate, and entailment gates it). The support quote is
  checked verbatim in BOTH. That check never turns off.
- `adapters/` is examples, not product. It is not packaged and not shipped.

## What is already done

- The spine, with 37 passing tests.
- `adapters/markdown.py`, a real SourceLoader over .md files. Handles fenced code
  blocks, empty parent sections, and duplicate heading paths.
- `adapters/model_seams.py`, the model-backed Generator and EntailmentChecker.
  Prompts and parsing live here ONCE, with two thin transports over it:
  `claude_code.py` (subprocess, no API key) and `anthropic_api.py` (needs a key).
- `adapters/extractive_gen.py`, a Generator with no model at all, so the whole
  loop runs offline.
- `examples/ground_markdown.py`, the end-to-end runner. Exits non-zero on any
  ungrounded claim, so it drops straight into CI or an agent hook.

## Open work, roughly in order of value

1. **Markdown syntax forces needless Tier 2 calls.** Observed in a real run: the
   source says `**both**`, the model's claim text says `both`, so `text != quote`
   and a claim that should have been settled in code fell through to the model.
   Fix in the GENERATE prompt in `model_seams.py`: when a claim is just the span,
   its text must be the span character for character, markdown and all. Do not fix
   this by stripping syntax before the Tier 1 comparison.

2. **A second real SourceLoader.** `adapters/youtube.py` and
   `adapters/confluence.py` are stubs. YouTube: a unit is a transcript segment,
   its id is the segment index, hash the fetched segments into `version_hash`,
   read live and do not cache. Either one proves the spine flexes across domains,
   which is the composability claim.

3. **A `python -m grounding` entry point.** `examples/ground_markdown.py` already
   does the job but is markdown-specific. A module entry point that takes a loader
   by name would make the harness usable without writing a script.

4. **Prompt tuning against real drops.** Run `--generator claude` against real
   documents and look at what falls out at Tier 1. Each drop is either a prompt
   problem or a genuine catch. Sort them.

## Out of scope for now

- Cross-source conflict reconciliation (two sources disagreeing with each other).
- Retrieval or source selection. The caller hands in the URI. Note that this is
  also the honest limit of what the harness proves: the tiers show a claim matches
  the doc it CITES, not that the right doc was fetched.
- Claim ranking or importance.
- Per-claim mode override. Mode is per-run.

## Definition of done for any change

- `pytest -q` green.
- `python examples/ground_markdown.py tests/fixtures/sample.md` exits 0.
- No em-dashes. No weakened deterministic tiers. No claim-kind label.
- `grounding/` still imports nothing outside the standard library.
