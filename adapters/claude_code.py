"""Model seams reached through the Claude Code CLI. No API key required.

This shells out to the `claude` binary in headless mode, so the work is done by
whatever subscription that binary is already authenticated with.

There is something fitting about this transport: the harness's stochastic step is
performed by another agent, invoked as a subprocess, with a deterministic verifier
standing between them. One harness calling another.

VERSION DRIFT WARNING
The Claude Code CLI's flags change between releases. Everything version-specific
lives in `ClaudeCodeCLI` below, so if the invocation differs on your version you
change it in exactly one place. Verify against the current Claude Code docs. If
`claude -p` does not read the prompt from stdin on your version, construct it with
`stdin_prompt=False` to pass the prompt as an argument instead.

WHAT TO EXPECT ON FIRST RUN
Unlike `extractive_gen`, this generator CAN be wrong, which is the entire reason
the verifier exists. Expect drops. The most likely early friction is Tier 1: the
model paraphrases a quote or normalizes whitespace inside it, and the verbatim
match fails. That is the verifier doing its job, and the bounded retry loop gets a
chance to repair it. If it proves noisy, tighten the prompt. Do not loosen the
tier: it is the tier the whole thesis rests on.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from .model_seams import ModelEntailer, ModelGenerator, ModelSeamError

# Kept as an alias so callers can catch one error type across transports.
ClaudeCodeError = ModelSeamError


class ClaudeCodeCLI:
    """One headless `claude` invocation. The only version-specific code here."""

    def __init__(
        self,
        argv: tuple[str, ...] = ("claude", "-p"),
        stdin_prompt: bool = True,
        timeout: int = 120,
    ) -> None:
        self._argv = argv
        self._stdin_prompt = stdin_prompt
        self._timeout = timeout

    def ask(self, prompt: str) -> str:
        binary = self._argv[0]
        if shutil.which(binary) is None:
            raise ModelSeamError(
                f"{binary!r} is not on PATH. Install the Claude Code CLI, or point "
                "this transport at another command via argv=."
            )

        cmd = list(self._argv) if self._stdin_prompt else [*self._argv, prompt]
        try:
            proc = subprocess.run(
                cmd,
                input=prompt if self._stdin_prompt else None,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise ModelSeamError(f"{binary} timed out after {self._timeout}s") from e

        if proc.returncode != 0:
            raise ModelSeamError(
                f"{binary} exited {proc.returncode}: {proc.stderr.strip()[:400]}"
            )
        return proc.stdout


class ClaudeCodeGenerator(ModelGenerator):
    """ModelGenerator over the CLI transport."""

    def __init__(self, cli: Optional[ClaudeCodeCLI] = None, **kw) -> None:
        super().__init__(transport=cli or ClaudeCodeCLI(), **kw)


class ClaudeCodeEntailer(ModelEntailer):
    """ModelEntailer over the CLI transport."""

    def __init__(self, cli: Optional[ClaudeCodeCLI] = None) -> None:
        super().__init__(transport=cli or ClaudeCodeCLI())
