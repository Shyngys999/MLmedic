"""Stage 3.4: aggregate the per-call analysis into actionable cuts.

Joins call_analysis with the call metadata (CSR, campaign) and reports, YoY:
  * booking rate and missed-opportunity rate by CSR and by lead source,
  * top reasons calls were not booked,
  * CSR-behaviour adherence (asked-for-booking, offered-membership, …).
Prints tables and writes them back to DuckDB as agg_* tables.
"""
from __future__ import annotations

import logging

import duckdb

import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("aggregate_calls")

QUERIES = {
    "agg_by_csr": """
        SELECT c.agent_name AS csr, a.period,
               COUNT(*)                                            AS analyzed_calls,
               AVG(CASE WHEN a.outcome='booked' THEN 1.0 ELSE 0 END)        AS booking_rate,
               AVG(CASE WHEN a.missed_opportunity THEN 1.0 ELSE 0 END)      AS missed_opp_rate,
               AVG(CASE WHEN a.csr_asked_for_booking THEN 1.0 ELSE 0 END)   AS asked_for_booking,
               AVG(CASE WHEN a.csr_offered_membership THEN 1.0 ELSE 0 END)  AS offered_membership
        FROM call_analysis a LEFT JOIN calls c USING (call_id, period)
        GROUP BY 1, 2 ORDER BY a.period, booking_rate
    """,
    "agg_by_source": """
        SELECT c.campaign_name AS lead_source, a.period,
               COUNT(*)                                              AS analyzed_calls,
               AVG(CASE WHEN a.outcome='booked' THEN 1.0 ELSE 0 END)         AS booking_rate,
               AVG(CASE WHEN a.missed_opportunity THEN 1.0 ELSE 0 END)       AS missed_opp_rate
        FROM call_analysis a LEFT JOIN calls c USING (call_id, period)
        GROUP BY 1, 2 ORDER BY a.period, booking_rate
    """,
    "agg_not_booked_reasons": """
        SELECT period, not_booked_reason, COUNT(*) AS n
        FROM call_analysis
        WHERE outcome <> 'booked' AND not_booked_reason <> 'n/a'
        GROUP BY 1, 2 ORDER BY period, n DESC
    """,
}


def main() -> None:
    con = duckdb.connect(str(config.DUCKDB_PATH))
    for name, sql in QUERIES.items():
        df = con.execute(sql).df()
        con.execute(f"DROP TABLE IF EXISTS {name}")
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM df", {"df": df})
        print(f"\n=== {name} ===")
        print(df.to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
