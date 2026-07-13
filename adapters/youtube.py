"""SourceLoader for YouTube transcripts. STUB.

A unit is a transcript segment; its id is the segment index, so a citation
points at a specific span of speech. Reads live and hashes the fetched segments
into version_hash. Requires the optional `youtube` extra.
"""
from __future__ import annotations

import hashlib

from grounding.model import Source, Unit


class YouTubeTranscriptLoader:
    def load(self, uri: str) -> Source:
        # from youtube_transcript_api import YouTubeTranscriptApi
        # video_id = _parse_id(uri)
        # segments = YouTubeTranscriptApi.get_transcript(video_id)
        # units = tuple(Unit(id=f"seg:{i}", text=s["text"])
        #               for i, s in enumerate(segments))
        # version = hashlib.sha256(repr(segments).encode()).hexdigest()
        # return Source(uri=uri, version_hash=version, units=units)
        raise NotImplementedError("wire in youtube_transcript_api here")
