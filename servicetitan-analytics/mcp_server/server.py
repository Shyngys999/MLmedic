"""Read-only MCP server for ServiceTitan + the analytics DuckDB.

Thin wrapper over code that already exists in this project — there is no new API
access code here:
  * servicetitan/client.py::ServiceTitanClient   (GET-only OAuth2 client)
  * pipeline/build_funnel.py                      (funnel + LMDI decomposition)
  * pipeline/revenue_trend.py                     (monthly YoY)

Security posture (see docs/mcp_security.md):
  * NO write tools, NO generic api passthrough — the underlying client only
    issues GET to the API (POST is used solely for the token endpoint).
  * query_analytics opens DuckDB read_only=True and rejects non-SELECT SQL.
  * Pair this with a ServiceTitan API app that has VIEW-only scopes (:r), so the
    credentials physically cannot mutate tenant data.
"""
from __future__ import annotations

import itertools
import sys
from datetime import date, datetime
from pathlib import Path

# Allow `import config`, `servicetitan`, `pipeline` when launched as a module.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import config  # noqa: E402
from servicetitan import ServiceTitanClient  # noqa: E402
from servicetitan import accounting, crm, jpm, telecom  # noqa: E402

mcp = FastMCP("servicetitan")

_client: ServiceTitanClient | None = None


def client() -> ServiceTitanClient:
    global _client
    if _client is None:
        _client = ServiceTitanClient()  # validates creds, GET-only
    return _client


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _take(it, limit: int) -> list[dict]:
    return list(itertools.islice(it, max(1, min(limit, 1000))))


# --- analytics tools (reuse the pipeline) ---------------------------------
@mcp.tool()
def funnel_yoy() -> dict:
    """YoY revenue funnel (current vs same month last year) with an exact additive
    LMDI decomposition of the revenue change. The most negative contributor is the
    funnel stage where the revenue drop lives."""
    from pipeline.build_funnel import collect_funnel, lmdi_decompose
    from dataclasses import asdict

    cur_p, prev_p = config.get_periods()
    c = client()
    cur, prev = collect_funnel(c, cur_p), collect_funnel(c, prev_p)
    return {
        "current_period": str(cur_p),
        "year_ago_period": str(prev_p),
        "current": asdict(cur) | {"booking_rate": cur.booking_rate,
                                  "conversion_rate": cur.conversion_rate,
                                  "average_ticket": cur.average_ticket},
        "year_ago": asdict(prev) | {"booking_rate": prev.booking_rate,
                                    "conversion_rate": prev.conversion_rate,
                                    "average_ticket": prev.average_ticket},
        "revenue_delta": cur.revenue - prev.revenue,
        "decomposition": lmdi_decompose(cur, prev),
    }


@mcp.tool()
def revenue_trend(months: int = 25) -> list[dict]:
    """Monthly revenue with YoY % over the last `months`, to locate WHEN the
    decline started (a step change points to a discrete event)."""
    from pipeline.revenue_trend import monthly_revenue

    today = date.today()
    start = today.replace(day=1).replace(year=today.year - (months // 12 + 1))
    rev = monthly_revenue(client(), start, today)
    out = []
    for k in sorted(rev):
        y, m = k.split("-")
        prev = rev.get(f"{int(y) - 1}-{m}")
        out.append({"month": k, "revenue": rev[k],
                    "yoy_pct": (rev[k] - prev) / prev * 100 if prev else None})
    return out


# --- raw read tools (bounded) ---------------------------------------------
@mcp.tool()
def list_calls(start: str, end: str, limit: int = 100) -> list[dict]:
    """List inbound/outbound calls created in [start, end] (YYYY-MM-DD). Read-only."""
    return _take(telecom.list_calls(client(), _d(start), _d(end)), limit)


@mcp.tool()
def list_jobs(start: str, end: str, by: str = "completed", limit: int = 100) -> list[dict]:
    """List jobs in [start, end] by 'created' or 'completed' date. Read-only."""
    return _take(jpm.list_jobs(client(), _d(start), _d(end), by=by), limit)


@mcp.tool()
def list_invoices(start: str, end: str, limit: int = 100) -> list[dict]:
    """List invoices in [start, end] (YYYY-MM-DD). Read-only."""
    return _take(accounting.list_invoices(client(), _d(start), _d(end)), limit)


@mcp.tool()
def list_bookings(start: str, end: str, limit: int = 100) -> list[dict]:
    """List bookings created in [start, end] (YYYY-MM-DD). Read-only."""
    return _take(crm.list_bookings(client(), _d(start), _d(end)), limit)


# --- read-only query over the analytics DuckDB ----------------------------
@mcp.tool()
def query_analytics(sql: str) -> list[dict]:
    """Run a read-only SELECT against the analytics DuckDB built by the pipeline
    (tables: funnel, revenue_decomposition, calls, call_analysis, agg_by_csr,
    agg_by_source, agg_not_booked_reasons, revenue_trend). Only SELECT/WITH is
    permitted; the connection is opened read-only."""
    import duckdb

    from .safe_sql import ensure_select_only

    safe = ensure_select_only(sql)
    if not config.DUCKDB_PATH.exists():
        return [{"error": "analytics DB not built yet — run the pipeline first"}]
    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    try:
        return con.execute(safe).df().to_dict(orient="records")
    finally:
        con.close()


if __name__ == "__main__":
    mcp.run()
