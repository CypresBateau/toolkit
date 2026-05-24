"""
model_singleton.py — 启动时加载一次 MVFA-AD 模型，全局复用。

对标 MAVL 的 model_singleton.py：
1. 通过 sys.path.insert 复用原始仓库代码；
2. /load 时加载模型；
3. /unload 时释放 GPU；
4. 不修改 MVFA-AD 原始 test_zero.py/test_few.py。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import torch


# ── 路径注入：让 Python 能 import MVFA-AD 原始模块 ─────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]  # .../MVFA-AD
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from CLIP.clip import create_model  # noqa: E402
from CLIP.adapter import CLIP_Inplanted  # noqa: E402
from utils import encode_text_with_prompt_ensemble  # noqa: E402
from prompt import REAL_NAME  # noqa: E402


# 与 test_zero.py 中 CLASS_INDEX 完全一致
CLASS_INDEX: dict[str, int] = {
    "Brain": 3,
    "Liver": 2,
    "Retina_RESC": 1,
    "Retina_OCT2017": -1,
    "Chest": -2,
    "Histopathology": -3,
}

CLASS_INDEX_INV: dict[int, str] = {
    3: "Brain",
    2: "Liver",
    1: "Retina_RESC",
    -1: "Retina_OCT2017",
    -2: "Chest",
    -3: "Histopathology",
}

VALID_OBJECTS: list[str] = list(CLASS_INDEX.keys())

    
def _parse_features(value: str) -> list[int]:
    return [int(x.strip()) for x in value.split(",") if x.strip()]


class ModelSingleton:
    """持有加载后的 MVFA-AD 模型及文本特征，进程内单例。"""

    _instance: "ModelSingleton | None" = None

    def __init__(self) -> None:
        self.clip_model: Any = None
        self.model: Any = None
        self.device: torch.device | None = None

        self.model_name: str = ""
        self.pretrain: str = ""
        self.img_size: int = 240
        self.features_list: list[int] = [6, 12, 18, 24]

        self.ckpt_dir: Path | None = None
        self.default_object: str = "Brain"
        self.active_object: str = ""
        self.checkpoint_name: str = ""
        self.loaded: bool = False

        # 缓存不同 object 的 text_features
        self.text_features_cache: dict[str, torch.Tensor] = {}

    @classmethod
    def get(cls) -> "ModelSingleton":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self) -> None:
        """读取环境变量，初始化 CLIP + MVFA adapter。由 Gateway 调用 /load。"""
        if self.loaded:
            return

        self.model_name = os.environ.get("MVFA_MODEL_NAME", "ViT-L-14-336")
        self.pretrain = os.environ.get("MVFA_PRETRAIN", "openai")
        self.img_size = int(os.environ.get("MVFA_IMG_SIZE", "240"))
        self.features_list = _parse_features(os.environ.get("MVFA_FEATURES", "6,12,18,24"))
        self.ckpt_dir = Path(os.environ.get("MVFA_CKPT_DIR", "/workspace/MVFA-AD/ckpt/zero-shot"))
        self.default_object = os.environ.get("MVFA_DEFAULT_OBJECT", "Brain")

        device_str = os.environ.get("MVFA_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
        self.device = torch.device(device_str)

        if self.default_object not in VALID_OBJECTS:
            raise ValueError(f"Invalid MVFA_DEFAULT_OBJECT={self.default_object}. Valid: {VALID_OBJECTS}")

        print(f"[ModelSingleton] Loading CLIP backbone: {self.model_name}")
        self.clip_model = create_model(
            model_name=self.model_name,
            img_size=self.img_size,
            device=self.device,
            pretrained=self.pretrain,
            require_pretrained=True,
        )
        self.clip_model.eval()

        print("[ModelSingleton] Building CLIP_Inplanted model")
        self.model = CLIP_Inplanted(
            clip_model=self.clip_model,
            features=self.features_list,
        ).to(self.device)
        self.model.eval()

        self.loaded = True

        # 默认先加载一个 object 的 adapter，后续 predict 可以动态切换
        self.set_object(self.default_object)

        print(
            f"[ModelSingleton] Model loaded successfully on {self.device}; "
            f"default_object={self.default_object}; checkpoint={self.checkpoint_name}"
        )

    def set_object(self, obj: str) -> None:
        if not self.loaded:
            raise RuntimeError("Model is not loaded. Call /load first.")

        if obj not in VALID_OBJECTS:
            raise ValueError(f"Invalid obj={obj}. Valid: {VALID_OBJECTS}")

        if self.active_object == obj:
            return

        assert self.ckpt_dir is not None
        ckpt_path = self.ckpt_dir / f"{obj}.pth"

        if not ckpt_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}")

        checkpoint = torch.load(str(ckpt_path), map_location="cpu")

        self.model.seg_adapters.load_state_dict(checkpoint["seg_adapters"])
        self.model.det_adapters.load_state_dict(checkpoint["det_adapters"])
        self.model.to(self.device)
        self.model.eval()

        self.active_object = obj
        self.checkpoint_name = ckpt_path.name

    def get_text_features(self, obj: str) -> torch.Tensor:
        """获取并缓存当前 object 的 prompt text features。"""
        if obj in self.text_features_cache:
            return self.text_features_cache[obj]

        if obj not in VALID_OBJECTS:
            raise ValueError(f"Invalid obj={obj}. Valid: {VALID_OBJECTS}")

        print(f"[ModelSingleton] Encoding text prompt ensemble for: {obj}")

        with torch.no_grad():
            text_features = encode_text_with_prompt_ensemble(
                self.clip_model,
                REAL_NAME[obj],
                self.device,
            )

        self.text_features_cache[obj] = text_features
        return text_features

    def unload(self) -> None:
        """释放 GPU 显存，由 Gateway LRU 调度器驱逐时调用。"""
        if not self.loaded:
            return

        del self.model
        del self.clip_model

        self.model = None
        self.clip_model = None
        self.text_features_cache.clear()

        if self.device and self.device.type == "cuda":
            torch.cuda.empty_cache()

        self.loaded = False
        self.active_object = ""
        self.checkpoint_name = ""

        print("[ModelSingleton] Model unloaded, GPU memory released.")