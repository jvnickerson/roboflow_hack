"""Channel switcher — picks which cam is on air, writes data/channel/<name>.json.

Runs as a daemon thread beside sweep_loop (see server.py), or standalone:

    export ROBOFLOW_API_KEY=...   # optional; without it the loop runs in
    python switcher.py            # degraded mode (timed rotation, no detection)

One loop, one writer. The qualifier (Roboflow person count) runs inside the
loop; API failures count as no sample and the loop keeps rotating, so boot,
Roboflow outage, and a too-crowded city all share the degraded code path.
The screen is never blank and the state file is never torn (tmp + os.replace).
"""

from __future__ import annotations

import io
import json
import os
import threading
import time
import urllib.parse

import numpy as np
import requests
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))

TICK = 6            # loop interval; DOT stills refresh ~every 2 s, faster sampling wastes calls
POOL_PER_TICK = 5   # pool cams sampled per tick, round-robin (31-cam list rescans ~40s)
PERSON_CONF = 0.05  # near-zero on purpose: night at 352x240 puts visible crowds at
                    # 0.05-0.39 confidence (measured 2026-08-07 7 PM, rain). Over-cutting
                    # is safe for this channel; showing a crowd captioned "empty" is not.
VEHICLE_CONF = 0.25 # vehicles detect stronger at night; "empty" means no people AND no traffic
                    # (Ida's call, 8-07 ~7:40 PM, after seeing the first deploy on air)
API_CONF = 0.05     # ask the API for everything; the hosted default (0.4) hides night people
QUALIFY_STREAK = 2  # consecutive person-free samples to qualify; one occupied sample re-arms
MIN_DWELL = 12      # min seconds on air before a rotation (never blocks a disqualification cut)
MAX_DWELL = 45      # rotate to the next qualified cam even if the current one is still empty
COOLDOWN = 120      # a cam that leaves the air cannot return for this long
FAIL_LIMIT = 3      # consecutive fetch/API failures before a cam is benched
FAIL_BENCH = 600    # bench duration in seconds

MODEL = os.environ.get("ROBOFLOW_MODEL", "coco/3")  # hosted COCO; the "yolov8n-640" alias 404s over raw HTTP
PERSON_CLASSES = {"person"}
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "bicycle", "train"}

NOIR_SPREAD = 0.55  # (p95-p5)/255 tonal range floor — 1940s noir wants the full ladder
NOIR_DARK = 0.35    # fraction of pixels in deep shadow (<50)
NOIR_BRIGHT = 0.02  # fraction of pixels in hard highlight (>200)

CHANNELS = {
    "empty": {
        "kind": "empty",
        "sources": "data/empty_cams.json",
        "state": "data/channel/empty.json",
    },
    "noir": {
        "kind": "noir",
        "sources": "data/noir_cams.json",
        "state": "data/channel/noir.json",
    },
}


def count_occupants(image_url: str, api_key: str) -> int | None:
    """One Roboflow serverless call; the API fetches the image URL itself.

    Returns how many people or vehicles occupy the scene, or None on any
    failure (treated as no sample). "Empty" means zero of either.
    """
    url = (
        f"https://serverless.roboflow.com/{MODEL}"
        f"?api_key={api_key}&image={urllib.parse.quote(image_url, safe='')}&confidence={API_CONF}"
    )
    resp = requests.post(url, timeout=10)
    data = resp.json()  # non-JSON raises -> caller counts a failure
    preds = data["predictions"]  # missing key raises -> failure
    n = 0
    for p in preds:
        cls, conf = p.get("class"), p.get("confidence", 0)
        if cls in PERSON_CLASSES and conf >= PERSON_CONF:
            n += 1
        elif cls in VEHICLE_CLASSES and conf >= VEHICLE_CONF:
            n += 1
    return n


def noir_badness(image_url: str) -> int | None:
    """Distance from noir, 0 = qualifies. None on any failure (no sample).

    Noir = deep shadows AND hard highlights AND a wide tonal range,
    computed from the frame itself — no detection API involved.
    """
    resp = requests.get(image_url, timeout=8)
    g = np.asarray(Image.open(io.BytesIO(resp.content)).convert("L"), dtype=np.float32)
    p5, p95 = np.percentile(g, [5, 95])
    spread = (p95 - p5) / 255
    dark = float((g < 50).mean())
    bright = float((g > 200).mean())
    deficit = (
        max(0.0, NOIR_SPREAD - spread)
        + max(0.0, NOIR_DARK - dark)
        + max(0.0, (NOIR_BRIGHT - bright) * 10)  # scale up: the bright band is narrow
    )
    return int(round(deficit * 100))


class CamState:
    __slots__ = ("cam", "streak", "persons", "sampled_at", "fails", "bench_until", "cooldown_until")

    def __init__(self, cam: dict):
        self.cam = cam
        self.streak = 0          # consecutive person-free samples
        self.persons: int | None = None  # last sample's person count
        self.sampled_at = 0.0
        self.fails = 0
        self.bench_until = 0.0
        self.cooldown_until = 0.0

    def available(self, now: float) -> bool:
        return now >= self.bench_until

    def qualified(self, now: float) -> bool:
        return self.available(now) and now >= self.cooldown_until and self.streak >= QUALIFY_STREAK


def slug(cam: dict) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in cam["name"].lower()).strip("-")[:60]


def switcher_loop(channel: str = "empty") -> None:
    cfg = CHANNELS[channel]
    src_path = os.path.join(ROOT, cfg["sources"])
    if not os.path.exists(src_path):
        raise SystemExit(f"switcher_loop: source list missing: {src_path}")
    with open(src_path) as fh:
        cams = json.load(fh)
    print(f"switcher_loop[{channel}]: {len(cams)} cams loaded")

    state_path = os.path.join(ROOT, cfg["state"])
    os.makedirs(os.path.dirname(state_path), exist_ok=True)

    kind = cfg.get("kind", "empty")
    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if kind == "empty" and not api_key:
        print(f"switcher_loop[{channel}]: no ROBOFLOW_API_KEY — degraded mode (timed rotation)")

    states = [CamState(c) for c in cams]  # list order = busyness priority
    on_air = states[0]
    on_air_since = time.time()
    previous: CamState | None = None
    pool_ptr = 0
    tick = 0
    api_calls = 0
    api_ok = True
    last_error: str | None = None

    def sample(cs: CamState, now: float) -> None:
        nonlocal api_calls, api_ok, last_error
        if (kind == "empty" and not api_key) or not cs.available(now):
            return
        api_calls += 1
        try:
            if kind == "noir":
                n = noir_badness(cs.cam["imageUrl"])
            else:
                n = count_occupants(cs.cam["imageUrl"], api_key)
        except Exception as exc:
            n = None
            last_error = f"{type(exc).__name__}: {exc}"[:200]
        cs.sampled_at = now
        if n is None:
            api_ok = False
            cs.fails += 1
            if cs.fails >= FAIL_LIMIT:
                cs.bench_until = now + FAIL_BENCH
                cs.fails = 0
                print(f"switcher: benched {slug(cs.cam)} for {FAIL_BENCH}s")
            return
        api_ok = True
        cs.fails = 0
        cs.persons = n
        cs.streak = cs.streak + 1 if n == 0 else 0

    def go_on_air(cs: CamState, now: float) -> None:
        nonlocal on_air, on_air_since, previous
        if cs is on_air:
            return
        on_air.cooldown_until = now + COOLDOWN
        previous = on_air
        on_air = cs
        on_air_since = now

    while True:
        started = time.time()
        tick += 1
        now = started

        # 1. Sample the on-air cam; any person cuts away immediately.
        sample(on_air, now)
        if on_air.persons and on_air.sampled_at >= now:
            on_air.streak = 0

        # 2. Round-robin the pool.
        for _ in range(POOL_PER_TICK):
            cs = states[pool_ptr % len(states)]
            pool_ptr += 1
            if cs is not on_air:
                sample(cs, now)

        # 3. Select on air.
        qualified = [cs for cs in states if cs.qualified(now)]
        dwell = now - on_air_since
        occupied = bool(on_air.persons) and on_air.sampled_at >= now
        candidates = [cs for cs in qualified if cs is not on_air]
        if occupied and candidates:
            go_on_air(candidates[0], now)  # premise cut — overrides MIN_DWELL
        elif dwell >= MAX_DWELL:
            nxt = None
            if candidates:
                i = states.index(on_air)
                ordered = states[i + 1:] + states[:i]
                nxt = next((cs for cs in ordered if cs in candidates), candidates[0])
            elif not api_key or not qualified:
                # degraded rotation: fewest persons in last sample, ties by list order
                pool = [cs for cs in states if cs is not on_air and cs.available(now)]
                if pool:
                    nxt = min(pool, key=lambda cs: (cs.persons if cs.persons is not None else 10**6,
                                                    states.index(cs)))
            if nxt is not None:
                go_on_air(nxt, now)
        elif dwell >= MIN_DWELL and candidates:
            best = min(qualified, key=states.index)  # priority = source list order
            if best is not on_air:
                go_on_air(best, now)

        # 4. Mode: live only when the on-air cam actually qualified.
        live = on_air.qualified(now)
        state = {
            "channel": channel,
            "mode": "live" if live else "degraded",
            "ts": int(now),
            "tick": tick,
            "on_air": {
                "slug": slug(on_air.cam),
                "name": on_air.cam["name"],
                "area": on_air.cam.get("area", ""),
                "imageUrl": on_air.cam["imageUrl"],
                "since": int(on_air_since),
                "persons": on_air.persons if on_air.persons is not None else 0,
                "reason": "qualified" if live else "degraded_best",
            },
            "previous": (
                {"slug": slug(previous.cam), "name": previous.cam["name"]} if previous else None
            ),
            "queue": [
                {
                    "slug": slug(cs.cam),
                    "name": cs.cam["name"],
                    "area": cs.cam.get("area", ""),
                    "imageUrl": cs.cam["imageUrl"],
                    "persons": cs.persons,
                    "streak": cs.streak,
                }
                for cs in qualified if cs is not on_air
            ],
            "stats": {
                "list_size": len(states),
                "qualified_now": len(qualified),
                "api_calls": api_calls,
                "api_ok": api_ok,
                "last_error": last_error,
            },
        }

        # 5. Atomic write — the player can never read a torn JSON.
        tmp = state_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(state, fh)
        os.replace(tmp, state_path)

        if tick % 5 == 1:
            print(
                f"switcher[{channel}] tick {tick}: on_air={slug(on_air.cam)} "
                f"mode={state['mode']} persons={on_air.persons} "
                f"qualified={len(qualified)} api_ok={api_ok}"
            )

        time.sleep(max(1.0, TICK - (time.time() - started)))


if __name__ == "__main__":
    import sys
    switcher_loop(sys.argv[1] if len(sys.argv) > 1 else "empty")
