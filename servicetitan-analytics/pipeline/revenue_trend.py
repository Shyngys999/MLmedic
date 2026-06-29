"""Stage 1 (when): monthly revenue with YoY change, to locate the drop in time.

A step change at one month points to a discrete event (a CSR/technician left, a
lead source died, a price change, a competitor entered). A gradual slide points
to something structural (market, capacity, competition). Pulls the last `months`
of invoices and prints month, revenue, and YoY %; flags the largest step down.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

import duckdb

import config
from servicetitan import ServiceTitanClient, accounting

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("revenue_trend")


def _month_key(iso_ts: str | None) -> str | None:
    if not iso_ts:
        return None
    return iso_ts[:7]  # YYYY-MM


def monthly_revenue(client: ServiceTitanClient, start: date, end: date) -> dict[str, float]:
    buckets: dict[str, float] = defaultdict(float)
    for inv in accounting.list_invoices(client, start, end):
        key = _month_key(inv.get("invoiceDate") or inv.get("createdOn"))
        if key:
            buckets[key] += accounting.invoice_total(inv)
    return dict(buckets)


def main(months: int = 25) -> None:
    import pandas as pd

    today = date.today()
    start = (today.replace(day=1).replace(year=today.year - (months // 12 + 1)))
    client = ServiceTitanClient()
    rev = monthly_revenue(client, start, today)

    keys = sorted(rev)
    rows = []
    for k in keys:
        year, mon = k.split("-")
        prev_key = f"{int(year) - 1}-{mon}"
        prev = rev.get(prev_key)
        yoy = (rev[k] - prev) / prev * 100 if prev else None
        rows.append({"month": k, "revenue": rev[k], "yoy_pct": yoy})

    df = pd.DataFrame(rows)
    print(df.to_string(index=False))

    yoy_series = df.dropna(subset=["yoy_pct"])
    if not yoy_series.empty:
        worst = yoy_series.loc[yoy_series["yoy_pct"].idxmin()]
        print(f"\nLargest YoY drop: {worst['month']} ({worst['yoy_pct']:.1f}%) "
              f"— inspect what changed around then.")

    con = duckdb.connect(str(config.DUCKDB_PATH))
    con.execute("DROP TABLE IF EXISTS revenue_trend")
    con.execute("CREATE TABLE revenue_trend AS SELECT * FROM df", {"df": df})
    con.close()


if __name__ == "__main__":
    main()
