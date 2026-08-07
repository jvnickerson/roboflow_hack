"""Wet lens — find cameras with rain on the glass, composite them.

    .venv/bin/python wet.py                    # score midtown, composite top 6
    .venv/bin/python wet.py --pool 120 --top 8

Water on a lens is a weather instrument: it means rain fell here recently,
and it is the camera's own body showing up in its picture. Optically a
droplet is a tiny lens — it defocuses what is behind it and refracts point
lights into discs, so it moves image energy out of fine detail and into
mid-scale blobs, and unlike traffic it does not move between frames.

wetness() scores that: over N frames it takes the temporal median (traffic
averages away, droplets persist), then measures the ratio of mid-scale to
fine-scale energy in the parts of the frame that stayed still.

Honest limits, measured 2026-08-07 in heavy rain: the ranking puts the
most droplet-covered lenses on top, but separation from merely-rainy
scenes is weak, because in a citywide downpour nearly every lens is wet.
Single-frame features (bloom, blur, bokeh area) did not separate at all —
at 352x240 at night they measure "raining" rather than "on the glass".
A dry-night baseline per camera would settle it; we did not have one.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import io
import json
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

from cams import load, select, slug

DATA = Path(__file__).parent / "data"
TS_BAND = 0.09   # burned-in timestamp
NFRAMES = 4      # frames per camera for the temporal median
GAP = 3.0        # seconds between frames
NWS = "https://api.weather.gov/stations/KNYC/observations/latest"
UA = {"User-Agent": "nyc-vision-hack (jvnickerson@gmail.com)"}
FONTS = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"]


def font(size: int):
    for p in FONTS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def weather() -> dict:
    """Live conditions from the NWS station in Central Park (Belvedere Castle)."""
    try:
        p = requests.get(NWS, headers=UA, timeout=10).json()["properties"]
        c = p.get("temperature", {}).get("value")
        return {
            "text": p.get("textDescription") or "—",
            "temp_f": None if c is None else round(c * 9 / 5 + 32),
            "humidity": (lambda v: None if v is None else round(v))(
                p.get("relativeHumidity", {}).get("value")),
            "time": (p.get("timestamp") or "")[11:16],
        }
    except Exception:
        return {"text": "—", "temp_f": None, "humidity": None, "time": ""}


def fetch(cam: dict):
    try:
        b = requests.get(cam["imageUrl"], timeout=8).content
        img = Image.open(io.BytesIO(b))
        rgb = np.asarray(img.convert("RGB"))
        gray = np.asarray(img.convert("L"), dtype=np.float32)
        return gray[int(gray.shape[0] * TS_BAND):], rgb
    except Exception:
        return None, None


def wetness(frames: list[np.ndarray]) -> float | None:
    """Mid-scale vs fine-scale energy where the frame held still."""
    frames = [f for f in frames if f.shape == frames[0].shape]
    if len(frames) < 3:
        return None
    stack = np.stack(frames)
    med = np.median(stack, axis=0).astype(np.float32)
    motion = stack.std(axis=0)

    fine = np.abs(cv2.Laplacian(med, cv2.CV_32F, ksize=3))
    blob = np.abs(cv2.GaussianBlur(med, (0, 0), 1.5) - cv2.GaussianBlur(med, (0, 0), 5.0))

    still = motion < np.percentile(motion, 60)
    if still.sum() < still.size * 0.05:
        return None
    return float(blob[still].mean() / (fine[still].mean() + 1e-6))


def score_cameras(cams: list[dict], workers: int) -> list[dict]:
    stacks: dict[str, list] = {c["id"]: [] for c in cams}
    last: dict[str, np.ndarray] = {}
    for i in range(NFRAMES):
        with cf.ThreadPoolExecutor(workers) as pool:
            for cam, (gray, rgb) in zip(cams, pool.map(fetch, cams)):
                if gray is not None:
                    stacks[cam["id"]].append(gray)
                    last[cam["id"]] = rgb
        print(f"  frame {i+1}/{NFRAMES}")
        if i < NFRAMES - 1:
            time.sleep(GAP)

    out = []
    for cam in cams:
        w = wetness(stacks[cam["id"]]) if stacks[cam["id"]] else None
        if w is not None and cam["id"] in last:
            out.append({"cam": cam, "wetness": round(w, 4), "rgb": last[cam["id"]]})
    out.sort(key=lambda r: -r["wetness"])
    return out


def feather(size: tuple[int, int], inset: float = 0.55) -> np.ndarray:
    """Soft-edged alpha: opaque core falling to zero well inside the border."""
    w, h = size
    ax = np.linspace(-1, 1, w)
    ay = np.linspace(-1, 1, h)
    gx, gy = np.meshgrid(ax, ay)
    r = np.sqrt((gx ** 2 + gy ** 2) / 2)
    a = np.clip((1.0 - r) / inset, 0, 1)
    return (a ** 1.4).astype(np.float32)


def composite(rows: list[dict], wx: dict, out_path: Path,
              canvas=(1500, 1000)) -> None:
    """Feathered alpha-weighted average, with the brightest droplet bokeh
    allowed to bloom back through on top. Straight screen blending of six
    night frames saturates to white — the average keeps the structure."""
    W, H = canvas
    acc = np.zeros((H, W, 3), dtype=np.float32)   # sum of premultiplied colour
    wsum = np.zeros((H, W, 1), dtype=np.float32)  # sum of alpha
    peak = np.zeros((H, W, 3), dtype=np.float32)  # brightest contribution

    n = len(rows)
    for i, row in enumerate(rows):
        rgb = row["rgb"]
        rgb = rgb[int(rgb.shape[0] * TS_BAND):]   # drop burned-in timestamp
        src = Image.fromarray(rgb).convert("RGB")
        scale = 1.30 - 0.09 * i
        tw, th = int(W * scale), int(H * scale)
        im = np.asarray(src.resize((tw, th), Image.LANCZOS), dtype=np.float32) / 255.0

        ang = 2 * np.pi * i / max(1, n) + 0.4
        cx = W // 2 + int(np.cos(ang) * W * 0.17)
        cy = H // 2 + int(np.sin(ang) * H * 0.15)
        x0, y0 = cx - tw // 2, cy - th // 2

        a = feather((tw, th))[..., None]
        sx0, sy0 = max(0, -x0), max(0, -y0)
        dx0, dy0 = max(0, x0), max(0, y0)
        cw = min(tw - sx0, W - dx0)
        chh = min(th - sy0, H - dy0)
        if cw <= 0 or chh <= 0:
            continue

        chunk = im[sy0:sy0+chh, sx0:sx0+cw]
        al = a[sy0:sy0+chh, sx0:sx0+cw]
        acc[dy0:dy0+chh, dx0:dx0+cw] += chunk * al
        wsum[dy0:dy0+chh, dx0:dx0+cw] += al
        region = peak[dy0:dy0+chh, dx0:dx0+cw]
        peak[dy0:dy0+chh, dx0:dx0+cw] = np.maximum(region, chunk * al)

    base = acc / np.maximum(wsum, 1e-5)
    # let only the genuinely bright parts (droplet bokeh, headlights) bloom
    glow = np.clip(peak - 0.62, 0, 1) * 0.85
    out = np.clip(base + glow, 0, 1)
    out = out ** 1.04
    out[..., 2] = np.clip(out[..., 2] * 1.04 + 0.01, 0, 1)
    img = Image.fromarray((out * 255).astype(np.uint8))

    # scrim behind the text so the captions stay legible over bright bloom
    scrim = np.asarray(img, dtype=np.float32) / 255.0
    ramp = np.linspace(0.35, 0.0, 150)[:, None, None]
    scrim[:150] *= (1 - ramp)
    foot = np.linspace(0.0, 0.4, 170)[:, None, None]
    scrim[-170:] *= (1 - foot)
    img = Image.fromarray((np.clip(scrim, 0, 1) * 255).astype(np.uint8))

    d = ImageDraw.Draw(img)
    t = f"{wx['temp_f']}°F" if wx["temp_f"] is not None else ""
    hum = f"  humidity {wx['humidity']}%" if wx["humidity"] is not None else ""
    d.text((34, 30), "WATER ON THE LENS", fill=(255, 255, 255), font=font(34))
    d.text((34, 74), f"{wx['text']}  {t}{hum}   NWS Central Park {wx['time']} UTC",
           fill=(190, 205, 220), font=font(17))
    y = H - 26 - 19 * len(rows)
    for row in rows:
        d.text((34, y), f"{row['wetness']:.3f}   {row['cam']['name']}",
               fill=(160, 178, 196), font=font(15))
        y += 19
    img.save(out_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", type=int, default=60, help="cameras to score")
    ap.add_argument("--top", type=int, default=6, help="wettest N to composite")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--grep", default=None, help="restrict pool by name")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    wx = weather()
    print(f"NWS Central Park: {wx['text']} {wx['temp_f']}F at {wx['time']}Z")

    cams = select(load(), grep=args.grep)
    if len(cams) > args.pool:
        step = max(1, len(cams) // args.pool)
        cams = cams[::step][:args.pool]
    print(f"scoring {len(cams)} cameras over {NFRAMES} frames...")

    rows = score_cameras(cams, args.workers)
    print(f"\n{'wetness':>8}  camera")
    for r in rows[:12]:
        print(f"{r['wetness']:8.3f}  {r['cam']['name']}")

    # ranked list for the live piece (water.html) — no image data, just where
    ranked = [{
        "slug": slug(r["cam"]), "id": r["cam"]["id"], "name": r["cam"]["name"],
        "area": r["cam"].get("area"), "lat": r["cam"].get("latitude"),
        "lng": r["cam"].get("longitude"), "imageUrl": r["cam"]["imageUrl"],
        "wetness": r["wetness"],
    } for r in rows]
    (DATA / "wet_scores.json").write_text(json.dumps(
        {"observed": wx, "cameras": ranked}, indent=1))
    print(f"ranked {len(ranked)} -> data/wet_scores.json")

    top = rows[:args.top]
    out = Path(args.out) if args.out else DATA / "wet_composite.png"
    composite(top, wx, out)
    print(f"composite of {len(top)} wettest -> {out}")


if __name__ == "__main__":
    main()
