"""The read-only SQL guard for the MCP query_analytics tool must allow SELECT/WITH
and reject every DDL/DML or multi-statement attempt."""
import sys
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:  # allow running standalone without pytest
    pytest = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_server.safe_sql import UnsafeQuery, ensure_select_only


_BAD = [
    "DROP TABLE funnel",
    "UPDATE funnel SET revenue=0",
    "INSERT INTO funnel VALUES (1)",
    "DELETE FROM calls",
    "SELECT * FROM funnel; DROP TABLE funnel",
    "ATTACH 'x.db' AS y",
    "COPY funnel TO 'out.csv'",
    "PRAGMA database_list",
    "select * from funnel union all delete from calls",
]


def test_allows_select_and_with():
    assert ensure_select_only("SELECT * FROM funnel")
    assert ensure_select_only("  with t as (select 1) select * from t ")


if pytest is not None:
    @pytest.mark.parametrize("bad", _BAD)
    def test_rejects_mutations(bad):
        with pytest.raises(UnsafeQuery):
            ensure_select_only(bad)


if __name__ == "__main__":
    test_allows_select_and_with()
    for q in _BAD:
        try:
            ensure_select_only(q)
            raise SystemExit(f"FAIL: did not reject {q!r}")
        except UnsafeQuery:
            pass
    print("ALL SAFE_SQL TESTS PASSED")
