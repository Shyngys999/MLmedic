"""Guard for the read-only DuckDB query tool.

Defence in depth: the DuckDB connection is opened read_only=True, AND we reject
any statement that is not a single SELECT/WITH. This blocks DDL/DML
(DROP/UPDATE/INSERT/ATTACH/COPY/PRAGMA/...) even before it reaches the engine.
"""
from __future__ import annotations

import re

_ALLOWED_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
# tokens that must never appear (word-boundary) even inside an otherwise-SELECT
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|pragma|"
    r"install|load|export|import|truncate|replace|vacuum|set|call|grant|revoke)\b",
    re.IGNORECASE,
)


class UnsafeQuery(ValueError):
    pass


def ensure_select_only(sql: str) -> str:
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise UnsafeQuery("Multiple statements are not allowed.")
    if not _ALLOWED_START.match(stripped):
        raise UnsafeQuery("Only SELECT/WITH queries are allowed.")
    if _FORBIDDEN.search(stripped):
        raise UnsafeQuery("Query contains a forbidden (non-read) keyword.")
    return stripped
