"""In-memory vote list for HITLManager. It never returns a bare bool."""

from __future__ import annotations

from typing import Any


class ReplayVoteAdapter:
    def __init__(self, votes: list[dict[str, Any]]):
        self.votes = list(votes)

    async def notify(self, request) -> list[dict[str, Any]]:
        return list(self.votes)
