# Regenerating the demo video

`../circularity-agentic-demo.mp4` (5:13, 1440 × 900, H.264/AAC) and its subtitles `../circularity-agentic-demo.srt` are generated from the live UI in `index.html`. Nothing is edited by hand.

1. **Voice:** Piper TTS with `en_GB-cori-high`, a public-domain voice (LibriVox; see `VOICE_MODEL_CARD.txt`). Install `piper-tts` into a venv on a short path (Windows long-path limits) and run `python -m piper.download_voices en_GB-cori-high`. Render each line of `narration.json` to `audio/<id>.wav` and write `durations.json` (`{id: seconds}`).
2. **Screen:** `pip install playwright imageio-ffmpeg`, then `python -m playwright install ffmpeg`. `record.py` drives the real app in the installed Chrome at 1440 × 900 from a fresh browser state. It shows a cursor, starts each narration line at its action and writes `rec/*.webm` and `timeline.json` (line start times and the sign-in segments to cut).
3. **Mix:** `python mux.py OUT.mp4` cuts the sign-in segments, places every line at its start time, encodes H.264/AAC and writes the `.srt`.

Lines and pacing are in `narration.json` and `record.py`. The title, journey and close cards are `card_*.html`, made in the app's palette with its logo. Do not use the Piper voices `lessac`, `ryan` or `hfc_*` for client material: their licences are non-commercial.
