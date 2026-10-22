# Handoff: the narrated demo video (Circularity, agentic decision layer)

**Read this first if you are continuing the demo-video work.** It covers only the video: what the user asked for, what exists, where every file is, how the video is generated, what went wrong along the way, and what is still open. Written 22 Oct 2026 at the end of the session that built it.

**Current deliverable:** [`circularity-agentic-demo.mp4`](circularity-agentic-demo.mp4) (4:11, 1440 × 900, H.264 30 fps, AAC 48 kHz mono, about 44 MB) with subtitles [`circularity-agentic-demo.srt`](circularity-agentic-demo.srt). Generated entirely from the app's own UI (`index.html` on branch `feature/live-run`) plus three HTML title cards, with a synthetic voice-over.

> **Legal review before any client sees it.** The video shows the product as a live, connected application although all data is synthetic and nothing is connected; vendor product names (SAP, IBM Maximo, Salesforce, Oracle, Manhattan, SafetyCulture, MasterControl …) appear on screen; model accuracy figures appear and only resale-price's are computed from data (the others are configured values). Kinective's Legal team should review the recording and narration before it is shown to a client or prospect.

---

## 1. What the user wants (all concerns, in the order they were given)

| # | Concern (user's words, paraphrased) | Where it stands |
|---|---|---|
| 1 | A demo video for a **Fortune 500, business-outcome** audience | Done; opens with outcome numbers, frames everything as value |
| 2 | Based on the PO's deck slide (`CVL - User Journey V1.1.pptx`, slide 3, one returned asset) and the PO's report (`IFS_Process_Inventory_and_DI_Pipeline_Fit 1.pdf`) | Done; both read, see section 3 |
| 3 | **Collaborate, not compete** with the big ERP/EAM/service suite in that report; convey it **indirectly**: never name the suite or anything related to it; **industry-agnostic** | Done; no suite or vendor is named in the narration or on the cards; message is "plugs into the systems you already run" |
| 4 | Portray Circularity as an **agentic-first decision intelligence platform** | Done; agents named on every board line, Ask panel tool calls, agent drafts |
| 5 | Show the flow with **visual modules: when and where to click** | First delivered as a written script ([`../VIDEO_SCRIPT_AGENTIC.md`](../VIDEO_SCRIPT_AGENTIC.md)), then as this generated video |
| 6 | **5–7 min max** | Superseded by #12 |
| 7 | "Can you create the video with voice-over fully from our own UI?" | Done; no slides, no external footage |
| 8 | Show **Connection Fabric** and **Workflow Studio with their AI capabilities** | Done (Source map, ✦ Diagnose on the stale market feed, Workflow Studio draft from plain words, Accept) |
| 9 | **Asset & Product Intelligence** was never covered; it is the most important part | Done (step 1 scene, smooth scroll through its sections) |
| 10 | **Treatment Intelligence**: full-page scroll, **Evidence snapshot** in detail, **Why this outcome**, **What-if**, each a quick 5–10 s scroll | Done |
| 11 | Remove the **Analytics** ending and the **Finance switch** at the end (felt useless) | Done; Finance confirms off camera (cut), no Analytics |
| 12 | **All under 5 minutes** | Done: 4:11 |
| 13 | Say we are **plug and play, not rip and replace** like similar products | Done (title card, scene 2 narration, close card) |
| 14 | **Deep, male, resonating voice that speaks like a top CEO** | User picked Kokoro **`am_michael`** from four samples (section 6) |
| 15 | Must cover every step of [`../user-flow.svg`](../user-flow.svg) (ten journey steps) with the updated agentic UX, evidence and logs | Done; mapping in section 5 |
| 16 | **Test well**, ask doubts, and **work faster, use as many resources as possible** | Every take checked frame by frame; questions asked once (voice, closed loop, length) |

Things the user said that were **not** received: they referred to notes sent with `/btw`; those never reached the session. Everything in the table above came from the conversation itself. If the user mentions `/btw` again, ask them to paste it.

---

## 2. Repository state (branch `feature/live-run`)

| Commit | What |
|---|---|
| `cc66992`, `4dd43eb`, `fee2663`, `f74055c` | The app work the video depends on: live wording, live run board, agentic board lines and model cards, MCP and Access as pages (see `docs/PLAN_LIVE_RUN_AND_LIVE_UI.md` sections 12–13 and CHANGES Updates 13–14) |
| `15a7561` | **The user's own commit**: added the deck, the PDF, `VIDEO_SCRIPT_AGENTIC.md`, the **first** video (5:13, Piper `cori` voice) and its pipeline, and the four voice samples |
| *(uncommitted)* | The **current** 4:11 video, its `.srt`, the updated pipeline (`record.py`, `narration.json`, `card_title.html`, `card_close.html`, `README.md`), deletion of `pipeline/VOICE_MODEL_CARD.txt` (Piper card, no longer used), the note in `VIDEO_SCRIPT_AGENTIC.md`, and this file |

Nothing is pushed. Do not push or merge without the user asking.

---

## 3. Source material and the positioning rule

| Source | Path | What was taken from it |
|---|---|---|
| PO deck | `CVL - User Journey V1.1.pptx` (repo root) | Slide 1 framework ring (Sense, Evaluate, Optimize, Execute, Learn); slide 2 three modules (Recover, Resolve, Reconcile) on one framework; slide 3 one returned asset: enterprise applications run steps 1–5, *Circularity decides*, enterprise applications carry it out, outcome comes back and Circularity learns. The deck's sample asset (gearbox, loan pool, $735) is **not** what the app shows; the video uses the app's record RT-1048 |
| PO report | `IFS_Process_Inventory_and_DI_Pipeline_Fit 1.pdf` (repo root; extracted text in the scratchpad as `ifs.txt`) | The positioning: *the suite runs the work; our DI decides what the work should be*. Read evidence from the system of record, recommend at the decision points it already has (return approval, disposition, material review board, asset disposal, remanufacture or teardown requisition), write the approved instruction back into its own processes, learn from outcomes. Keep the claim **narrow**: the best compliant next life for assets that **come back** (returned, end-of-lease, retired, surplus), not in-service repair/defer/replace (the suite has its own capability there). Differentiators: seven routes on one economic basis, eligibility gates before price, allocation across competing demand, external recovery evidence, learning by cost line. Phased adoption: shadow → one route → closed loop → portfolio |
| User flow | `docs/demo/user-flow.svg` | The ten journey steps the video must cover (section 5) |

**Hard rule for narration, cards and on-screen choices:** never say the suite's name or its products, and never imply a named vendor is connected for the viewer. Keep vendor names to what the app itself displays.

---

## 4. File map

### 4.1 In the repository

| Path | What it is |
|---|---|
| `docs/demo/video/circularity-agentic-demo.mp4` | **Current video** (4:11) |
| `docs/demo/video/circularity-agentic-demo.srt` | Subtitles, generated from the narration timing |
| `docs/demo/video/pipeline/record.py` | Playwright recorder: drives the real app, shows a cursor, starts each narration line at its action, marks segments to cut. Writes `rec/*.webm` and `timeline.json` next to itself |
| `docs/demo/video/pipeline/mux.py` | Cuts the marked segments, mixes every narration clip at its start time, encodes MP4 and writes the SRT. Usage: `python mux.py OUT.mp4` |
| `docs/demo/video/pipeline/narration.json` | The 18 narration lines (`c0` … `c8`), section 5 |
| `docs/demo/video/pipeline/card_title.html`, `card_journey.html`, `card_close.html` | Title, journey and close cards, 1440 × 900, app palette and fonts, app logo embedded as a data URI. `card_journey.html` is **not used** by the current cut (it was scene 2 in the first video) |
| `docs/demo/video/pipeline/tts.py` | Renders `narration.json` with Kokoro `am_michael` to `audio/*.wav` and writes `durations.json`; `--only c4d,c7` re-renders selected lines |
| `docs/demo/video/pipeline/README.md` | Short regeneration steps |
| `docs/demo/video/voice-samples/sample-*.mp3` | The four Kokoro male voices offered to the user (`am_michael` chosen) |
| `docs/demo/VIDEO_SCRIPT_AGENTIC.md` | The written recording script (first version, 6–7 min, manual recording). Its header points to the generated video; **its scene tables are older than the video** and do not include Connection Fabric, Workflow Studio, Asset Intelligence or the Treatment scroll |
| `docs/demo/DEMO_SCRIPT.md`, `VOICEOVER_SCRIPT.md` | Earlier live-demo scripts (pre-agent build); not used by the video |

### 4.2 Outside the repository (temporary; may be cleaned by the OS)

Session scratchpad: `C:\Users\ranilmj\AppData\Local\Temp\claude\C--repos-astra-prism-DI-ayush-ui-Circularity-ui\08dcd09d-2067-4cc6-a6d4-e10f79a1014b\scratchpad\` (below: `SCRATCH\`).

| Path | What it is |
|---|---|
| `SCRATCH\video2\` | **Working folder of the current video.** `record.py` (same as the repo copy), `main_part.py` (the scene script that was appended to the helper header to make `record.py`; keep in sync or ignore), `mux.py`, `narration.json`, `durations.json` (seconds per clip), `audio\c*.wav` (Kokoro clips), `rec\*.webm` (raw screen capture), `timeline.json` (clip start times, cut segments, raw total), `circularity-agentic-demo.mp4/.srt`, review images `rv0-2.png`, `chk\*.png`, `frames\*.png` |
| `SCRATCH\video\` | First video's working folder (Piper voice, 5:13). Kept for history |
| `SCRATCH\venv\vid\` | Python venv with `playwright` and `imageio-ffmpeg` (the ffmpeg binary is `SCRATCH\venv\vid\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe`) |
| `SCRATCH\venv\pdf\` | venv with `pypdf` (used once to extract the PDF) |
| `SCRATCH\ifs.txt` | Text of the PO report |
| `SCRATCH\h2\` | Second headless-test harness (its own Chrome profile) used to explore screens: `run.py`, `af_common.js`, `tour.js`, `flow.js`, `explore.js`, `ex2-ex5.js` (selector checks), outputs `tour.txt`, `flow.txt` |
| `C:\Users\ranilmj\AppData\Local\Temp\cvlv\` | **Voice venv on a short path** (Windows long-path limit breaks `onnxruntime` installs under the scratchpad). Has `kokoro-onnx`, `soundfile`, `piper-tts` |
| `C:\Users\ranilmj\AppData\Local\Temp\cvlv\kokoro\kokoro-v1.0.onnx`, `voices-v1.0.bin` | Kokoro model and voice pack (from the `kokoro-onnx` GitHub release `model-files-v1.0`) |
| `C:\Users\ranilmj\AppData\Local\Temp\cvlv\voices\` | Piper voices (`en_GB-cori-high` public domain; `lessac` and `ryan` are **non-commercial, do not use**) |
| `C:\Users\ranilmj\AppData\Local\ms-playwright\ffmpeg-1013\` | Playwright's own ffmpeg, needed for `record_video_dir` (`python -m playwright install ffmpeg`) |
| `C:\Program Files\Google\Chrome\Application\chrome.exe` | The browser Playwright drives (`executable_path`), no Playwright browser download needed |

If the temp folders are gone, rebuild them with section 7.

---

## 5. The current cut (4:11)

Times are in the final video. Each row is one narration clip; role captions appear after each cut.

| Time | Clip | Scene and clicks | User-flow step |
|---|---|---|---|
| 0:02 | `c0` | Title card: *Circularity · The agentic decision layer for every asset that comes back*; footer *Plug and play · No rip and replace · Agent-first · Human-governed* | — |
| 0:15 | `c1` | Sign in `exec` (cut) → **Home** briefing and key figures ($2,433,569 recovered, $1,741,546 avoided, value at risk with owner) | outcome |
| 0:33 | `c2a` | Sign in `admin` (cut) → **Integration › Source map**: *systems keep owning their transactions*, 19 sources, health tiles, scroll to the tiles. "Plug and play. No rip and replace." | plug and play |
| 0:51 | `c2b` | **✦ Diagnose** on *Market pricing* → Ask panel; typed *Why is the Market pricing feed stale, and how do I fix it?* → diagnosis (token expired, refresh and re-sync) | plug and play (AI) |
| 1:05 | `c2c` | **Workflow studio** tab → top-bar **Ask** → typed *Draft a workflow that ingests inspection results from SafetyCulture into the condition model every 15 minutes* → card *Workflow draft · Ingest · SafetyCulture (AI draft)*, 6 ghost steps, checks 0 errors → **Accept all as a new draft** | plug and play (AI) |
| 1:21 | `c3a` | Sign in `ops` (Planner, cut) → **Product** → Returned assets → **MTR-2041** link → **Asset & Product Intelligence**; eased scroll to *Retrieved from enterprise systems*, *Lease end, return and transit* | 1 Supply evidence |
| 1:37 | `c3b` | Scroll *Diagnostic condition* → *Inspection findings* (cost inputs) → *Lifecycle evidence timeline* | 1 |
| 1:50 | `c4a` | **Actions ▾ › Open decision analysis** → Treatment Intelligence, decision packet → **Evidence snapshot** drawer, slow scroll inside it (source, file, record, fetch time, checksum per item) | 2 (evidence) |
| 2:05 | `c4b` | **Full analysis** → scroll to *All pathways · 7 routes · 6 eligible · 1 withheld* | 2 Build alternatives |
| 2:15 | `c4c` | Scroll *Why this outcome* → *Predicted outcomes and comparison* (Redeploy $9,600, $4,800 ahead of selling) | 3 Predict outcomes |
| 2:29 | `c4d` | Scroll *What-if and edge cases* → preset **Demand cancelled**: *Redeploy · not eligible · Sell + buy for Site 3 would now rank first by $4,800*; reset after the line | 4 Optimize plan |
| 2:39 | `c5a` | Scroll *Next best action* → bottom bar **Submit RT-1048 for review** | 5 Plan approval |
| 2:52 | `c5b` | Sign in `approver` (cut) → search `RT-1048` → **Evaluate treatments** → **Approve…** → approval card (agent-drafted rationale, limit, raw instruction) → tick evidence box → **Approve and send instruction** (APR-2026-10-3161) | 5 |
| 3:06 | `c6a` | **Process orchestration**: live run board plays at 1× (agents, tool → system, audit IDs, counters) | 6 Send instruction |
| 3:20 | `c6b` | **Skip to now** → box **6 Decide** model cards (XGBoost, LightGBM, transformer ranker, MAE line) → box **5** (vision CNN line) | (3–4 models) |
| 3:32 | `c6c` | Box **8 Execute** → **Check for the next acknowledgement →** three times (order acknowledged automatically, then work order, transfer, actual result) | 7–9 |
| (cut) | — | Off camera: sign in `finance` → board → **Confirm the outcome →** → sign in `approver` → board → open box 10 | 9 |
| 3:46 | `c7` | Board box **10**: *Predicted $9,600, actual $9,230 (−$370); 3 learning records* → **Open RT-1048** → Full analysis → scroll to **Reconcile and learn** cost-line table with the model per line | 10 Reconcile and learn |
| 4:00 | `c8` | Close card: *Your systems run the work. Circularity makes sure it's the right work.* Shadow mode → One route → Closed loop → Portfolio; *Plug and play · Agent-first · Human-governed* | — |

Cut segments in the raw capture (seconds): `[15.09–20.77]` initial load and exec sign-in, `[34.94–43.17]` admin, `[90.3–98.47]` planner, `[185.66–194.01]` approver, `[255.99–294.64]` off-camera Finance confirmation and return. Raw capture 5:19, final 4:11.

---

## 6. Voice

| Voice | Engine | Licence | Status |
|---|---|---|---|
| **`am_michael`** (US, warm, measured) | Kokoro 82M via `kokoro-onnx`, speed 0.94, 0.15 s tail silence | Apache 2.0 (model and voices) | **In use, chosen by the user** |
| `am_fenrir`, `bm_george`, `bm_fable` | Kokoro | Apache 2.0 | Offered as samples (`voice-samples/`) |
| `en_GB-cori-high` | Piper | Public domain (LibriVox) | Used in the first video |
| `en_US-lessac-high`, `en_US-ryan-high`, `hfc_*` | Piper | **Non-commercial** (Blizzard 2013 research licence; CC BY-NC-SA) | **Do not use** for client material |
| Microsoft David / Zira (SAPI) | Windows | — | Too robotic; not used |

All synthesis is local; the script never leaves the machine. Online TTS services were deliberately not used. Pronunciation workarounds in `narration.json`: "E R P" for ERP, "audit I D", amounts spelled out ("ninety-six hundred dollars").

---

## 7. How to regenerate (end to end)

```bash
# 0. App: branch feature/live-run, index.html unchanged since f74055c (the video depends on its board, model cards and MCP/Access pages)

# 1. Voice venv (short path!) and Kokoro model, if missing
python -m venv "%TEMP%\cvlv"; "%TEMP%\cvlv\Scripts\python" -m pip install kokoro-onnx soundfile
# download kokoro-v1.0.onnx and voices-v1.0.bin from github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0 into %TEMP%\cvlv\kokoro

# 2. Render narration (writes audio/<id>.wav and durations.json next to tts.py; --only c4d,c7 re-renders some lines)
"%TEMP%\cvlv\Scripts\python" docs/demo/video/pipeline/tts.py

# 3. Recorder venv
python -m venv vid; vid\Scripts\python -m pip install playwright imageio-ffmpeg; vid\Scripts\python -m playwright install ffmpeg

# 4. Record (≈ 5.5 min real time; prints each clip's start, WARN lines for cosmetic cursor misses, and the final length)
cd docs/demo/video/pipeline   # or a working copy; record.py writes rec/ and timeline.json next to itself
vid\Scripts\python record.py

# 5. Mix
vid\Scripts\python mux.py circularity-agentic-demo.mp4
```

`record.py` needs `durations.json`, `audio/` is needed by `mux.py`; both are generated, not committed. `record.py` resets the app by clearing `localStorage` at the start, so every take starts from the seeded state (RT-1048 awaiting approval).

### 7.1 How each take was verified (do this every time)

1. The recorder log: every clip printed, no traceback; `WARN point …` lines are cosmetic (the cursor could not point at something) and acceptable.
2. **No overlapping lines:** for consecutive clips, `start + duration ≤ next start` (after shifting by the cuts).
3. **Frames:** extract a frame at each clip's start + 1 s and end − 0.4 s from the MP4 (ffmpeg `-ss`), tile them into contact sheets (Pillow) and look at every one: the screen must show what the line says (for example the what-if must show *Not eligible* while `c4d` plays; box 10 must be open with the $9,230 result while `c7` plays).
4. `ffmpeg -i` shows the expected duration, H.264 video and AAC audio.

---

## 8. `record.py` in detail

**Helpers (class `Rec`):** `say(k)` logs a clip start and returns its end time; `until(t, pad)` waits for the line to finish; `point(sel)` glides the cursor to an element (non-fatal if missing, saves `missN.png`); `click(sel)` points, ripples and clicks (fatal if missing); `type(sel, text, delay)`; `scroll_to(sel)`; `sign_in(user)` / `sign_out()`; `switch(user, role)` = sign out + sign in recorded as a **cut** and followed by a role caption pill; `cut(coro)` records any off-camera segment; `open_case(id)` = search box → result → **Evaluate treatments** in the drawer; `nav(group)` clicks a sidebar group. Module-level helpers: `glide_to(R, heading_text, ms, offset)` eased scroll to a heading inside `#view`; `glide_in(R, '#drawer', fraction, ms)` scrolls the drawer's scroll container; `to_top(page)`; `lr_settled(R)` waits until the run board's playback reaches its end (`S.lr.t >= S.lr.total`).

**Cursor:** injected with `context.add_init_script` (a fixed `#__cur` circle with eased `left/top`, plus a yellow ripple); its position persists across page loads via `sessionStorage`.

**Gotchas found while building (each cost a re-take):**

| Problem | Fix in `record.py` |
|---|---|
| Search result opens a **quick-view drawer**, not the case | `open_case` clicks **Evaluate treatments** in `#drawer` |
| *Open decision analysis* on the asset page sits inside the **Actions ▾** menu (`details.asmenu`) | Click `#view details.asmenu > summary` first |
| Esc closes the evidence drawer but its close button still reports "visible" (off-screen slide) | Close with `page.evaluate('closeDrawer(true)')` instead of clicking |
| Clicking a run-board box that is already open **closes** it (toggle) | Open box 10 with `ACT.afRunSel(10)` (always opens) |
| After approval the order step is **acknowledged automatically** (`afAutoAck`, ≈ 1.6 s) | Three presses of *Check for the next acknowledgement*, each followed by `lr_settled` (the board replays the stage after each action and hides the button while playing) |
| The finance user re-opening the board starts a **new playback from stage 1** | Press **Skip to now** first (inside the cut) |
| What-if reset too early hid the flipped ranking | Click the preset, hold until the line ends, then reset |
| Long bash heredocs get truncated in this environment | Write scripts with a file editor, not inline heredocs |
| Headless CSS transitions/animations do not advance in the old virtual-time harness | Not an issue for Playwright real-time capture; only for `run.py shot` screenshots |
| `onnxruntime` install fails under the long scratchpad path | Voice venv lives at `%TEMP%\cvlv` |
| `text=/integration health/i` never matches (cosmetic) | Left as a `WARN`; the tile is still on screen |

**Selectors that must keep working if the UI changes:** `#si-id`, `#si-pw`, `#siForm`, `summary.acchip`, `[data-act="signOut"]`, `.ngh[data-nav="…"]`, `[data-act="intTab"][data-arg="map|studio"]`, `[data-act="afAssist"][data-arg="source|mkt"]` (text *Diagnose*), `#afAskBtn`, `#afq`, `#askp`, `[data-act="afDo"]` with texts *Accept all*, *Full analysis*, *Approve*, `#view a[href="#/product/asset/RT-1048"]`, `details.asmenu`, `[data-act="snapshot"]`, `[data-act="tiPreset"][data-arg="demand"]`, `#jgmount [data-act]` text *Submit RT-1048 for review*, `#modal [data-act="confirmApprove"]`, `#lrBoard [data-act="lrSkip"]`, `.lrb[data-n] .lrh`, `#lrBody-N`, `[data-act="afRunNext"]`, `a.btn` text *Open RT-1048*, headings *Retrieved from enterprise systems*, *Lease end, return and transit*, *Diagnostic condition*, *Inspection findings*, *Lifecycle evidence timeline*, *All pathways*, *Why this outcome*, *Predicted outcomes and comparison*, *What-if and edge cases*, *Next best action*, *Reconcile and learn*.

---

## 9. Iteration history

| # | Version | What changed | Why |
|---|---|---|---|
| 1 | Written script `VIDEO_SCRIPT_AGENTIC.md` (≈ 7 min) | Scene tables with clicks and voice-over; positioning table; never-on-camera list (Presenter menu, + Add source vendor picker, Data checks) | First ask: a script to record manually |
| 2 | Script cut to 6 min | Dropped Command Center, Event stream, long board playback | User: 5–7 min max |
| 3 | Video v1 (Piper `lessac`) | Playwright capture + local TTS + ffmpeg mix; cursor overlay; title, journey and close cards | User: create the video from our UI |
| 4 | Fixes | Playwright ffmpeg install; non-fatal cursor pointing; *Evaluate treatments* drawer step | Recording failures |
| 5 | Cuts and role captions | Sign-ins cut out; four bridge lines added (approver intro, board counters, agent autonomy, predicted vs actual) | ≈ 1 min of dead air at role switches |
| 6 | Voice licence | `lessac` and `ryan` found **non-commercial**; switched to public-domain `cori` | Client-facing material |
| 7 | Finance line split | Numbers spoken only once the result is on screen | Sync |
| 8 | **Video v1 final** (5:13) | Committed by the user as `15a7561` | — |
| 9 | Feedback round | User: missing Connection Fabric, Workflow Studio AI, Asset & Product Intelligence, full Treatment scroll; no Analytics ending; no Finance switch; plug and play; deeper CEO voice; follow `user-flow.svg`; under 5 min | — |
| 10 | Voice samples | Kokoro installed; four male samples; user chose `am_michael` | — |
| 11 | **Video v2** (4:11, current) | New narration (18 lines), new scene order (section 5), eased scrolls, off-camera Finance, Diagnose and workflow-draft AI scenes; fixes for Actions menu, drawer close, box-10 toggle, cut helper, what-if hold | — |

---

## 10. Open items and suggestions for the next agent

1. **Commit or not:** the current video and pipeline changes are uncommitted on top of the user's `15a7561`. Ask the user before committing (the MP4 is ≈ 44 MB; consider Git LFS or keeping videos out of git).
2. **`VIDEO_SCRIPT_AGENTIC.md`** scene tables describe the older manual script; if the user wants the written script to match the video, rewrite its sections 3–5 from section 5 above.
3. **Legal review** (top of this file).
4. **Model figures:** only resale-price's MAE, MAPE and coverage are computed (from reconciled decisions); condition-vision, rul-survival, demand-match, prep-cost-time, service-exposure and repair-success figures are configured values in `LR_MODELS` (`index.html`). Confirm with data science or keep them off camera.
5. **Voice polish options:** Kokoro `speed` (0.9 for slower), per-line pauses, or a professional human voice-over recorded to the same timeline (`timeline.json` gives exact start times; `.srt` doubles as the read script).
6. **Possible additions if time allows (≤ 5 min total):** Source tables or Canonical models to underline plug and play; *Suggest field mappings* with sample preview; Agent autonomy (was in v1); Event stream (idempotent instructions). Each costs 8–12 s.
7. **Deck alignment:** the deck's slide 3 sample (gearbox, $735) differs from the video's RT-1048 ($9,600 motor); the PO may want the slide updated to the video's record.
8. **If the UI changes:** re-run the selector checks (section 8 list) before a full take; a failed take costs about 3–6 minutes.
