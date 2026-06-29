"""Accounting: invoices (revenue) and payments.

Invoice subtotals drive the revenue numerator and the average-ticket metric.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterator

from .client import ServiceTitanClient

_INVOICES = "/accounting/v2/tenant/{tenant}/invoices"


def list_invoices(
    client: ServiceTitanClient,
    start: date,
    end: date,
    extra: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield invoices by invoice date within [start, end]."""
    params = {
        "invoicedOnOrAfter": f"{start.isoformat()}T00:00:00Z",
        "invoicedBefore": f"{end.isoformat()}T23:59:59Z",
    }
    params.update(extra or {})
    yield from client.paginate(_INVOICES, params)


def invoice_total(invoice: dict[str, Any]) -> float:
    """Best-effort revenue figure from an invoice record (subtotal, ex-tax)."""
    for key in ("subTotal", "subtotal", "total"):
        if invoice.get(key) is not None:
            try:
                return float(invoice[key])
            except (TypeError, ValueError):
                pass
    return 0.0
