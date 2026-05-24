"""
inference.py — 图像预处理 + 单张推理后处理。

对标 MVFA-AD/test_zero.py 的核心 test() 逻辑：
1. image -> CLIP_Inplanted；
2. det patch token -> image-level anomaly score；
3. seg patch token -> pixel-level anomaly map；
4. 单图 API 返回 score + heatmap。
"""

from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms

if TYPE_CHECKING:
    from .model_singleton import ModelSingleton


def _build_transform(img_size: int) -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize((img_size, img_size), Image.BICUBIC),
            transforms.ToTensor(),
        ]
    )


def _load_image_bytes(data: bytes, filename: str) -> Image.Image:
    """从原始字节加载 PIL.Image。MVFA-AD 官方 benchmark 使用普通图像输入。"""
    return Image.open(io.BytesIO(data)).convert("RGB")


def _normalize_map(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    mn, mx = float(x.min()), float(x.max())

    if mx - mn < 1e-8:
        return np.zeros_like(x, dtype=np.float32)

    return (x - mn) / (mx - mn)


def _heatmap_to_base64(heatmap: np.ndarray) -> str:
    """把 0-1 heatmap 编码为 PNG base64，方便 Gateway/前端传输。"""
    heatmap = _normalize_map(heatmap)
    arr = (heatmap * 255).clip(0, 255).astype(np.uint8)

    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    return base64.b64encode(buf.getvalue()).decode("utf-8")


def run_inference(
    image_bytes: bytes,
    filename: str,
    singleton: "ModelSingleton",
    obj: str,
    return_heatmap: bool = True,
) -> dict:
    """
    对单张图像执行推理。

    返回：
    - anomaly_score_raw: 未归一化图像级异常分数
    - anomaly_score: 平均后的图像级异常分数
    - heatmap_png_base64: PNG base64 格式异常热图
    """
    singleton.set_object(obj)

    img = _load_image_bytes(image_bytes, filename)
    transform = _build_transform(singleton.img_size)
    image = transform(img).unsqueeze(0).to(singleton.device)

    model = singleton.model
    text_features = singleton.get_text_features(obj)

    with torch.no_grad(), torch.cuda.amp.autocast(enabled=(singleton.device.type == "cuda")):
        _, ori_seg_patch_tokens, ori_det_patch_tokens = model(image)

        ori_seg_patch_tokens = [p[0, 1:, :] for p in ori_seg_patch_tokens]
        ori_det_patch_tokens = [p[0, 1:, :] for p in ori_det_patch_tokens]

        # ── image-level anomaly score，对标 test_zero.py image 分支 ─────────────
        anomaly_score = 0.0
        det_patch_tokens = ori_det_patch_tokens.copy()

        for layer in range(len(det_patch_tokens)):
            det_patch_tokens[layer] /= det_patch_tokens[layer].norm(dim=-1, keepdim=True)
            anomaly_map = (100.0 * det_patch_tokens[layer] @ text_features).unsqueeze(0)
            anomaly_map = torch.softmax(anomaly_map, dim=-1)[:, :, 1]
            anomaly_score += anomaly_map.mean()

        anomaly_score_raw = float(anomaly_score.detach().float().cpu().item())
        anomaly_score_avg = anomaly_score_raw / max(len(det_patch_tokens), 1)

        # ── pixel-level anomaly map，对标 test_zero.py pixel 分支 ───────────────
        heatmap_png_base64 = None

        if return_heatmap:
            seg_patch_tokens = ori_seg_patch_tokens
            anomaly_maps = []

            for layer in range(len(seg_patch_tokens)):
                seg_patch_tokens[layer] /= seg_patch_tokens[layer].norm(dim=-1, keepdim=True)
                anomaly_map = (100.0 * seg_patch_tokens[layer] @ text_features).unsqueeze(0)

                b, l, c = anomaly_map.shape
                h = int(np.sqrt(l))

                anomaly_map = F.interpolate(
                    anomaly_map.permute(0, 2, 1).view(b, 2, h, h),
                    size=singleton.img_size,
                    mode="bilinear",
                    align_corners=True,
                )

                anomaly_map = torch.softmax(anomaly_map, dim=1)[:, 1, :, :]
                anomaly_maps.append(anomaly_map.float().cpu().numpy())

            final_score_map = np.sum(anomaly_maps, axis=0).squeeze()
            heatmap_png_base64 = _heatmap_to_base64(final_score_map)

    return {
        "anomaly_score_raw": anomaly_score_raw,
        "anomaly_score": float(anomaly_score_avg),
        "heatmap_png_base64": heatmap_png_base64,
    }