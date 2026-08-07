# HANDOFF — NYC Vision Hack v.2 (Aug 7, 2026)

State as of ~1pm, written for the next session (any model) to continue
without the morning's conversation. README.md has run commands; this file
has the *why* and the gotchas.

## What exists and is VERIFIED WORKING

Foveated attention over 966 public NYC DOT cams:

| piece | status |
|---|---|
| `cams.py` | registry cached; 966 online cams, lat/lng, borough |
| `sweep.py` | **periphery**: all 966 cams in ~4s/pass, threaded, zero API calls; churn + colorfulness → `data/sweep/scores.json` |
| `poll.py` | snapshots chosen cams on an interval → `data/frames/` |
| `detect.py` | **fovea**: Roboflow serverless, `yolov8n-640` alias (works); → `data/detections/` |
| `metrics.py` | colorfulness, class entropy, **motion-direction entropy** ("kinds of movement") → `data/leaderboard.json` |
| `control.html` | live grid, rank/borough/size/refresh/dissolve controls; serve via `python3 -m http.server 8123` |
| `robo.py` | Roboflow smoke test (soccer demo) — passed |

Verified numbers, if something regresses: 7 Ave @ 42 St scored movH 3.02 /
73 objects / colorfulness 22.3 over 11 frames; overlay spot-check
(`data/overlay_7ave42.png`) shows boxes correctly placed.

## Key decisions, with reasoning

- **Foveation**: sweeping all 966 with pixel churn is free (4s/pass);
  detection costs API calls. So periphery ranks city-wide, fovea
  (detect.py) spends only on the salient ~25. Do NOT wire detection to all
  966 — that's ~870K calls/hour.
- **Two movement measures on purpose**: churn = *amount* (pixel diff);
  motion entropy = *kinds* (direction distribution of matched detections).
  They disagree and that disagreement is content, not a bug. (Roboflow's
  coding agent independently built the churn measure — screenshot in repo.)
- **No framework front end**: `<img>` tags dodge CORS entirely, so the
  browser polls DOT directly; `http.server` exists only to serve local
  JSON. Keep it that way — a proxy adds nothing.
- **Import, don't vendor** (kernel rule): `inquiry/` bootstraps
  `~/Dropbox/projects/inquiry_kernel` via sys.path. Never copy kernel code
  in.

## Gotchas that cost time once already

- **Anaconda base python is broken** for this stack (numpy/scipy binary
  mismatch kills `inference_sdk`). Always use `./.venv/bin/python`.
- **Roboflow key** is in `.env` (git-ignored). Export before detect/robo:
  `export ROBOFLOW_API_KEY=$(cut -d= -f2 .env)`. Rotate key after event.
- **"This camera is being serviced" cards**: gray placeholder frames;
  colorfulness < 6 identifies them (real streets ≥ ~11). sweep.py filters
  them (`serviced` flag) — one faked 49% churn before filtering.
- **Burned-in timestamp** (top ~8% of frame) inflates frame differencing;
  sweep.py crops it (`TS_BAND`). Keep the crop in anything new.
- **Slug functions are duplicated** in `cams.py` (Python) and
  `control.html` (JS) and must stay in sync — they key the score join.
- Small-model hallucinations at 352×240: a "boat" on Canal St, a "train"
  at 42nd. Threshold confidence ≥ ~0.5 for anything shown publicly.

## Inquiry ledger — keep using it

`ledgers/hack.jsonl`, run_id `nyc-vision-hack-v2`, opening warrant
`W-2a614bc60e41` (prediction already met: live-feed detections, 12:30pm).

```python
import inquiry                       # from repo root, any python ≥3.10
inquiry.probe("what you did", warrant_id="W-2a614bc60e41", result="...")
inquiry.edit_goal("old goal", "new goal", why="...")   # WHEN THE GOAL PIVOTS
inquiry.goal(...)                    # new line of work, filed ex ante
```

Log a probe per work block and an edit_goal on every pivot — the goal-edit
trail is itself demo material (fold renders it: `inquiry.lens()`).

## Next steps, in intended order

1. **ε-greedy cells** in control.html: reserve 2–3 grid cells for random
   low-ranked cams so the fovea doesn't freeze on Times Square.
2. **Time series**: sweep.py `--loop` currently overwrites scores.json;
   append per-pass summaries (e.g. `data/sweep/history.jsonl`) to get the
   day's arc per camera → regime detection (commute/going-out) later.
3. **Object transplant** (Stage 2 art): YOLO box → box-prompted SAM2
   (Roboflow serves SAM2; same API key) → OpenCV feathered paste into
   another cam's frame. Do NOT run SAM2 in anaconda base (see gotcha).
4. **Veris**: `uv tool install veris-cli`, `veris login` (Google OAuth,
   self-serve); start from github.com/veris-ai/cookbook. Fit: wrap a
   traffic-analyst agent's tools, simulate scenarios, grade predictions.
5. Roboflow bot's server-side app: under Solutions in the workspace at
   app.roboflow.com — ask it to expose a URL; can be iframed as a grid cell.

Morning context (repo move, parent-repo git tangle, Veris research) is in
the session ledger probes and the Claude memory dir; not needed to code.
