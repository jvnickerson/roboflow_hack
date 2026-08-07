"""City-wide sweep — cheap salience for every online cam, no API calls.

    .venv/bin/python sweep.py                # two passes -> churn for all ~966
    .venv/bin/python sweep.py --loop         # sweep forever (one pass / --interval)
    .venv/bin/python sweep.py --workers 20 --interval 120

Each pass fetches every online camera once (threaded, ~30s for the city).
Per camera it computes:
- colorfulness (Hasler-Susstrunk, shared with metrics.py)
- churn: mean absolute grayscale difference vs the SAME camera's previous
  sweep image, as a percent — the top 8% of the frame is cropped first
  (burned-in timestamp would otherwise register as constant movement).

This is the peripheral tier: it ranks all 966 continuously for free, so
detection (detect.py) can be spent only on the salient few.

Output: data/sweep/scores.json — [{slug, id, name, area, lat, lng, ts,
colorfulness, churn}]. control.html merges it with leaderboard.json.
Latest JPEGs kept in data/sweep/latest/<slug>.jpg (overwritten each pass).
"""

from __future__ import annotations

import argparse
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from PIL import Image

from cams import load, select, slug
from metrics import colorfulness_arr

DATA = Path(__file__).parent / "data"
SWEEP = DATA / "sweep"
LATEST = SWEEP / "latest"
SCORES = SWEEP / "scores.json"
TS_BAND = 0.08  # crop this fraction off the top: burned-in timestamp
SERVICE_COLORFULNESS = 6.0  # below this it's the gray "being serviced" card
                            # (card measures ~2; grayest real street ~11)


def fetch(cam: dict) -> tuple[dict, bytes | None]:
    try:
        r = requests.get(cam["imageUrl"], timeout=8)
        r.raise_for_status()
        return cam, r.content
    except requests.RequestException:
        return cam, None


def to_array(data: bytes) -> np.ndarray | None:
    try:
        return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), dtype=np.float32)
    except Exception:
        return None


def churn_pct(prev: np.ndarray, curr: np.ndarray) -> float | None:
    if prev.shape != curr.shape:
        return None
    cut = int(curr.shape[0] * TS_BAND)
    a, b = prev[cut:].mean(axis=2), curr[cut:].mean(axis=2)
    return float(np.abs(a - b).mean() / 255.0 * 100.0)


def sweep_pass(cams: list[dict], workers: int, prev_arrays: dict) -> tuple[list[dict], dict]:
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    LATEST.mkdir(parents=True, exist_ok=True)
    scores, arrays = [], {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for cam, data in pool.map(fetch, cams):
            if data is None:
                continue
            arr = to_array(data)
            if arr is None:
                continue
            s = slug(cam)
            color = colorfulness_arr(arr)
            serviced = color < SERVICE_COLORFULNESS
            if not serviced:
                arrays[s] = arr  # only real frames participate in churn
            (LATEST / f"{s}.jpg").write_bytes(data)
            scores.append({
                "slug": s,
                "id": cam["id"],
                "name": cam["name"],
                "area": cam.get("area"),
                "lat": cam.get("latitude"),
                "lng": cam.get("longitude"),
                "ts": ts,
                "serviced": serviced,
                "colorfulness": round(color, 1),
                "churn": (None if serviced or s not in prev_arrays
                          else round(churn_pct(prev_arrays[s], arr) or 0.0, 2)),
            })
    got_churn = sum(1 for s in scores if s["churn"] is not None)
    print(f"pass done in {time.time()-t0:.0f}s: {len(scores)}/{len(cams)} cams fetched, "
          f"{got_churn} with churn")
    return scores, arrays


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--interval", type=float, default=120.0, help="seconds between passes")
    ap.add_argument("--loop", action="store_true", help="keep sweeping until killed")
    args = ap.parse_args()

    cams = select(load())
    print(f"sweeping {len(cams)} online cams ({args.workers} workers)")

    prev: dict = {}
    first = True
    while True:
        scores, prev = sweep_pass(cams, args.workers, prev)
        SCORES.write_text(json.dumps(scores))
        top = sorted((s for s in scores if s["churn"] is not None),
                     key=lambda s: -s["churn"])[:5]
        for s in top:
            print(f"  churn {s['churn']:5.2f}%  {s['area']:14s} {s['name']}")
        if not args.loop and not first:
            break
        if not args.loop and first:
            first = False
            time.sleep(8)  # short gap so the default two-pass run yields churn
            continue
        time.sleep(args.interval)
    print(f"scores -> {SCORES}")


if __name__ == "__main__":
    main()
