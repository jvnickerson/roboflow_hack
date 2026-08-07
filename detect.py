"""Roboflow loop — run detection over frames the poller has captured.

Usage:
    export ROBOFLOW_API_KEY=...
    .venv/bin/python detect.py                 # process all un-detected frames
    .venv/bin/python detect.py --follow        # keep watching index.jsonl (run beside poll.py)
    .venv/bin/python detect.py --limit 40

Model: ROBOFLOW_MODEL env var, default "yolov8n-640" (Roboflow-hosted COCO
core model — person, car, truck, bus, bicycle, dog, ...). Swap in any
Universe model id like "vehicle-detection-3mmwj/1" if the alias 401s.

Output: one JSONL per camera in data/detections/<slug>.jsonl —
{ts, cam_id, slug, model, predictions:[{class, confidence, x, y, width, height}]}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

DATA = Path(__file__).parent / "data"
INDEX = DATA / "frames" / "index.jsonl"
DETECTIONS = DATA / "detections"


def load_done() -> set[tuple[str, str]]:
    done = set()
    if DETECTIONS.exists():
        for f in DETECTIONS.glob("*.jsonl"):
            for line in f.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    done.add((r["slug"], r["ts"]))
    return done


def iter_index():
    if not INDEX.exists():
        return
    for line in INDEX.read_text().splitlines():
        if line.strip():
            yield json.loads(line)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max frames this run (0 = all)")
    ap.add_argument("--follow", action="store_true", help="poll index.jsonl for new frames")
    args = ap.parse_args()

    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        sys.exit("Set ROBOFLOW_API_KEY (app.roboflow.com -> Settings -> API Keys)")
    model_id = os.environ.get("ROBOFLOW_MODEL", "yolov8n-640")

    from inference_sdk import InferenceHTTPClient

    client = InferenceHTTPClient(api_url="https://serverless.roboflow.com", api_key=api_key)
    DETECTIONS.mkdir(exist_ok=True)

    done = load_done()
    processed = 0
    while True:
        fresh = [e for e in iter_index() if (e["slug"], e["ts"]) not in done]
        for entry in fresh:
            frame = DATA.parent / entry["path"]
            if not frame.exists():
                continue
            try:
                result = client.infer(str(frame), model_id=model_id)
            except Exception as exc:
                print(f"  ! {entry['slug']} {entry['ts']}: {exc}")
                continue
            record = {
                "ts": entry["ts"],
                "cam_id": entry["cam_id"],
                "slug": entry["slug"],
                "model": model_id,
                "predictions": [
                    {k: p[k] for k in ("class", "confidence", "x", "y", "width", "height")}
                    for p in result.get("predictions", [])
                ],
            }
            with (DETECTIONS / f"{entry['slug']}.jsonl").open("a") as fh:
                fh.write(json.dumps(record) + "\n")
            done.add((entry["slug"], entry["ts"]))
            processed += 1
            classes = [p["class"] for p in record["predictions"]]
            print(f"{entry['slug']} {entry['ts']}: {len(classes)} objs {sorted(set(classes))}")
            if args.limit and processed >= args.limit:
                print(f"limit {args.limit} reached")
                return
        if not args.follow:
            break
        time.sleep(3)
    print(f"done — {processed} frames detected")


if __name__ == "__main__":
    main()
