# roboflow_hack — NYC Vision Hack v.2

Live NYC camera analysis: 968 public NYC DOT cams → Roboflow detection →
complexity/movement metrics, with the inquiry ledger tracking goals and
goal edits as the night evolves.

## The spine

```bash
.venv/bin/python cams.py --refresh                 # registry -> data/cameras.json (968 cams, lat/lng)
.venv/bin/python poll.py --grep "7 ave" --minutes 10 --interval 4
export ROBOFLOW_API_KEY=...                        # app.roboflow.com -> Settings -> API Keys
.venv/bin/python detect.py --follow                # run beside poll.py; detections -> data/detections/
.venv/bin/python metrics.py --sort motion_entropy  # leaderboard -> data/leaderboard.json
```

- `cams.py` — fetch/filter the DOT registry (`--borough`, `--grep`; other cam
  sources can merge in with the same shape).
- `poll.py` — snapshot cameras on an interval; frames in
  `data/frames/<slug>/`, capture log in `data/frames/index.jsonl`.
- `detect.py` — Roboflow serverless on each new frame. Model from
  `ROBOFLOW_MODEL` (default `yolov8n-640`, hosted COCO; swap in a Universe
  model id if that alias 401s).
- `metrics.py` — per-camera scores: **colorfulness** (Hasler–Süsstrunk, needs
  frames only), **class entropy** (variety of objects), **motion entropy**
  (variety of movement *directions* from matched detections across
  consecutive frames — the "most kinds of movement" measure).
- `sweep.py` — the peripheral tier: all 966 cams in ~4 s/pass (threaded,
  no API calls), scoring **churn** (frame differencing, timestamp band
  cropped, "being serviced" cards filtered) + colorfulness city-wide into
  `data/sweep/scores.json`. Run `--loop` during the event; spend detection
  only on what it surfaces.
- `control.html` — the control center: live grid ranked by any score,
  borough filter, dissolves. Serve with `python3 -m http.server 8123`.
- `robo.py` — minimal Roboflow smoke test (their soccer demo).

## Inquiry ledger

`inquiry/` binds `~/Dropbox/projects/inquiry_kernel` (sys.path import, never
copied). File goals ex ante, log goal edits as we pivot:

```python
import inquiry
inquiry.goal("...", move="...", prediction="...", stop_loss="...")
inquiry.edit_goal("old goal", "new goal", why="...")
inquiry.probe("what we did", warrant_id="W-...", result="...")
inquiry.status()   # fold ledgers/ -> metrics
inquiry.lens()     # interactive graph -> lens.html
```

Opening warrant: `W-2a614bc60e41` — live detections on an NYC feed by end of
night; stop-loss: two dry hours → recorded footage.

## Cameras

NYC DOT: `https://webcams.nyctmc.org/api/cameras` — open JSON, no key.
352×240 JPEG per camera, refreshes every ~2 s, timestamp burned in.
