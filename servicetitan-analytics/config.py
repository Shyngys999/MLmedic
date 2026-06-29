"""Central configuration: API credentials, analysis periods (YoY), paths.

Reads from environment / .env with sensible defaults. The two analysis periods
are the "current" window and the same window one year earlier (YoY) so that
HVAC seasonality is cancelled out when decomposing the revenue drop.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
DB_DIR = ROOT / "db"
DATA_DIR = ROOT / "data"
RECORDINGS_DIR = DATA_DIR / "recordings"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
DUCKDB_PATH = DB_DIR / "analytics.duckdb"

for _d in (DB_DIR, DATA_DIR, RECORDINGS_DIR, TRANSCRIPTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# --- ServiceTitan ---------------------------------------------------------
_ENV = os.getenv("ST_ENV", "production").lower()
_IS_INTEGRATION = _ENV in ("integration", "int", "sandbox")

AUTH_BASE = (
    "https://auth-integration.servicetitan.io" if _IS_INTEGRATION
    else "https://auth.servicetitan.io"
)
API_BASE = (
    "https://api-integration.servicetitan.io" if _IS_INTEGRATION
    else "https://api.servicetitan.io"
)

ST_CLIENT_ID = os.getenv("ST_CLIENT_ID", "")
ST_CLIENT_SECRET = os.getenv("ST_CLIENT_SECRET", "")
ST_APP_KEY = os.getenv("ST_APP_KEY", "")
ST_TENANT_ID = os.getenv("ST_TENANT_ID", "")


# --- Transcription / LLM --------------------------------------------------
TRANSCRIBE_BACKEND = os.getenv("TRANSCRIBE_BACKEND", "deepgram").lower()
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "claude-fable-5")


# --- Analysis periods -----------------------------------------------------
@dataclass(frozen=True)
class Period:
    name: str
    start: date
    end: date  # inclusive

    def __str__(self) -> str:
        return f"{self.name} [{self.start} … {self.end}]"


def _parse(d: str | None) -> date | None:
    return datetime.strptime(d, "%Y-%m-%d").date() if d else None


def _last_full_month(today: date) -> tuple[date, date]:
    first_this = today.replace(day=1)
    end_prev = first_this.replace(day=1)  # placeholder
    # last day of previous month = day before first of this month
    from datetime import timedelta
    last_prev = first_this - timedelta(days=1)
    start_prev = last_prev.replace(day=1)
    return start_prev, last_prev


def _shift_year(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # Feb 29
        return d.replace(year=d.year + years, day=28)


def get_periods(today: date | None = None) -> tuple[Period, Period]:
    """Return (current, year_ago) analysis periods."""
    today = today or date.today()
    start = _parse(os.getenv("CURRENT_PERIOD_START"))
    end = _parse(os.getenv("CURRENT_PERIOD_END"))
    if not (start and end):
        start, end = _last_full_month(today)
    current = Period("current", start, end)
    year_ago = Period("year_ago", _shift_year(start, -1), _shift_year(end, -1))
    return current, year_ago


def require_servicetitan() -> None:
    missing = [
        k for k, v in {
            "ST_CLIENT_ID": ST_CLIENT_ID,
            "ST_CLIENT_SECRET": ST_CLIENT_SECRET,
            "ST_APP_KEY": ST_APP_KEY,
            "ST_TENANT_ID": ST_TENANT_ID,
        }.items() if not v
    ]
    if missing:
        raise RuntimeError(
            "Missing ServiceTitan credentials: " + ", ".join(missing)
            + ". Fill them in .env (see .env.example)."
        )
