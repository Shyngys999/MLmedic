"""Stage 3.3: structured analysis of each diarized transcript with Claude.

Claude returns a strict JSON object per call (enforced via a tool schema):
call reason, outcome, why-not-booked, CSR behaviour checklist, sentiment,
red flags, and a missed-opportunity flag. These rows power the aggregation
(booking rate & missed-opportunity rate by CSR / source / reason, YoY).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("analyze_calls")

ANALYSIS_TOOL = {
    "name": "record_call_analysis",
    "description": "Record the structured analysis of a single phone call.",
    "input_schema": {
        "type": "object",
        "properties": {
            "call_reason": {
                "type": "string",
                "enum": [
                    "new_appointment", "existing_customer", "billing",
                    "price_shopping", "emergency", "spam_or_recruiting", "other",
                ],
            },
            "outcome": {
                "type": "string",
                "enum": ["booked", "not_booked", "callback_promised"],
            },
            "not_booked_reason": {
                "type": "string",
                "enum": [
                    "price", "scheduling", "just_shopping",
                    "csr_could_not_help", "customer_hung_up", "n/a",
                ],
            },
            "csr_greeted": {"type": "boolean"},
            "csr_asked_for_booking": {"type": "boolean"},
            "csr_captured_contact": {"type": "boolean"},
            "csr_handled_objection": {"type": "boolean"},
            "csr_offered_membership": {"type": "boolean"},
            "customer_sentiment": {
                "type": "string", "enum": ["positive", "neutral", "negative"],
            },
            "missed_opportunity": {
                "type": "boolean",
                "description": "Bookable intent that the CSR failed to convert.",
            },
            "red_flags": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
        "required": [
            "call_reason", "outcome", "not_booked_reason", "csr_greeted",
            "csr_asked_for_booking", "csr_captured_contact", "csr_handled_objection",
            "csr_offered_membership", "customer_sentiment", "missed_opportunity",
            "red_flags", "summary",
        ],
    },
}

SYSTEM = (
    "You are a call-QA analyst for an HVAC/plumbing company. You receive a "
    "diarized transcript of one inbound phone call. Speaker labels are numeric; "
    "infer which speaker is the CSR (company) and which is the customer. Judge "
    "strictly from the transcript. Call record_call_analysis exactly once."
)


def _format_transcript(data: dict) -> str:
    return "\n".join(f"Speaker {t['speaker']}: {t['text']}" for t in data.get("turns", []))


def analyze_one(client, transcript: dict) -> dict | None:
    msg = client.messages.create(
        model=config.ANALYSIS_MODEL,
        max_tokens=1024,
        system=SYSTEM,
        tools=[ANALYSIS_TOOL],
        tool_choice={"type": "tool", "name": "record_call_analysis"},
        messages=[{"role": "user", "content": _format_transcript(transcript)}],
    )
    for block in msg.content:
        if block.type == "tool_use" and block.name == "record_call_analysis":
            return block.input
    return None


def main() -> None:
    import anthropic
    import pandas as pd

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    con = duckdb.connect(str(config.DUCKDB_PATH))
    transcripts = con.execute(
        "SELECT call_id, period, transcript_path FROM transcripts"
    ).fetchall()

    rows = []
    for call_id, period, path in transcripts:
        try:
            data = json.loads(Path(path).read_text())
            result = analyze_one(client, data)
            if result is None:
                continue
            result["red_flags"] = json.dumps(result.get("red_flags", []), ensure_ascii=False)
            rows.append({"call_id": call_id, "period": period, **result})
        except Exception as exc:  # noqa: BLE001
            log.warning("call %s: analysis failed: %s", call_id, exc)

    con.execute("DROP TABLE IF EXISTS call_analysis")
    con.execute("CREATE TABLE call_analysis AS SELECT * FROM df", {"df": pd.DataFrame(rows)})
    con.close()
    log.info("Analyzed %d transcripts via %s", len(rows), config.ANALYSIS_MODEL)


if __name__ == "__main__":
    main()
