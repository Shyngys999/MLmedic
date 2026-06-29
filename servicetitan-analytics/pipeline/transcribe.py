"""Stage 3.2: transcribe call recordings with speaker diarization.

Diarization matters: we need to separate the CSR from the customer to judge
booking behaviour. Two backends:
  * deepgram  — hosted, nova model + diarize=true (simplest/cheapest)
  * whisperx  — self-hosted (Whisper + pyannote diarization)

Output: one JSON per call in data/transcripts/<period>/<call_id>.json with a
diarized turn list, plus a `transcripts` table (call_id, period, text path).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("transcribe")


def transcribe_deepgram(audio_path: Path) -> dict:
    from deepgram import DeepgramClient, PrerecordedOptions

    dg = DeepgramClient(config.DEEPGRAM_API_KEY)
    with open(audio_path, "rb") as fh:
        source = {"buffer": fh.read()}
    options = PrerecordedOptions(
        model="nova-2", smart_format=True, diarize=True, punctuate=True
    )
    resp = dg.listen.prerecorded.v("1").transcribe_file(source, options)
    return _deepgram_to_turns(resp.to_dict())


def _deepgram_to_turns(resp: dict) -> dict:
    alt = resp["results"]["channels"][0]["alternatives"][0]
    words = alt.get("words", [])
    turns, cur_spk, buf = [], None, []
    for w in words:
        spk = w.get("speaker", 0)
        if spk != cur_spk and buf:
            turns.append({"speaker": cur_spk, "text": " ".join(buf)})
            buf = []
        cur_spk = spk
        buf.append(w.get("punctuated_word", w["word"]))
    if buf:
        turns.append({"speaker": cur_spk, "text": " ".join(buf)})
    return {"full_text": alt.get("transcript", ""), "turns": turns}


def transcribe_whisperx(audio_path: Path) -> dict:
    import whisperx  # type: ignore

    device = "cpu"
    model = whisperx.load_model("large-v3", device, compute_type="int8")
    audio = whisperx.load_audio(str(audio_path))
    result = model.transcribe(audio)
    align_model, meta = whisperx.load_align_model(result["language"], device)
    result = whisperx.align(result["segments"], align_model, meta, audio, device)
    diarize = whisperx.DiarizationPipeline(device=device)
    result = whisperx.assign_word_speakers(diarize(audio), result)
    turns = [
        {"speaker": seg.get("speaker", "?"), "text": seg["text"].strip()}
        for seg in result["segments"]
    ]
    return {"full_text": " ".join(t["text"] for t in turns), "turns": turns}


_BACKENDS = {"deepgram": transcribe_deepgram, "whisperx": transcribe_whisperx}


def main() -> None:
    import pandas as pd

    backend = _BACKENDS.get(config.TRANSCRIBE_BACKEND)
    if backend is None:
        raise SystemExit(f"Unknown TRANSCRIBE_BACKEND={config.TRANSCRIBE_BACKEND}")

    con = duckdb.connect(str(config.DUCKDB_PATH))
    calls = con.execute(
        "SELECT call_id, period, audio_path FROM calls WHERE audio_path IS NOT NULL"
    ).fetchall()

    rows = []
    for call_id, period, audio_path in calls:
        out_dir = config.TRANSCRIPTS_DIR / period
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{call_id}.json"
        if not dest.exists():
            try:
                result = backend(Path(audio_path))
                dest.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            except Exception as exc:  # noqa: BLE001
                log.warning("call %s: transcription failed: %s", call_id, exc)
                continue
        rows.append({"call_id": call_id, "period": period, "transcript_path": str(dest)})

    con.execute("DROP TABLE IF EXISTS transcripts")
    con.execute("CREATE TABLE transcripts AS SELECT * FROM df", {"df": pd.DataFrame(rows)})
    con.close()
    log.info("Transcribed %d calls via %s", len(rows), config.TRANSCRIBE_BACKEND)


if __name__ == "__main__":
    main()
