"""Memberships: recurring-revenue base and renewals."""
from __future__ import annotations

from typing import Any, Iterator

from .client import ServiceTitanClient

_MEMBERSHIPS = "/memberships/v2/tenant/{tenant}/memberships"


def list_memberships(
    client: ServiceTitanClient,
    extra: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    yield from client.paginate(_MEMBERSHIPS, extra or {})
