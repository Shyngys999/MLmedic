"""Stage 0 sanity check: authenticate and pull a tiny slice from each resource.

Run this first. It verifies the OAuth token + ST-App-Key work, that pagination
returns rows, and prints record counts you can eyeball against the ServiceTitan
UI for the same window.
"""
from __future__ import annotations

import itertools
import logging

import config
from servicetitan import ServiceTitanClient
from servicetitan import accounting, crm, jpm, telecom

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("check_access")


def _count(iterator, cap: int = 50) -> tuple[int, bool]:
    """Count up to `cap` items; second value says whether more remain."""
    items = list(itertools.islice(iterator, cap + 1))
    return min(len(items), cap), len(items) > cap


def main() -> None:
    current, year_ago = config.get_periods()
    log.info("Current period:  %s", current)
    log.info("Year-ago period: %s", year_ago)

    client = ServiceTitanClient()
    log.info("Authenticating…")
    client._ensure_token()  # noqa: SLF001 - intentional smoke test
    log.info("Token OK against %s", client.api_base)

    s, e = current.start, current.end
    checks = {
        "calls":    telecom.list_calls(client, s, e),
        "bookings": crm.list_bookings(client, s, e),
        "leads":    crm.list_leads(client, s, e),
        "jobs":     jpm.list_jobs(client, s, e, by="completed"),
        "invoices": accounting.list_invoices(client, s, e),
    }
    print(f"\nSample counts for {current} (capped at 50):")
    for name, it in checks.items():
        try:
            n, more = _count(it)
            print(f"  {name:10s}: {n}{'+' if more else ''}")
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  {name:10s}: ERROR — {exc}")


if __name__ == "__main__":
    main()
