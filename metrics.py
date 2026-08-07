"""Complexity metrics per camera — static now, temporal once frames accumulate.

    .venv/bin/python metrics.py                # leaderboard over everything captured
    .venv/bin/python metrics.py --sort motion  # rank by movement diversity

Three scores per camera:
- colorfulness: Hasler-Susstrunk metric, averaged over that camera's frames.
  Needs frames only (no detections).
- class_entropy: Shannon entropy of detected object classes. Needs detect.py.
- motion_entropy: the temporal one. Detections in consecutive frames are
  greedily matched (same class, nearest centroid); each match yields a
  displacement vector, binned into 8 compass directions plus "still".
  Entropy over that distribution = how many *different kinds of movement*
  the camera sees. An intersection where everything flows one way scores
  low; one with crossing traffic, turning cars, pedestrians on two
  crosswalks scores high.

Writes data/leaderboard.json and prints a table.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

DATA = Path(__file__).parent / "data"
FRAMES = DATA / "frames"
DETECTIONS = DATA / "detections"

MATCH_RADIUS = 60.0  # px; max centroid travel between consecutive frames
STILL_RADIUS = 3.0   # px; below this a matched object counts as "still"


def colorfulness(path: Path) -> float:
    """Hasler & Susstrunk (2003)."""
    arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    rg = r - g
    yb = 0.5 * (r + g) - b
    return float(
        math.hypot(rg.std(), yb.std()) + 0.3 * math.hypot(rg.mean(), yb.mean())
    )


def entropy(counts: Counter) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((n / total) * math.log2(n / total) for n in counts.values() if n)


def direction_bin(dx: float, dy: float) -> str:
    if math.hypot(dx, dy) < STILL_RADIUS:
        return "still"
    octant = int(((math.degrees(math.atan2(-dy, dx)) + 382.5) % 360) // 45)
    return ["E", "NE", "N", "NW", "W", "SW", "S", "SE"][octant]


def match_frames(prev: list[dict], curr: list[dict]) -> list[tuple[float, float]]:
    """Greedy nearest-centroid matching within class; returns displacement vectors."""
    vectors = []
    used = set()
    for p in prev:
        best, best_d = None, MATCH_RADIUS
        for j, c in enumerate(curr):
            if j in used or c["class"] != p["class"]:
                continue
            d = math.hypot(c["x"] - p["x"], c["y"] - p["y"])
            if d < best_d:
                best, best_d = j, d
        if best is not None:
            used.add(best)
            c = curr[best]
            vectors.append((c["x"] - p["x"], c["y"] - p["y"]))
    return vectors


def camera_scores() -> list[dict]:
    scores = []
    det_by_slug = {}
    for f in sorted(DETECTIONS.glob("*.jsonl")) if DETECTIONS.exists() else []:
        rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        det_by_slug[f.stem] = sorted(rows, key=lambda r: r["ts"])

    for camdir in sorted(FRAMES.iterdir()) if FRAMES.exists() else []:
        if not camdir.is_dir():
            continue
        jpgs = sorted(camdir.glob("*.jpg"))
        if not jpgs:
            continue
        color = float(np.mean([colorfulness(p) for p in jpgs[-10:]]))

        rows = det_by_slug.get(camdir.name, [])
        classes = Counter(p["class"] for r in rows for p in r["predictions"])
        dirs: Counter = Counter()
        for prev, curr in zip(rows, rows[1:]):
            for dx, dy in match_frames(prev["predictions"], curr["predictions"]):
                dirs[direction_bin(dx, dy)] += 1

        scores.append({
            "slug": camdir.name,
            "frames": len(jpgs),
            "detections": sum(classes.values()),
            "colorfulness": round(color, 1),
            "class_entropy": round(entropy(classes), 3),
            "classes": dict(classes.most_common()),
            "motion_entropy": round(entropy(dirs), 3),
            "motion_bins": dict(dirs.most_common()),
        })
    return scores


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sort", default="colorfulness",
                    choices=["colorfulness", "class_entropy", "motion_entropy"])
    args = ap.parse_args()

    scores = sorted(camera_scores(), key=lambda s: -s[args.sort])
    (DATA / "leaderboard.json").write_text(json.dumps(scores, indent=1))
    print(f"{'camera':42s} {'frames':>6} {'objs':>5} {'color':>6} {'clsH':>6} {'movH':>6}")
    for s in scores:
        print(f"{s['slug'][:42]:42s} {s['frames']:6d} {s['detections']:5d} "
              f"{s['colorfulness']:6.1f} {s['class_entropy']:6.2f} {s['motion_entropy']:6.2f}")
    print(f"-- leaderboard written to data/leaderboard.json (sorted by {args.sort})")
