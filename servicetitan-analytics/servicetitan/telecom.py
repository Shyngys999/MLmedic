"""Telecom resource: inbound/outbound calls and their recordings.

Call leads (per ServiceTitan's Call Booking Rate definition) are inbound calls
that last >= 60 seconds OR are flagged as a lead. Each call references the
campaign / lead source, the agent (CSR), direction, duration, and the booking
it produced (if any), plus a recording id used to download the audio.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterator

from .client import ServiceTitanClient

_CALLS = "/telecom/v2/tenant/{tenant}/calls"


def list_calls(
    client: ServiceTitanClient,
    start: date,
    end: date,
    extra: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield calls created within [start, end] (end inclusive)."""
    params = {
        "createdOnOrAfter": f"{start.isoformat()}T00:00:00Z",
        "createdBefore": f"{end.isoformat()}T23:59:59Z",
    }
    params.update(extra or {})
    yield from client.paginate(_CALLS, params)


def recording_url(client: ServiceTitanClient, recording_id: Any) -> str:
    """Build the recording download URL for a given call recording id."""
    return (
        f"{client.api_base}/telecom/v2/tenant/{client.tenant_id}"
        f"/recording/{recording_id}"
    )


def is_call_lead(call: dict[str, Any], min_seconds: int = 60) -> bool:
    """ServiceTitan 'call lead': inbound and (>=60s OR explicitly marked lead)."""
    if str(call.get("direction", "")).lower() != "inbound":
        return False
    if call.get("isLead") or (call.get("leadCall") is not None):
        return True
    duration = call.get("duration") or 0
    if isinstance(duration, str) and ":" in duration:  # "HH:MM:SS"
        parts = [int(p) for p in duration.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        duration = parts[0] * 3600 + parts[1] * 60 + parts[2]
    return float(duration or 0) >= min_seconds
