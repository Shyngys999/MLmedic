"""CRM: bookings and leads (top of the funnel after the call is handled)."""
from __future__ import annotations

from datetime import date
from typing import Any, Iterator

from .client import ServiceTitanClient

_BOOKINGS = "/crm/v2/tenant/{tenant}/bookings"
_LEADS = "/crm/v2/tenant/{tenant}/leads"


def list_bookings(
    client: ServiceTitanClient,
    start: date,
    end: date,
    extra: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    params = {
        "createdOnOrAfter": f"{start.isoformat()}T00:00:00Z",
        "createdBefore": f"{end.isoformat()}T23:59:59Z",
    }
    params.update(extra or {})
    yield from client.paginate(_BOOKINGS, params)


def list_leads(
    client: ServiceTitanClient,
    start: date,
    end: date,
    extra: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    params = {
        "createdOnOrAfter": f"{start.isoformat()}T00:00:00Z",
        "createdBefore": f"{end.isoformat()}T23:59:59Z",
    }
    params.update(extra or {})
    yield from client.paginate(_LEADS, params)
