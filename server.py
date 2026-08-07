"""Cloud Run entrypoint — serves control.html + data/, sweeps in the background.

    python server.py            # local: http://localhost:8080
    gcloud run deploy --source . picks this up via the Dockerfile's CMD.

IMPORTANT deploy flags (see README): Cloud Run throttles CPU to ~0 between
requests by default, which stalls the background sweep thread, and scales
to zero after idle, which kills it. Deploy with:
    --min-instances=1 --no-cpu-throttling
"""

from __future__ import annotations

import json
import os
import threading
import time

from flask import Flask, send_from_directory

import cams
import sweep

ROOT = os.path.dirname(os.path.abspath(__file__))
SWEEP_INTERVAL = 120  # seconds between full-city passes

app = Flask(__name__, static_folder=None)


def sweep_loop() -> None:
    cams.refresh()
    online = cams.select(cams.load())
    print(f"sweep_loop: watching {len(online)} online cams")
    prev: dict = {}
    while True:
        try:
            scores, prev = sweep.sweep_pass(online, workers=20, prev_arrays=prev)
            sweep.SCORES.write_text(json.dumps(scores))
        except Exception as exc:  # keep the loop alive across transient failures
            print(f"sweep pass failed: {exc}")
        time.sleep(SWEEP_INTERVAL)


@app.route("/")
def index():
    return send_from_directory(ROOT, "control.html")


@app.route("/data/<path:path>")
def data(path):
    return send_from_directory(os.path.join(ROOT, "data"), path)


@app.route("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    threading.Thread(target=sweep_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), threaded=True)
