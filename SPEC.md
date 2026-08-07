# Design Spec & Execution Plan — NYC Vision Hack Channel Switcher

_Design spec and execution plan authored by Claude (Fable 5), 2026-08-07, ~7:00 PM at the event. Product decisions come from [[Fable Brief - NYC Vision Hack]] and are not re-opened here. Repo facts were verified against the live clone at `roboflow_hack/` at 6:50 PM: git state, ignore files, `server.py` routes, `robo.py`, `data/pedestrian_cams.json`. The raw Roboflow HTTP call is the one unverified dependency; verifying it is the first build step._

[[#The rulings]] | [[#How the design answers Ida's fears]] | [[#System shape]] | [[#The switcher]] | [[#The qualifier]] | [[#The source list]] | [[#The state file contract]] | [[#Where each piece lands]] | [[#Key provisioning and deploy]] | [[#Two-builder split]] | [[#Execution plan with acceptance checks]] | [[#Demo safety]] | [[#Feed discovery plan]] | [[#Submission block]] | [[#What to cut if late]] | [[#Open for Ida]]

---

## The rulings

**Empty New York ships first.** Reasons, in order of weight:

1. Its source list already exists. `data/pedestrian_cams.json` holds 21 curated busy cams (Times Square corridor and similar, each tagged "heavy foot traffic"), tracked in git and already uploaded by the deploy. Zero feed discovery required.
2. Its qualifier is the crispest of the three: count persons in a frame, which is exactly what the sponsor's hosted COCO model does.
3. It has the strongest answer to the event's privacy guidance. The channel structurally cuts away from people. Person detections are used only to leave occupied scenes, and no imagery is stored or proxied by the service.
4. The NYC hook is sharp: the city that never sleeps, shown with no one in it, live, on the exact cameras that are normally packed.

**Fallback if it stalls:** the same switcher shipping in its degraded mode, which is a timed rotation over the same curated source list. Every stage of this build is the fallback for the stage after it. The switcher skeleton (rotation, no detection) is itself a working, demoable channel, and every later step upgrades it in place. If Roboflow integration fails at any point, stop upgrading and ship the stage that works.

**New York in Motion is cut for tonight.** The 966 DOT cams are fixed-mount, no moving camera has been found, and the container can only read JPEG stills, so even a found HLS mover could not be qualified server-side (no ffmpeg or OpenCV in the image). A mover found during the stretch window becomes a narrated aside or an embedded preview in the demo, never a third build track. Details under [[#Feed discovery plan]].

**Natural New York is stretch only.** Once the switcher is channel-generic (it is, by construction, one config dict), Natural New York is a second config: sources from a name-grep of the registry (bridge, river, park) plus the 55 Water Street falcon poster still, qualifier from the sweep signals that already exist. Only touched after the submission gates are green.

**The composed frame: one full-bleed feed at a time, with the multi-panel grammar kept open in two specific places.** The one-at-a-time rule is the channel premise and the guard against dashboard drift, so it stands on air. Burtin, Thomas Crown, and Miller enter later without any server change: (a) the cut is where two frames may legitimately coexist, so the transition is the future home of the split-screen grammar (tonight ships a hard cut); (b) the state file publishes on-air, previous, and queue, so a multi-panel front end can be composed later purely in HTML. Tonight's one visible design element is a lower-third caption strip: channel name, camera name, borough, and a counter of how long the scene has been empty. The switcher needs it to be legible to judges (the caption says why the channel cut), so it is in scope.

**The brief's decomposition (source list + qualifier + shared switcher) holds**, with one addition: the published state file is a fourth named piece. It is the contract that lets two builders work in parallel and lets the visual second pass happen without touching the server. The qualifier runs inside the switcher loop rather than as a separate process: one loop, one writer, no file races.

---

## How the design answers Ida's fears

**"Hard to execute in a few hours."** Nothing new is installed. `requirements.txt` is unchanged (flask, requests, numpy, pillow cover everything; Roboflow is called with `requests` over raw HTTP). The service, deploy path, data route, and source list all exist. The build adds two new files, edits one existing file in two places, and adds one deploy flag. Every stage from the skeleton onward is shippable, so an early 8:30 means shipping the current stage.

**"Only one of us can make progress."** The server track and the player track share exactly one thing: the state file contract, frozen in this spec. The player is built against a committed fixture and needs nothing from the server until integration, which consists of opening a URL. File ownership is disjoint, so git cannot conflict. Either person can stop for a stretch without blocking the other.

---

## System shape

```
Cloud Run container  (existing flags unchanged, + ROBOFLOW_API_KEY env var)
│
├─ sweep_loop()     every 120s ─► data/sweep/scores.json     (existing, untouched)
├─ switcher_loop()  every 6s   ─► data/channel/empty.json    (new)
│       │
│       └─ POST serverless.roboflow.com/yolov8n-640?image=<DOT cam imageUrl>
│
├─ /          → control.html   (existing grid, untouched)
├─ /channel   → channel.html   (new full-screen player)
├─ /data/<path>                (existing route — already serves the state file)
└─ /healthz

Browser (channel.html)
├─ polls /data/channel/empty.json every 2s
└─ <img src="cam.imageUrl?t=...">  direct from DOT — no proxy, unchanged
```

The service still never proxies imagery. Roboflow fetches camera frames from the DOT URL itself, so the container downloads nothing for detection. The SDK call in `robo.py` proves the endpoint accepts a URL as input; whether the raw HTTP `image` query parameter does the same is exactly what the first build step's curl verifies.

---

## The switcher

`switcher.py`, a daemon loop beside `sweep_loop` in the same process. Channel-generic: one `CHANNELS` dict maps a channel name to a source-list path and qualifier parameters, and the loop takes the channel it runs. Tonight it runs one channel, `empty`.

Constants at the top of the file, each with a one-line comment:

| Constant | Value | Meaning |
|---|---|---|
| `TICK` | 6 s | loop interval; DOT stills refresh ~every 2 s, so faster sampling wastes calls |
| `POOL_PER_TICK` | 3 | pool cams sampled per tick, round-robin |
| `CONF` | 0.5 | confidence floor for counting a person (brief's public-display threshold) |
| `QUALIFY_STREAK` | 2 | consecutive person-free samples to qualify; one occupied sample re-arms |
| `MIN_DWELL` | 12 s | minimum time on air before a rotation (never blocks a disqualification cut) |
| `MAX_DWELL` | 45 s | rotate to the next qualified cam even if the current one is still empty |
| `COOLDOWN` | 120 s | a cam that leaves the air cannot return for this long |
| `FAIL_BENCH` | 3 fails → 600 s | fetch or API failures bench a cam for ten minutes |

Per tick:

1. Sample the on-air cam. Any person at `CONF` or above cuts away immediately. This overrides `MIN_DWELL`; it is the channel premise and the visible demo moment.
2. Sample the next `POOL_PER_TICK` pool cams round-robin; update each cam's person-free streak.
3. Select on air: the highest-priority qualified cam (priority = source list order) not in cooldown. Rotate on `MAX_DWELL`; otherwise stay put past `MIN_DWELL` only if the current cam is still the best.
4. If nothing qualifies, enter degraded mode: show the cam with the fewest persons in its last sample (ties broken by list order) and mark `mode: "degraded"`. The screen is never blank.
5. Write the state file atomically (`tmp` + `os.replace`), so the player can never read a torn JSON.

Degraded mode is also the boot state (before streaks exist) and the Roboflow-outage state (API errors count as no data, and the loop keeps rotating on the `MAX_DWELL` cadence). One code path covers boot, outage, and a city too crowded to qualify.

API arithmetic: 1 on-air + 3 pool samples per 6 s tick = 2,400 calls/hour. The 21-cam list is fully rescanned about every 42 s. `POOL_PER_TICK` is the knob if that needs to move either way.

---

## The qualifier

For `empty`: a scene qualifies when it contains zero persons.

- **Computed from:** one Roboflow serverless call per sample, model `yolov8n-640` (hosted COCO), passing the cam's `imageUrl` directly in the `image` query parameter.
- **Person:** any prediction with `class == "person"` and `confidence >= 0.5`. Filter in Python; do not rely on the API's confidence query parameter.
- **Vehicles are ignored.** A street full of cars with no people still counts as empty of people, and at 352×240 drivers are not detectable anyway. This is a one-constant call Ida can flip (see [[#Open for Ida]]).
- **Cost:** ~2,400 calls/hour at the constants above.
- **Failure:** a failed fetch or a non-JSON response counts as no sample. Three consecutive failures bench the cam for ten minutes.

**The one unverified dependency, verified first.** `robo.py` proves the serverless endpoint and the URL-input pattern work through the SDK; the raw HTTP form has not been run. First server-track action, before any code:

```bash
export ROBOFLOW_API_KEY=...   # from the session shell that has it, or app.roboflow.com → Settings → API Keys
IMG="https://webcams.nyctmc.org/api/cameras/5d055599-875a-4010-991f-e7e454889052/image"
curl -s -m 20 -X POST "https://serverless.roboflow.com/yolov8n-640?api_key=$ROBOFLOW_API_KEY&image=$(python3 -c "import urllib.parse;print(urllib.parse.quote('$IMG',safe=''))")" | head -c 400
```

Pass: JSON containing a `predictions` array. On a 401 or 404 (detect.py's docstring warns the `yolov8n-640` alias can 401): spend at most 5 minutes finding a hosted COCO model id on universe.roboflow.com, and if that fails, add `inference_sdk` to `requirements.txt` and use the `robo.py` call pattern instead. That last resort carries build-time risk (the SDK may pull heavy dependencies), so check its footprint locally with `pip download inference-sdk` before committing to it.

Note: `.env` is not in this clone (checked 6:50 PM). The key exists only in the event session's shell, so the local export above and the Cloud Run env var under [[#Key provisioning and deploy]] are both required setup steps.

---

## The source list

`data/pedestrian_cams.json`, as it stands: 21 cams, each with `id`, `name`, `area`, `imageUrl`, and a `why` field, ordered list. That order is the busyness priority the switcher uses. It is tracked in git and not excluded by `.gcloudignore`, so it deploys with the source.

Static tonight. The switcher reads it once at boot; a missing file is a fatal boot error with a clear log line, not a silent empty channel.

Stretch only: widen to ~35 by grepping `data/cameras.json` names for additional known-busy corridors (34 St, Herald Sq, Canal St, Broadway crossings) and appending in the same shape. Order still hand-set. Do not spend pre-gate time here; 21 is enough pool for the switcher to move.

---

## The state file contract

`data/channel/empty.json`. Frozen as of this spec; both tracks build to it, and integration means nothing changes. The player uses only fields in this file — it never joins against `cameras.json` and never computes a slug, which sidesteps the duplicated Python/JS slug functions entirely.

```json
{
  "channel": "empty",
  "mode": "live",
  "ts": 1754607600,
  "tick": 412,
  "on_air": {
    "slug": "7-ave--40-st",
    "name": "7 Ave @ 40 St",
    "area": "Manhattan",
    "imageUrl": "https://webcams.nyctmc.org/api/cameras/5d055599-875a-4010-991f-e7e454889052/image",
    "since": 1754607570,
    "persons": 0,
    "reason": "qualified"
  },
  "previous": { "slug": "7-ave--43-st", "name": "7 Ave @ 43 St" },
  "queue": [
    { "slug": "...", "name": "...", "area": "...", "imageUrl": "...", "persons": 0, "streak": 2 }
  ],
  "stats": { "list_size": 21, "qualified_now": 4, "api_calls": 913, "api_ok": true, "last_error": null }
}
```

- `mode` is `"live"` or `"degraded"`. `reason` is `"qualified"` or `"degraded_best"`.
- `ts` and `tick` exist for freshness checks: a healthy switcher advances both every tick. This is the guard against the reference failure class, where the page serves fine while the data has silently frozen.
- `stats.api_ok` and `stats.last_error` make a key problem diagnosable from one curl after deploy.
- Timestamps are epoch seconds; the player computes the empty-for counter from `on_air.since`.

The player track commits a fixture at `data/channel/empty.sample.json`: this object twice over, with two different cams on air, so a slug change can be simulated by hand-editing. `.gitignore` and `.gcloudignore` both leave this path alone (checked 6:55 PM).

---

## Where each piece lands

| File | Change | Owner |
|---|---|---|
| `switcher.py` | new — loop, state machine, qualifier, state write | server track |
| `server.py` | two edits: start `switcher_loop` thread beside `sweep_loop`; add `/channel` route serving `channel.html` | server track |
| `deploy.sh` | add the env-var flag and a guard line (below) | server track |
| `channel.html` | new — full-screen player | player track |
| `data/channel/empty.sample.json` | new — fixture matching the contract | player track |
| `README.md` | story pass (skeleton under [[#Submission block]]) | player track |
| `requirements.txt` | **unchanged**, deliberately | — |

Route surface after the build: `/` control grid (untouched), `/channel` the channel, `/data/<path>` (already serves the state file), `/healthz`. No new data routes.

Player behavior (`channel.html`):

- Fetch `/data/channel/empty.json?t=<now>` every 2 s. A `?src=` query parameter overrides the state path, which is how the fixture drives it: `/channel?src=/data/channel/empty.sample.json`.
- Render `on_air.imageUrl` full-bleed (`object-fit: cover`, black background), refreshing the `?t=` cache-buster every 2 s. 352×240 upscaled is soft; that is the medium's texture, accept it.
- On `on_air.slug` change: hard cut. Crossfade can be dropped without loss; see [[#What to cut if late]].
- Lower-third caption from state-file fields only: EMPTY NEW YORK, camera name, borough, empty-for counter. In degraded mode, a quiet "scanning for empty streets" line instead of the counter.
- `<img>` error: hold the last good frame (the server benches failing cams and will move within a tick or two). State-fetch errors: hold the frame and show the scanning line. The screen never goes blank or shows a broken-image glyph.

---

## Key provisioning and deploy

All existing deploy flags stand exactly as they are in `deploy.sh` (min-instances, no-cpu-throttling, 2Gi, 2 CPU, clear-base-image). The switcher adds no meaningful memory: it holds no decoded frames (Roboflow fetches imagery itself), so the 2Gi headroom analysis is unchanged.

Two additions to `deploy.sh`:

```bash
: "${ROBOFLOW_API_KEY:?export ROBOFLOW_API_KEY first}"    # guard near the top
# and on the gcloud line:
--set-env-vars "ROBOFLOW_API_KEY=${ROBOFLOW_API_KEY}"
```

The key is read from the deploying shell at deploy time and never lands in the repo. Without this flag the container has no key at all: `.env` is git-ignored, `.gcloudignore`d, `.dockerignore`d, and not present in this clone anyway.

Deploy freeze at **8:15 PM**. After that, no deploys for any reason; whatever is live is the demo.

---

## Two-builder split

**Server track — Ida's machine, executed by the Opus session.** Her machine has the gcloud auth and tonight's deploy history. Owns `switcher.py`, `server.py`, `deploy.sh`, the key, and all deploys.

**Player track — Jeff's machine.** The repo lives under his GitHub account, so only he can flip visibility, and the player is fully verifiable alone against the fixture. Owns `channel.html`, the fixture, `README.md`, repo visibility, and the fallback clip.

**Git ground truth, verified 6:50 PM:** `main` and `origin/main` are in sync (0/0) — the divergence noted in the brief has been resolved. The working tree has uncommitted changes (`README.md` plus regenerated sweep JPEGs). First moves, before splitting:

1. Commit and push the current working tree.
2. Optional hygiene, two commands, recommended: the sweep JPEGs under `data/sweep/latest/` are tracked and rewritten every pass, which will dirty every pull tonight. `git rm -r --cached data/sweep/latest/` plus a `.gitignore` line stops that. Skip if it causes any friction.

Rules for the night: both commit small and often to `main`; `git pull --rebase` before every push. No file has two owners, so rebases should be clean.

**What each verifies alone.** Server track: curl the local state file twice, 30 s apart, and watch `ts` and `tick` advance and the on-air cam change within 3 minutes. Player track: open the page with `?src=` pointed at the fixture, edit the fixture's on-air slug, and watch the cut land within 2 s.

**Jeff stepping away is survivable by design:** after the player renders the fixture correctly, everything left on his list (README, clip, stretch items) is interruptible, and the server track never waits on him.

---

## Execution plan with acceptance checks

Gates are wall-clock times. Every step names what a builder observes to know the step worked; "it ran" proves nothing here. The reference failure is the 2Gi OOM, where the page served normally while the data froze, so every check below checks freshness or behavior rather than whether the page serves.

### By 7:15 — repo public, key verified, tree committed

- [ ] **Repo public** (Jeff, GitHub Settings → change visibility). The `inquiry/` and `ledgers/` folders are already git-ignored for exactly this. **Check:** `curl -s -o /dev/null -w "%{http_code}" https://github.com/jvnickerson/roboflow_hack` from any shell returns 200, unauthenticated.
- [ ] **Working tree committed and pushed** (server track). **Check:** `git status -sb` clean, both machines pull the same head.
- [ ] **Raw Roboflow call verified** (server track, the curl under [[#The qualifier]]). **Check:** predictions JSON on screen. On failure, the 5-minute model-id box, then the SDK fallback decision.

### By 7:45 — switcher running locally, player rendering the fixture

- [ ] **Switcher skeleton running locally** (server track): loop, source list, rotation by list order, state file writing, no detection yet, `mode: "degraded"` throughout. **Check:** two curls of `localhost:8080/data/channel/empty.json` 30 s apart show `ts` and `tick` advanced and the on-air slug rotating. *This stage is itself shippable.*
- [ ] **Player renders the fixture** (player track). **Check:** the hand-edit-slug test above, plus caption fields correct, plus killing the state file leaves the last frame and the scanning line rather than a broken page.
- [ ] **Qualifier wired in** (server track). **Check:** local log line per tick shows person counts; a Times Square cam is visibly rejected (persons > 0) while some cam qualifies; `mode` flips to `"live"` when a streak completes.

### By 8:05 — deployed, integrated, fallback clip recorded

- [ ] **`/channel` route and thread startup in `server.py`** (server track). **Check:** local `python server.py` serves `/channel` and the state file stays fresh while the page is open.
- [ ] **Deployed with the env var.** **Check:** on the live URL, the state-file curl twice 30 s apart — `ts` advances, `api_ok` is `true`, `mode` reads `"live"` at least intermittently. Then open `/channel` and watch one full cut happen.
- [ ] **Integration** (player track): open the live `/channel`. By contract, nothing changes.
- [ ] **Fallback clip** (Jeff): screen-record the live channel for 60–90 s. **Check:** the file plays.

### 8:10 – 8:25 — form and README

Ida on the form (elements under [[#Submission block]]), player track finishing the README. Submit by **8:25**, five minutes inside the lock.

### Stretch — only if every gate above went green early

In order: crossfade on cuts; widen the source list; Natural New York as a second channel config; Jeff's 10-minute feed-discovery box below.

---

## Demo safety

What runs at 8:45, per failure:

- **A cam goes dark mid-demo:** the server benches it after 3 failed samples and moves on; the player holds the last frame meanwhile. With 21 cams in pool, the channel keeps cutting.
- **Roboflow goes down:** the switcher degrades to timed rotation automatically, same screen, scanning line on. The channel keeps cutting with the premise weakened.
- **Nothing qualifies for 60+ seconds** (plausible on a Friday night): degraded mode shows the least-occupied scene with the scanning line. Least-populated New York still reads as the premise.
- **Deploy broke at 8:20:** cannot happen by rule; the freeze is 8:15. Whatever is live demos. If the live service itself dies, `python server.py` on Ida's laptop and demo `localhost:8080/channel`; the Cloud Run criterion is satisfied by the deployed service either way.
- **Total failure:** the 8:05 fallback clip, which the event's own best-practices list asks for.

Demo setup: the live `/channel` full screen in one tab, the control grid at `/` in a second (one glance shows the system behind the channel), the fixture-driven player in a third for rehearsal before the slot.

---

## Feed discovery plan

Ruled: **no discovery before the submission gates.** Empty New York needs none. Discovery is one stretch box, suited to the side explorations Jeff takes anyway.

**The box (Jeff, 10 minutes, hard stop, only after the player passes its fixture check):** open the handbook's Reddit collection of NYC 24/7 live cameras and hunt only for cameras mounted on things that move (ferries, boats, vehicles). Per candidate:

- **Usable as a still:** `curl` the image URL twice, 5 s apart; the bytes differ. That cam could join a source list tonight.
- **Usable as video but display-only:** an unauthenticated `.m3u8` (curl returns `#EXTM3U`, or it plays in Safari). The container cannot read it tonight, so it can only be shown, not switched.
- **YouTube:** embeddable for a demo aside, not pipeline-readable. Note the id and move on.

**Partial result:** one found mover becomes a 15-second demo aside ("here is the channel that needs this camera"), embedded or narrated. It does not become a build track tonight.

**Declaring it unsourced:** if the box closes with nothing, New York in Motion is listed in the README as designed and awaiting a source, which is the honest state and a ready "what's next" line for judges.

Natural New York needs no discovery either: the 55 Water Street falcon poster still (server-refreshed JPEG at the `.m3u8` path ending `.jpg`, verified earlier this evening per the brief) plus name-grepped DOT cams. The Cuomo Bridge feed stays out: its burned-in 10/13/2025 timestamps are unresolved, and a possibly archival replay does not belong on a channel presented as live.

---

## Submission block

Content elements per form field. Ida phrases everything; nothing here is draft text.

- **Project name:** Ida's call. "Empty New York" is on the table; the three-channel frame ("NYC Channels," with Empty New York on air tonight) is the alternative shape.
- **Description (25+ words, must name judging criteria and technologies):** elements to hit — live working demo on real NYC DOT feeds (966-camera public registry); the channel premise and the cut-away-from-people privacy stance; Cloud Run (Flask, Python, background loops, the deploy flags story); Roboflow serverless `yolov8n-640` as the qualifier; NumPy/Pillow city-wide sweep; open repo.
- **Products and tools checkboxes:** Google Cloud, Roboflow.
- **Team contributions, per person, naming sponsor tools:** Ida — concept and channel design, source curation, Cloud Run deployment; Jeff — front-end player, repo and README, plus whatever his side explorations produced. Adjust to what actually happened by 8:25.
- **Prior work disclosure:** registry fetch, sweep, metrics, server scaffold, and the control grid predate the 4 PM start; tonight's build is the switcher, the qualifier integration, the channel player, and the deploy env-var work. State it plainly; the field exists so judges can score the split.
- **2-minute video (optional, judged):** the fallback clip trimmed is the candidate. Decide at 8:25, after the form is in.

README skeleton (player track writes it; it is a scored criterion): what this is (three channels, one on air tonight); how it works (the system-shape diagram above, roughly); run it (deploy.sh, the env var, the local fallback); data sourcing and privacy (public 352×240 DOT stills, faces and plates not resolvable at that resolution, detections used only to cut away from people, no imagery stored or proxied); prior work note matching the form; what's next (Motion awaiting a source, the multi-panel visual pass).

---

## What to cut if late

Named now so nobody discovers it at 8:15. Cut from the top:

1. Crossfade — hard cut ships fine.
2. Source-list widening — 21 cams is a working pool.
3. Natural New York config — the README's "what's next" absorbs it.
4. The discovery box — Motion is already cut; the box is a bonus.
5. Queue field richness — the player only strictly needs `on_air`; queue can ship sparse.
6. The video — optional by the form's own terms.

Not cuttable: repo public, the deployed switcher in whatever mode it reached, the form, the README in some honest state, the fallback clip.

---

## Open for Ida

- **Project name** (form field, her words).
- **Does "empty" mean empty of people specifically?** The spec rules persons-only and lets vehicles through, for the uncanny-image reason above. One constant flips it to persons-and-vehicles if her intent differs.
- **Caption wording** — defaults ship so nothing blocks; her words replace them whenever she wants, including after tonight.
