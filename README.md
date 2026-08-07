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
- **`--memory=2Gi` is now just headroom.** Before `74df75c`, `sweep_pass`
  retained a full-res frame per camera across passes and the container was
  OOM-killed mid-pass on Cloud Run's 512 MiB default
  (`Memory limit of 512 MiB exceeded with 741 MiB used`), restarting every
  few seconds. Peak is ~312 MB since the thumbnail cache. The flag costs
  nothing to keep and covers the cam count growing.
- **`/healthz` is unreachable in production.** Google's edge answers it with
  its own 404 before the request reaches the container: no Cloud Run trace
  header on the response, reproduced from a laptop, from Cloud Shell, and on
  both the project-number and hashed service URLs. `/data/*` reaches the app
  normally, so it is specific to that path. Do not wire a health check to it.
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

### How the sweep fails, and how to tell

Both failures hit so far leave `/` and `/data/*` returning 200 while
`scores.json` quietly stops changing. `sweep_loop` catches every exception
and sleeps, and Python block-buffers stdout in a container, so the logs stay
silent too. The site looks completely healthy.

1. **OOM.** Container killed mid-pass, restarting every few seconds. Fixed at
   the source in `74df75c`; `--memory=2Gi` covers the rest.
2. **Call-site drift.** `server.py` passed `prev_arrays=` after `74df75c`
   renamed the parameter to `prev_thumbs`, so every pass raised `TypeError`
   into the bare `except` and no scores were ever written.

The check that catches both: hash `data/sweep/scores.json` off the live URL
twice, a few minutes apart, and confirm it changed. Never take a 200 on `/`
as evidence the sweep is running.

First churn values are always null. A fresh container has no previous pass to
diff against, so pass one writes `churn: null` for every camera and pass two
is the first with real numbers. Two nulls in a row means something is wrong.

### What is actually deployed

The live service is built from a hand-assembled copy in Cloud Shell
(`~/vision`). The repo is private and Cloud Shell cannot clone it, so those
files were written there by hand. As of this commit the running revision is
`vision-00004-nkx`, which predates `74df75c` and still carries the old
`sweep.py` plus its
matching `server.py`. Re-bundle and redeploy to pick up repo changes; the
deployed artifact does not track `main`.

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
