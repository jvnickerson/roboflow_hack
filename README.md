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

## Deploy (Cloud Run)

```bash
./deploy.sh                      # deploys, then curls the routes to confirm
SERVICE=vision REGION=us-east1 ./deploy.sh
```

Or by hand:

```bash
gcloud run deploy vision --source . --region us-east1 \
  --allow-unauthenticated --min-instances=1 --no-cpu-throttling \
  --clear-base-image --memory=2Gi --cpu=2
```

- **Both scaling flags are required.** Cloud Run throttles CPU to ~0 between
  requests and scales to zero when idle; either one stalls or kills
  `server.py`'s background sweep thread.
- **`--clear-base-image` is required** if the service was ever deployed from
  buildpacks before switching to the Dockerfile. Otherwise gcloud stops with
  "Base image is not supported for services built from Dockerfile". Hit on
  the first Dockerfile deploy of `vision`.
- **`--memory=2Gi` is not optional.** `sweep_pass` holds one decoded frame
  per camera plus the previous pass's arrays for the diff, roughly 250 MB per
  set at ~963 cams. On Cloud Run's 512 MiB default the container is
  OOM-killed mid-pass (`Memory limit of 512 MiB exceeded with 741 MiB used`)
  and restarts in a loop every few seconds, so `sweep_loop` never finishes a
  pass and `scores.json` silently never updates. The page still serves, which
  is what makes this easy to miss: check that `scores.json` actually changes,
  not that the site loads.
- `Dockerfile` builds the image; `.dockerignore` controls its contents.
  `.gcloudignore` separately controls what gets **uploaded** to Cloud Build.
  Without it gcloud falls back to `.gitignore`, which does not exclude
  `data/sweep/latest/` (~28 MB regenerated every pass).
- `control.html` loads camera frames browser-side straight from DOT, so the
  service never proxies imagery. Only the page and the JSON are served.
- Only `data/cameras.json` is required at boot. `leaderboard.json`,
  `pedestrian_cams.json`, and `sweep/scores.json` each load inside a
  `try/catch`, so a deploy missing them still boots with reduced function.

Measured sweep timing, if `--loop` cadence needs tuning: ~21 s/pass on an M5
laptop, ~33-39 s/pass in Cloud Shell (2 vCPU). The limit is CPU spent on
image decode, so more bandwidth does not help.

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

Bird cams around the city, with live status checked per cam and raw endpoints:
[`BIRD_CAMS.md`](BIRD_CAMS.md). Six were streaming on 2026-08-07; two expose an
unauthenticated `.m3u8` that ffmpeg or OpenCV reads directly, the rest are on
YouTube.
