"""Stage 1: build the YoY revenue funnel and decompose the revenue change.

The funnel is the multiplicative chain

    Revenue = L · b · r · c · t

    L = call leads (qualified inbound demand reaching us)
    b = booking rate          = bookings / call_leads
    r = run/completion rate   = completed_opportunity_jobs / bookings
    c = conversion rate       = converted_jobs / completed_opportunity_jobs
    t = average ticket        = revenue / converted_jobs

We compute every factor for the current and year-ago periods, then attribute the
revenue delta to each factor with an exact additive LMDI-I decomposition. The
factor(s) carrying the largest negative contribution are where the 20–30% drop
lives — that is what Stage 3 (call analysis) then drills into.

NOTE: field names below follow ServiceTitan's documented record shapes but MUST
be sanity-checked against the tenant (see verify()/check_access). Where a field
is ambiguous the helper degrades gracefully rather than crashing.
"""
from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass

import duckdb

import config
from servicetitan import ServiceTitanClient
from servicetitan import accounting, crm, jpm, telecom

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("build_funnel")


@dataclass
class Funnel:
    period: str
    inbound_calls: int
    call_leads: int
    answered_calls: int
    bookings: int
    completed_opportunity_jobs: int
    converted_jobs: int
    revenue: float

    # derived factors
    @property
    def answer_rate(self) -> float:
        return _safe_div(self.answered_calls, self.inbound_calls)

    @property
    def booking_rate(self) -> float:
        return _safe_div(self.bookings, self.call_leads)

    @property
    def run_rate(self) -> float:
        return _safe_div(self.completed_opportunity_jobs, self.bookings)

    @property
    def conversion_rate(self) -> float:
        return _safe_div(self.converted_jobs, self.completed_opportunity_jobs)

    @property
    def average_ticket(self) -> float:
        return _safe_div(self.revenue, self.converted_jobs)

    def factors(self) -> dict[str, float]:
        return {
            "call_leads (L)": float(self.call_leads),
            "booking_rate (b)": self.booking_rate,
            "run_rate (r)": self.run_rate,
            "conversion_rate (c)": self.conversion_rate,
            "average_ticket (t)": self.average_ticket,
        }


def _safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b else 0.0


# --- data collection ------------------------------------------------------
def collect_funnel(client: ServiceTitanClient, period) -> Funnel:
    s, e = period.start, period.end
    inbound = call_leads = answered = 0
    for call in telecom.list_calls(client, s, e):
        if str(call.get("direction", "")).lower() == "inbound":
            inbound += 1
            if str(call.get("callType", call.get("status", ""))).lower() not in (
                "abandoned", "missed", "voicemail"
            ):
                answered += 1
        if telecom.is_call_lead(call):
            call_leads += 1

    bookings = sum(1 for _ in crm.list_bookings(client, s, e))

    completed = converted = 0
    for job in jpm.list_jobs(client, s, e, by="completed"):
        if _is_opportunity(job):
            completed += 1
            if _is_converted(job):
                converted += 1

    revenue = sum(accounting.invoice_total(inv) for inv in accounting.list_invoices(client, s, e))

    return Funnel(
        period=period.name,
        inbound_calls=inbound,
        call_leads=call_leads,
        answered_calls=answered,
        bookings=bookings,
        completed_opportunity_jobs=completed,
        converted_jobs=converted,
        revenue=revenue,
    )


def _is_opportunity(job: dict) -> bool:
    # ServiceTitan flags demand/opportunity jobs; default True if unspecified.
    val = job.get("jobGenerationReasonType") or job.get("isOpportunity")
    if isinstance(val, bool):
        return val
    return True


def _is_converted(job: dict) -> bool:
    # A converted opportunity is a completed job whose subtotal clears the
    # job-type's "sold" threshold. Best-effort: positive subtotal or sold flag.
    if job.get("soldBy") or job.get("sold"):
        return True
    total = job.get("total") or job.get("subTotal") or 0
    try:
        return float(total) > 0
    except (TypeError, ValueError):
        return False


# --- LMDI-I additive decomposition ---------------------------------------
def lmdi_decompose(cur: Funnel, prev: Funnel) -> dict[str, float]:
    """Exact additive attribution of (cur.revenue - prev.revenue) to each factor.

    contribution_k = ((R1-R0)/(ln R1-ln R0)) · ln(f1_k / f0_k)
    Sum of contributions == R1 - R0 (within float error).
    """
    r1, r0 = cur.revenue, prev.revenue
    if r1 <= 0 or r0 <= 0:
        return {k: float("nan") for k in cur.factors()}
    log_mean = (r1 - r0) / (math.log(r1) - math.log(r0)) if r1 != r0 else r1
    out: dict[str, float] = {}
    f1, f0 = cur.factors(), prev.factors()
    for k in f1:
        if f1[k] > 0 and f0[k] > 0:
            out[k] = log_mean * math.log(f1[k] / f0[k])
        else:
            out[k] = float("nan")
    return out


# --- persistence + report -------------------------------------------------
def persist(funnels: list[Funnel], contributions: dict[str, float]) -> None:
    con = duckdb.connect(str(config.DUCKDB_PATH))
    con.execute("CREATE TABLE IF NOT EXISTS funnel AS SELECT * FROM (VALUES (NULL)) WHERE 1=0")
    con.execute("DROP TABLE IF EXISTS funnel")
    rows = []
    for f in funnels:
        d = asdict(f)
        d.update({
            "answer_rate": f.answer_rate,
            "booking_rate": f.booking_rate,
            "run_rate": f.run_rate,
            "conversion_rate": f.conversion_rate,
            "average_ticket": f.average_ticket,
        })
        rows.append(d)
    con.execute("CREATE TABLE funnel AS SELECT * FROM rows", {"rows": _to_df(rows)})
    con.execute("DROP TABLE IF EXISTS revenue_decomposition")
    decomp = [{"factor": k, "contribution_to_delta": v} for k, v in contributions.items()]
    con.execute(
        "CREATE TABLE revenue_decomposition AS SELECT * FROM df",
        {"df": _to_df(decomp)},
    )
    con.close()
    log.info("Saved funnel + revenue_decomposition to %s", config.DUCKDB_PATH)


def _to_df(rows: list[dict]):
    import pandas as pd
    return pd.DataFrame(rows)


def _print_report(cur: Funnel, prev: Funnel, contributions: dict[str, float]) -> None:
    print("\n=== YoY FUNNEL ===")
    print(f"{'metric':28s}{'year_ago':>14s}{'current':>14s}{'Δ %':>10s}")
    pairs = [
        ("inbound_calls", prev.inbound_calls, cur.inbound_calls),
        ("call_leads (L)", prev.call_leads, cur.call_leads),
        ("answer_rate", prev.answer_rate, cur.answer_rate),
        ("booking_rate (b)", prev.booking_rate, cur.booking_rate),
        ("bookings", prev.bookings, cur.bookings),
        ("run_rate (r)", prev.run_rate, cur.run_rate),
        ("conversion_rate (c)", prev.conversion_rate, cur.conversion_rate),
        ("average_ticket (t)", prev.average_ticket, cur.average_ticket),
        ("revenue", prev.revenue, cur.revenue),
    ]
    for name, p, c in pairs:
        delta = _safe_div(c - p, p) * 100 if p else float("nan")
        print(f"{name:28s}{p:>14,.2f}{c:>14,.2f}{delta:>9.1f}%")

    print("\n=== REVENUE Δ DECOMPOSITION (LMDI, additive) ===")
    total = cur.revenue - prev.revenue
    print(f"Total revenue change: {total:,.2f}\n")
    for k, v in sorted(contributions.items(), key=lambda kv: (math.isnan(kv[1]), kv[1])):
        share = _safe_div(v, total) * 100 if total else float("nan")
        print(f"  {k:24s}{v:>16,.2f}{share:>9.1f}% of Δ")
    print("\n→ Most negative contributor = stage to drill into with call analysis (Stage 3).")


def main() -> None:
    current, year_ago = config.get_periods()
    client = ServiceTitanClient()
    log.info("Collecting current funnel: %s", current)
    cur = collect_funnel(client, current)
    log.info("Collecting year-ago funnel: %s", year_ago)
    prev = collect_funnel(client, year_ago)
    contributions = lmdi_decompose(cur, prev)
    persist([prev, cur], contributions)
    _print_report(cur, prev, contributions)


if __name__ == "__main__":
    main()
