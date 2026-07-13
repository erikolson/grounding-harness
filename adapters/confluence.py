"""SourceLoader for Confluence pages. STUB.

A unit is a heading path. Reads the page LIVE so version_hash reflects the
current page, not an ingested copy. Version control as source of truth,
enforced.
"""
from __future__ import annotations

import hashlib

from grounding.model import Source, Unit


class ConfluenceLoader:
    def load(self, uri: str) -> Source:
        # page = confluence.get_page_by_url(uri)          # live read
        # units = tuple(Unit(id=path, text=body) for path, body in _sections(page))
        # version = hashlib.sha256(page["body"].encode()).hexdigest()
        # return Source(uri=uri, version_hash=version, units=units)
        raise NotImplementedError("wire in your Confluence client here")
