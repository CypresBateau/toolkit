import os
import numpy as np
from PIL import Image, ImageDraw

root = "/data/wxb/toolkit/MVFA-AD/data/demo_medical_ad"

dirs = [
    f"{root}/test/good",
    f"{root}/test/anomaly",
    f"{root}/ground_truth/anomaly",
]

for d in dirs:
    os.makedirs(d, exist_ok=True)

def make_normal(path, seed):
    rng = np.random.default_rng(seed)
    img = rng.normal(80, 12, size=(336, 336)).clip(0, 255).astype(np.uint8)

    yy, xx = np.mgrid[:336, :336]
    body = ((xx - 168) ** 2 / 120 ** 2 + (yy - 168) ** 2 / 145 ** 2) < 1
    img[body] = np.clip(img[body] + 60, 0, 255)

    Image.fromarray(img).save(path)

def make_anomaly(img_path, mask_path, seed):
    rng = np.random.default_rng(seed)
    img = rng.normal(80, 12, size=(336, 336)).clip(0, 255).astype(np.uint8)

    yy, xx = np.mgrid[:336, :336]
    body = ((xx - 168) ** 2 / 120 ** 2 + (yy - 168) ** 2 / 145 ** 2) < 1
    img[body] = np.clip(img[body] + 60, 0, 255)

    pil = Image.fromarray(img)
    draw = ImageDraw.Draw(pil)

    cx = int(rng.integers(120, 220))
    cy = int(rng.integers(120, 220))
    r = int(rng.integers(18, 35))

    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=230)
    pil.save(img_path)

    mask = Image.new("L", (336, 336), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    mask.save(mask_path)

for i in range(5):
    make_normal(f"{root}/test/good/{i:03d}.png", seed=i)

for i in range(5):
    make_anomaly(
        f"{root}/test/anomaly/{i:03d}.png",
        f"{root}/ground_truth/anomaly/{i:03d}_mask.png",
        seed=100 + i,
    )

print(f"Demo dataset created at: {root}")