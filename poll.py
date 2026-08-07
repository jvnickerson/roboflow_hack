"""Poller — snapshot a set of cameras on an interval.

Usage:
    .venv/bin/python poll.py --grep "central park" --minutes 10 --interval 4
    .venv/bin/python poll.py --ids <id1> <id2> --minutes 5
    .venv/bin/python poll.py --borough Manhattan --sample 12 --minutes 30

Frames land in data/frames/<slug>/<utc-ts>.jpg; every capture is also
appended to data/frames/index.jsonl (cam_id, slug, ts, path, bytes) so the
detection loop can pick up exactly what's new.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from cams import load, select, slug

DATA = Path(__file__).parent / "data"
FRAMES = DATA / "frames"
INDEX = FRAMES / "index.jsonl"


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def snap(cam: dict, session: requests.Session) -> dict | None:
    try:
        r = session.get(cam["imageUrl"], timeout=10)
        r.raise_for_status()
    except requests.RequestException as exc:
        print(f"  ! {cam['name']}: {exc}")
        return None
    s = slug(cam)
    ts = utc_ts()
    out = FRAMES / s / f"{ts}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    entry = {
        "cam_id": cam["id"],
        "slug": s,
        "name": cam["name"],
        "area": cam.get("area"),
        "lat": cam.get("latitude"),
        "lng": cam.get("longitude"),
        "ts": ts,
        "path": str(out.relative_to(DATA.parent)),
        "bytes": len(r.content),
    }
    with INDEX.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--borough")
    ap.add_argument("--grep")
    ap.add_argument("--sample", type=int, help="random sample size from the selection")
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--interval", type=float, default=4.0, help="seconds between rounds")
    args = ap.parse_args()

    cams = load()
    if args.ids:
        byid = {c["id"]: c for c in cams}
        picked = [byid[i] for i in args.ids if i in byid]
    else:
        picked = select(cams, borough=args.borough, grep=args.grep)
        if args.sample and args.sample < len(picked):
            picked = random.sample(picked, args.sample)
    if not picked:
        raise SystemExit("no cameras matched")

    print(f"polling {len(picked)} cams every {args.interval}s for {args.minutes} min")
    session = requests.Session()
    deadline = time.time() + args.minutes * 60
    rounds = 0
    while time.time() < deadline:
        t0 = time.time()
        got = sum(1 for cam in picked if snap(cam, session))
        rounds += 1
        print(f"round {rounds}: {got}/{len(picked)} frames")
        time.sleep(max(0.0, args.interval - (time.time() - t0)))
    print(f"done — {rounds} rounds; frames under {FRAMES}")


if __name__ == "__main__":
    main()
