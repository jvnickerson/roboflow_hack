# NYC Channels

**Television for a city that is already being watched.** New York points 966 public
cameras at itself. This turns them into channels: one camera on screen at a time,
chosen live by a machine looking for a specific condition, cutting away the moment
the condition breaks.

Not a dashboard. A dashboard shows you everything at once and asks you to find the
signal. A channel has already decided what is worth looking at, and tells you why.

**On air tonight: EMPTY NEW YORK.** The city that never sleeps, shown with nobody in
it — live, on the exact midtown cameras that are normally packed. A scene qualifies
when a person detector finds zero people in it. When someone walks into frame, the
channel cuts away.

**Second channel: WATER ON THE LENS.** Cameras with rain on their own glass. It rained
hard during the build, and a wet lens turns a traffic camera into something closer to
a painting.

```
/channel                  EMPTY NEW YORK      (live switcher, Roboflow qualifier)
/channel?channel=water    WATER ON THE LENS   (wetness-ranked, no API calls)
/                         the control grid    (the instrument behind the channels)
```

---

## How it works

```
Cloud Run container
│
├─ sweep_loop()      every 120s ─► data/sweep/scores.json    churn + colour, all 966 cams
├─ switcher_loop()   every 6s   ─► data/channel/empty.json   who is on air, and why
│      └─ Roboflow serverless yolov8n-640, given the DOT image URL directly
│
├─ /          control.html    the grid
├─ /channel   channel.html    the player
├─ /data/…    state + scores
└─ /healthz   (see the deploy notes — Google's edge intercepts this path)

Browser
├─ polls the channel state every 2s
└─ <img src="dot-camera-url"> — imagery goes straight from the city to the viewer
```

**The service never touches a photograph.** Roboflow fetches frames from the DOT URL
itself, and the browser loads them directly. The container moves JSON only.

### Two tiers of attention

Detection costs money per call; pixel arithmetic is free. So the system looks the way
eyes do — a cheap wide periphery and an expensive narrow fovea.

- **Periphery** (`sweep.py`): all 966 cameras, ~21 s per pass, no API calls. Scores
  *churn* (how much the frame changed since last pass) and *colourfulness*.
- **Fovea** (`switcher.py`, `detect.py`): Roboflow object detection, spent only on the
  handful of cameras a channel actually cares about.

Running detection on all 966 at sweep cadence would be ~870,000 calls an hour. The
switcher uses about 2,400.

### The measures

| Measure | What it is | Cost |
|---|---|---|
| **churn** | mean pixel difference vs. the same camera's previous pass | free |
| **colourfulness** | Hasler–Süsstrunk; finds neon and signage after dark | free |
| **motion entropy** | Shannon entropy over the *directions* objects moved — not how much movement, but how many **kinds**. A one-way avenue scores low; a crossroads with turning traffic and two crosswalks scores high. | detection |
| **wetness** | mid-scale vs. fine-scale image energy where the frame held still | free |
| **persons** | Roboflow `yolov8n-640`, confidence ≥ 0.5 | detection |

**Wetness, since it is the least obvious.** A droplet on a lens is itself a lens: it
defocuses whatever is behind it and refracts point lights into discs, moving image
energy out of fine detail and into mid-scale blobs. Unlike traffic, it does not move
between frames. So `wet.py` takes a temporal median over several frames — traffic
averages away, droplets persist — and measures the blob-to-detail ratio in the parts
of the frame that stayed still.

**It only half works, and the docstring says so.** The ranking does put the most
droplet-covered lenses on top, but separation from merely-rainy scenes is weak,
because in a citywide downpour nearly every lens is wet — there is barely a dry class
left to separate against. Single-frame features (bloom, blur, bokeh area) failed
completely: at 352×240 at night they measure *"it is raining"*, not *"it is on the
glass."* Proving it properly needs a dry-night baseline per camera, which one evening
did not provide.

### One thing the data said

At 21:51 UTC the National Weather Service station in Central Park reported **Clear.**
Every camera on 42nd Street was streaming with water at that moment. The station did
not report Heavy Rain until 22:13 UTC.

The station is not broken — it is one instrument, four miles from midtown, reporting
hourly. There are 966 lenses. Water on the glass is a weather reading, and it arrives
first.

---

## Run it

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
export ROBOFLOW_API_KEY=...            # app.roboflow.com → Settings → API Keys
./.venv/bin/python server.py           # http://localhost:8080/channel
```

Without a key the switcher still runs, in degraded mode: timed rotation, no detection.
The screen is never blank.

```bash
./.venv/bin/python cams.py --refresh              # registry → data/cameras.json
./.venv/bin/python sweep.py --loop                # citywide churn + colour
./.venv/bin/python wet.py --grep "42 st" --top 6  # wetness → water channel + composite
./.venv/bin/python metrics.py --sort motion_entropy
```

| File | What it does |
|---|---|
| `cams.py` | the 966-camera registry, filterable by borough or name |
| `sweep.py` | citywide churn + colourfulness, no API calls |
| `switcher.py` | picks who is on air and why; writes the channel state |
| `channel.html` | the player — reads only the state file |
| `control.html` | the grid, ranked by any measure |
| `wet.py` | wetness scoring, the water channel, and the composite |
| `poll.py` / `detect.py` / `metrics.py` | capture, detect, and score over time |
| `exploded.py` | pulls detected objects outside the frame with leader lines |

---

## Deploy (Cloud Run)

```bash
export ROBOFLOW_API_KEY=...
./deploy.sh                          # deploys, then curls the routes to confirm
SERVICE=vision REGION=us-east1 ./deploy.sh
```

Hard-won operational notes, each one paid for tonight:

- **Both scaling flags are required.** Cloud Run throttles CPU to ~0 between requests
  and scales to zero when idle; either one stalls or kills the background loops.
- **`--clear-base-image` is required** if the service was ever deployed from buildpacks
  before switching to the Dockerfile, or gcloud stops with "Base image is not supported
  for services built from Dockerfile."
- **`--memory=2Gi` is now just headroom.** Before `74df75c`, `sweep_pass` retained a
  full-resolution frame per camera across passes and the container was OOM-killed
  mid-pass on the 512 MiB default (`Memory limit of 512 MiB exceeded with 741 MiB
  used`), restarting every few seconds. Peak is ~312 MB since the thumbnail cache.
- **`/healthz` is unreachable in production.** Google's edge answers it with its own
  404 before the request reaches the container — reproduced from a laptop, from Cloud
  Shell, and on both URL forms. `/data/*` reaches the app normally. Do not wire a
  health check to it.
- `.dockerignore` controls the image; `.gcloudignore` separately controls what gets
  **uploaded**. Without the latter, gcloud falls back to `.gitignore`, which does not
  exclude ~28 MB of regenerated JPEGs.
- Only `data/cameras.json` is required at boot. Everything else loads inside a
  `try/catch`, so a partial deploy still boots with reduced function.

### How the sweep fails, and how to tell

Both failures hit tonight left `/` and `/data/*` returning 200 while `scores.json`
quietly stopped changing. `sweep_loop` catches every exception and sleeps, and Python
block-buffers stdout in a container, so the logs stay silent too. **The site looks
completely healthy while the data is frozen.**

1. **OOM** — container killed mid-pass, restarting every few seconds.
2. **Call-site drift** — `server.py` passed `prev_arrays=` after the parameter was
   renamed to `prev_thumbs`, so every pass raised `TypeError` into a bare `except` and
   nothing was ever written.

The check that catches both: hash `data/sweep/scores.json` off the live URL twice, a
few minutes apart, and confirm it changed. Never take a 200 on `/` as evidence that
anything is running.

First churn values are always `null` — a fresh container has no previous pass to diff
against. Two nulls in a row means something is wrong.

### The deployed artifact does not track `main`

The live service was built from a hand-assembled copy in Cloud Shell (`~/vision`),
because the repo was private and Cloud Shell could not clone it. **The repo is public
now, so that constraint is gone** — clone it in Cloud Shell and deploy from the clone
rather than re-copying files by hand. Until that happens, assume the running revision
is behind `main` and re-bundle before trusting any change to be live.

---

## Data, and looking away

Everything here comes from `https://webcams.nyctmc.org/api/cameras` — the city's own
public traffic-camera registry. No key, no scraping, no authentication. The handbook
hands out this endpoint as the event's quickstart source.

- **352×240.** Faces and licence plates are not resolvable at this resolution, and
  nothing here attempts to resolve them.
- **No imagery is stored or proxied by the service.** Frames go from the city to the
  viewer's browser; Roboflow fetches them from the same public URL.
- **Detections are used only to look away.** The person detector exists so the channel
  can leave occupied scenes. It counts people in order to avoid showing them.
- Sources with terms of use prohibiting automated capture (EarthCam and similar) were
  checked and deliberately excluded, even where the imagery was better. See
  [`BIRD_CAMS.md`](BIRD_CAMS.md) for that survey.

## What came before tonight

Built before the 4 PM start: the registry fetch, the citywide sweep, the metrics, the
Flask scaffold, and the control grid. Built tonight: the channel concept and switcher,
the Roboflow qualifier, the channel player, the wetness measure and water channel, and
the Cloud Run deployment.

## What is next

- **New York in Motion** — a channel of cameras that move. Designed, not built: every
  one of the 966 DOT cameras is fixed-mount, and no public moving-camera feed was
  sourced in time. It is waiting on a source, not on code.
- **Free channels.** Neon (colourfulness) and Deserted (inverted churn) need no API
  calls at all — both measures are already computed citywide every pass. Deserted is
  also the honest understudy for Empty: no motion is a decent proxy for no people, and
  it keeps working if the detector is unavailable.
- **Sodium and LED.** Classify streetlight colour temperature from the hue of bright
  pixels. New York replaced amber sodium lamps with cold white LEDs block by block, so
  a warm/cool map of the city is a map of which neighbourhoods got money, and when.
- **The multi-panel grammar.** The state file already publishes `on_air`, `previous`,
  and `queue`, so a split-screen composition is a front-end change with no server work.
  `wet.py`'s composite is a first sketch of it.
