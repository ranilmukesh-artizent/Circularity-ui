# Regenerating the demo videos

**Current video: `../circularity-cxo-demo.mp4` (CXO cut, 7:27).** Build it with `record_cxo.py` + `narration_cxo.json` + `card_close_cxo.html`; `tts.py` and `mux.py` take `--src narration_cxo.json`. The steps, take checks (`check/frames.py`, `check/strip.py`) and gotchas are in [`../HANDOFF.md`](../HANDOFF.md) section 9.

The rest of this file is about the earlier 4:11 cut (`record.py`, `narration.json`), which no longer matches the UI.

# Regenerating the demo video

`../circularity-agentic-demo.mp4` (4:11, 1440 × 900, H.264/AAC) and `../circularity-agentic-demo.srt` are generated from the live UI in `index.html`, following the ten steps of `../../user-flow.svg`. Nothing is edited by hand.

**Order:** title · executive briefing · plug and play (Connection Fabric, an agent diagnosing the stale market feed, Workflow Studio drafting a pipeline from plain words) · step 1 Asset & Product Intelligence · steps 2–4 Treatment Intelligence (evidence snapshot, all pathways, why this outcome, what-if with *Demand cancelled*) · step 5 submit and approval · steps 6–9 the live run board (agents, models, acknowledgements) · step 10 reconcile and learn · close. Finance confirms the outcome off camera; sign-ins are cut and replaced by a role caption.

1. **Voice:** Kokoro TTS (`kokoro-onnx`, model and voices Apache 2.0), voice `am_michael`, speed 0.94. Install `kokoro-onnx soundfile` into a venv on a short path (Windows long-path limits) and download `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the kokoro-onnx GitHub release `model-files-v1.0`. Run `tts.py` with that venv: it renders each line of `narration.json` to `audio/<id>.wav` and writes `durations.json`. The candidate voices are in `../voice-samples/`.
2. **Screen:** `pip install playwright imageio-ffmpeg`, then `python -m playwright install ffmpeg`. `record.py` drives the real app in the installed Chrome at 1440 × 900 from a fresh browser state, with a cursor and eased scrolls. It writes `rec/*.webm` and `timeline.json` (line start times and the segments to cut).
3. **Mix:** `python mux.py OUT.mp4` cuts the marked segments, places each line at its start time, encodes H.264/AAC and writes the `.srt`.

Do not use the Piper voices `lessac`, `ryan` or `hfc_*` for client material: their licences are non-commercial.

Full handoff (concerns, file paths, iteration history, gotchas): [`../HANDOFF.md`](../HANDOFF.md).
