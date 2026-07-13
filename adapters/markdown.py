"""A real SourceLoader over markdown files. No network, no API key.

This is the first adapter here that touches real data, and its job is to prove
the seam contract survives contact with something messier than a fixture dict.

A unit is a HEADING PATH: the section body under `## Setup` inside `# Guide`
becomes the unit `Guide > Setup`. That is the addressable thing a claim cites,
so a citation points at a specific section of a specific document, and Tier 0
can resolve it.

Design notes worth reading, because each one exists to satisfy a contract rule:

* Headings inside fenced code blocks are NOT headings. A `# comment` in a bash
  block would otherwise open a bogus section and swallow the code under it.
* Sections with no direct body text are skipped. A heading that only contains
  subheadings has nothing to quote, and `check_source` rejects blank unit text.
* Duplicate heading paths get a disambiguating suffix. `check_source` rejects
  duplicate unit ids, because Tier 0 resolves a citation by id and an ambiguous
  address is not an address. Real documents repeat headings (two `### Example`
  sections under different parents already differ, but two under the SAME parent
  do not), so this is not hypothetical.
* version_hash is the sha256 of the raw bytes actually read. Read live, hash what
  you read. That is what makes the audit trail honest.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from grounding.model import Source, Unit

_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_PREAMBLE = "(preamble)"


def _sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading_path, body) pairs.

    Returns section bodies only. A heading's own text is not part of its body;
    its children are separate units.
    """
    stack: list[str] = []
    current_path = _PREAMBLE
    body: list[str] = []
    out: list[tuple[str, str]] = []
    in_fence = False

    def flush() -> None:
        joined = "\n".join(body).strip()
        if joined:                      # blank sections are dropped, not emitted
            out.append((current_path, joined))
        body.clear()

    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            body.append(line)
            continue

        m = None if in_fence else _ATX.match(line)
        if m is None:
            body.append(line)
            continue

        flush()
        level = len(m.group(1))
        title = m.group(2).strip()
        del stack[level - 1:]           # pop to the parent of this level
        stack.append(title)
        current_path = " > ".join(stack)

    flush()
    return out


def _dedupe(sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Make heading paths unique. Required: duplicate unit ids are a SeamViolation."""
    seen: dict[str, int] = {}
    out: list[tuple[str, str]] = []
    for path, body in sections:
        n = seen.get(path, 0) + 1
        seen[path] = n
        out.append((path if n == 1 else f"{path} ({n})", body))
    return out


class MarkdownLoader:
    """SourceLoader for a markdown file or a directory of them.

    Directory mode prefixes each unit id with the file's path relative to the
    root, so `docs/setup.md :: Guide > Auth` stays unambiguous across files.
    """

    def load(self, uri: str) -> Source:
        root = Path(uri)

        if root.is_dir():
            files = sorted(p for p in root.rglob("*.md") if p.is_file())
            if not files:
                # Let the contract speak: a source with nothing to cite is a
                # SeamViolation, raised by check_source with a clear message.
                return Source(uri=str(root), version_hash=_hash(b""), units=())
            raw = b""
            sections: list[tuple[str, str]] = []
            for f in files:
                data = f.read_bytes()
                raw += data
                rel = f.relative_to(root).as_posix()
                for path, body in _sections(data.decode("utf-8", errors="replace")):
                    sections.append((f"{rel} :: {path}", body))
        else:
            raw = root.read_bytes()
            sections = _sections(raw.decode("utf-8", errors="replace"))

        units = tuple(Unit(id=pid, text=body) for pid, body in _dedupe(sections))
        return Source(uri=str(root), version_hash=_hash(raw), units=units)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
