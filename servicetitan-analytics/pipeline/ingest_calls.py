"""Stage 3.1: pull call metadata for both periods and download recordings.

Writes a `calls` table to DuckDB (metadata + local audio path) and saves audio
files under data/recordings/<period>/<call_id>.<ext>. Idempotent: existing
audio files are skipped so re-runs only fetch what is missing.
"""
from __future__ import annotations

import logging

import duckdb

import config
from servicetitan import ServiceTitanClient, telecom

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ingest_calls")


def _recording_id(call: dict):
    rec = call.get("recording") or call.get("recordingId") or call.get("voiceMail")
    if isinstance(rec, dict):
        return rec.get("id")
    return rec


def ingest_period(client: ServiceTitanClient, period) -> list[dict]:
    out_dir = config.RECORDINGS_DIR / period.name
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for call in telecom.list_calls(client, period.start, period.end):
        call_id = call.get("id")
        rec_id = _recording_id(call)
        audio_path = None
        if rec_id is not None:
            audio_path = out_dir / f"{call_id}.mp3"
            if not audio_path.exists():
                try:
                    client.download(telecom.recording_url(client, rec_id), audio_path)
                except Exception as exc:  # noqa: BLE001
                    log.warning("call %s: recording download failed: %s", call_id, exc)
                    audio_path = None
        rows.append({
            "call_id": call_id,
            "period": period.name,
            "direction": call.get("direction"),
            "created_on": call.get("createdOn") or call.get("receivedOn"),
            "duration": call.get("duration"),
            "agent_id": _nested(call, "agent", "id"),
            "agent_name": _nested(call, "agent", "name"),
            "campaign_id": _nested(call, "campaign", "id"),
            "campaign_name": _nested(call, "campaign", "name"),
            "is_call_lead": telecom.is_call_lead(call),
            "has_booking": bool(call.get("booking") or call.get("bookingId")),
            "audio_path": str(audio_path) if audio_path else None,
        })
    log.info("%s: %d calls (%d with audio)",
             period.name, len(rows), sum(1 for r in rows if r["audio_path"]))
    return rows


def _nested(d: dict, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def main() -> None:
    import pandas as pd

    current, year_ago = config.get_periods()
    client = ServiceTitanClient()
    rows = ingest_period(client, current) + ingest_period(client, year_ago)
    con = duckdb.connect(str(config.DUCKDB_PATH))
    con.execute("DROP TABLE IF EXISTS calls")
    con.execute("CREATE TABLE calls AS SELECT * FROM df", {"df": pd.DataFrame(rows)})
    con.close()
    log.info("Wrote %d call rows to DuckDB", len(rows))


if __name__ == "__main__":
    main()
