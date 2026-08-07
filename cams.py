"""Camera registry — fetch and filter the public NYC DOT camera list.

Usage:
    .venv/bin/python cams.py --refresh              # fetch registry -> data/cameras.json
    .venv/bin/python cams.py --borough Manhattan    # list matching cams
    .venv/bin/python cams.py --grep "park"          # name search (case-insensitive)

The registry is a list of dicts: id, name, latitude, longitude, area,
isOnline, imageUrl, source. Other sources (511NY, Windy, ...) can be merged
in later with the same shape; `source` marks provenance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

DOT_API = "https://webcams.nyctmc.org/api/cameras"
DATA = Path(__file__).parent / "data"
REGISTRY = DATA / "cameras.json"


def refresh() -> list[dict]:
    cams = requests.get(DOT_API, timeout=30).json()
    for c in cams:
        c["source"] = "nyc-dot"
    DATA.mkdir(exist_ok=True)
    REGISTRY.write_text(json.dumps(cams, indent=1))
    return cams


def load() -> list[dict]:
    if not REGISTRY.exists():
        return refresh()
    return json.loads(REGISTRY.read_text())


def select(
    cams: list[dict] | None = None,
    *,
    borough: str | None = None,
    grep: str | None = None,
    online_only: bool = True,
) -> list[dict]:
    cams = cams if cams is not None else load()
    if online_only:
        cams = [c for c in cams if str(c.get("isOnline")).lower() == "true"]
    if borough:
        cams = [c for c in cams if c.get("area", "").lower() == borough.lower()]
    if grep:
        cams = [c for c in cams if grep.lower() in c.get("name", "").lower()]
    return cams


def slug(cam: dict) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in cam["name"].lower()).strip("-")[:60]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--borough")
    ap.add_argument("--grep")
    ap.add_argument("--all", action="store_true", help="include offline cams")
    args = ap.parse_args()

    cams = refresh() if args.refresh else load()
    picked = select(cams, borough=args.borough, grep=args.grep, online_only=not args.all)
    for c in picked:
        print(f"{c['id']}  {c['area']:14s} {c['name']}")
    print(f"-- {len(picked)} cameras ({len(cams)} total in registry)")
