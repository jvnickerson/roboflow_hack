"""Roboflow inference demo — NYC Vision Hack v.2.

Runs the public soccer-players model against Roboflow's sample image via the
hosted serverless API (no local inference server needed).

Needs ROBOFLOW_API_KEY in the environment (app.roboflow.com -> Settings -> API Keys):
    export ROBOFLOW_API_KEY=...
    .venv/bin/python robo.py
"""

import os
import sys

from inference_sdk import InferenceHTTPClient

api_key = os.environ.get("ROBOFLOW_API_KEY")
if not api_key:
    sys.exit("Set ROBOFLOW_API_KEY first (get it from app.roboflow.com -> Settings -> API Keys)")

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=api_key,
)

result = client.infer(
    "https://media.roboflow.com/inference/soccer.jpg",
    model_id="soccer-players-5fuqs/1",
)

predictions = result["predictions"]
print(f"{len(predictions)} detections")
for p in predictions:
    print(f"  {p['class']:12s} conf={p['confidence']:.2f} at ({p['x']:.0f},{p['y']:.0f})")
