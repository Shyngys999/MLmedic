"""Marketing: campaigns and lead sources (for segmenting the funnel by source)."""
from __future__ import annotations

from typing import Any

from .client import ServiceTitanClient

_CAMPAIGNS = "/marketing/v2/tenant/{tenant}/campaigns"


def campaigns(client: ServiceTitanClient) -> dict[Any, dict[str, Any]]:
    """Map campaign id -> campaign record (name, category, lead source)."""
    return {c["id"]: c for c in client.paginate(_CAMPAIGNS)}
