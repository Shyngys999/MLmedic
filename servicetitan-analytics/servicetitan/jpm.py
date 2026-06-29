"""Job Planning & Management: jobs and appointments.

Used for the run-rate (scheduled -> completed) and conversion stages, and to
segment by business unit / job type. Jobs are the unit at which an opportunity
is converted into sold revenue.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterator

from .client import ServiceTitanClient

_JOBS = "/jpm/v2/tenant/{tenant}/jobs"
_APPOINTMENTS = "/jpm/v2/tenant/{tenant}/appointments"
_JOB_TYPES = "/jpm/v2/tenant/{tenant}/job-types"


def list_jobs(
    client: ServiceTitanClient,
    start: date,
    end: date,
    by: str = "created",
    extra: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield jobs. `by` selects the date filter: 'created' or 'completed'."""
    if by == "completed":
        params = {
            "completedOnOrAfter": f"{start.isoformat()}T00:00:00Z",
            "completedBefore": f"{end.isoformat()}T23:59:59Z",
        }
    else:
        params = {
            "createdOnOrAfter": f"{start.isoformat()}T00:00:00Z",
            "createdBefore": f"{end.isoformat()}T23:59:59Z",
        }
    params.update(extra or {})
    yield from client.paginate(_JOBS, params)


def list_appointments(
    client: ServiceTitanClient,
    start: date,
    end: date,
    extra: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    params = {
        "startsOnOrAfter": f"{start.isoformat()}T00:00:00Z",
        "startsBefore": f"{end.isoformat()}T23:59:59Z",
    }
    params.update(extra or {})
    yield from client.paginate(_APPOINTMENTS, params)


def job_types(client: ServiceTitanClient) -> dict[Any, dict[str, Any]]:
    """Map job-type id -> job-type record (for naming / segmentation)."""
    return {jt["id"]: jt for jt in client.paginate(_JOB_TYPES)}
