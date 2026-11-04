"""Authenticated actor resolved from a session cookie and the membership store."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Actor:
    identity_id: UUID
    scope: str
    tenant_id: UUID | None
    permissions: frozenset[str]

    def has(self, permission: str) -> bool:
        return permission in self.permissions
