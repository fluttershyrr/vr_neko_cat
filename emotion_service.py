from __future__ import annotations

import math
from typing import Any

# 12 种情感到 VR 设备姿态偏移的预设表。
# 每个情感定义 HMD/双手的 Y 偏移(抬头低头)、X 偏移(手臂开合)、Yaw 旋转(偏头) 和默认手势。
EMOTION_PRESETS: dict[str, dict[str, Any]] = {
    "happy": {
        "hmd": {"py": 0.05, "ry": 0.15},
        "left_controller": {"py": 0.1, "px": -0.05, "pz": 0.05},
        "right_controller": {"py": 0.12, "px": 0.05, "pz": 0.05},
        "gesture": "open",
    },
    "sad": {
        "hmd": {"py": -0.1, "ry": -0.12},
        "left_controller": {"py": -0.15, "px": 0.03},
        "right_controller": {"py": -0.15, "px": -0.03},
        "gesture": "open",
    },
    "angry": {
        "hmd": {"py": 0.02, "ry": 0.08},
        "left_controller": {"px": -0.1, "py": 0.05},
        "right_controller": {"px": 0.1, "py": 0.08},
        "gesture": "fist",
    },
    "surprised": {
        "hmd": {"py": 0.08, "ry": 0.05},
        "left_controller": {"py": 0.2, "px": -0.15, "pz": 0.1},
        "right_controller": {"py": 0.25, "px": 0.15, "pz": 0.1},
        "gesture": "open",
    },
    "scared": {
        "hmd": {"py": 0.0, "ry": -0.1, "pz": 0.1},
        "left_controller": {"py": 0.02, "px": 0.05, "pz": 0.05},
        "right_controller": {"py": 0.02, "px": -0.05, "pz": 0.05},
        "gesture": "open",
    },
    "excited": {
        "hmd": {"py": 0.1, "ry": 0.2},
        "left_controller": {"py": 0.25, "px": -0.2, "pz": 0.1},
        "right_controller": {"py": 0.3, "px": 0.2, "pz": 0.1},
        "gesture": "open",
    },
    "shy": {
        "hmd": {"py": -0.05, "ry": -0.15, "rz": 0.05},
        "left_controller": {"py": 0.0, "px": 0.05, "pz": 0.02},
        "right_controller": {"py": 0.0, "px": -0.05, "pz": 0.02},
        "gesture": "fist",
    },
    "confident": {
        "hmd": {"py": 0.06, "ry": 0.1},
        "left_controller": {"px": -0.08, "py": -0.02, "pz": 0.02},
        "right_controller": {"px": 0.08, "py": 0.0, "pz": 0.05},
        "gesture": "thumbs_up",
    },
    "relaxed": {
        "hmd": {"py": 0.0, "ry": 0.02},
        "left_controller": {"py": -0.05, "px": -0.02},
        "right_controller": {"py": -0.05, "px": 0.02},
        "gesture": "open",
    },
    "curious": {
        "hmd": {"py": 0.03, "ry": 0.18, "pz": 0.05},
        "left_controller": {"px": -0.05, "py": 0.02, "pz": 0.05},
        "right_controller": {"px": 0.05, "py": 0.02, "pz": 0.05},
        "gesture": "point",
    },
    "tired": {
        "hmd": {"py": -0.08, "ry": -0.05},
        "left_controller": {"py": -0.2, "px": 0.02},
        "right_controller": {"py": -0.2, "px": -0.02},
        "gesture": "open",
    },
    "neutral": {
        "hmd": {"py": 0.0, "ry": 0.0},
        "left_controller": {"py": 0.0, "px": 0.0},
        "right_controller": {"py": 0.0, "px": 0.0},
        "gesture": "open",
    },
}

DEVICE_KEYS = ["hmd", "left_controller", "right_controller", "hip", "left_foot", "right_foot"]


class VrEmotionService:
    """情感→姿态映射：12 种情感预设 → 基于基线位姿的线性插值 → 应用到 HMD/双手 + 手势。"""

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._current_emotion = "neutral"
        self._emotion_intensity = 0.0
        self._baseline_pose: dict[str, dict[str, float]] = {}

    @property
    def _config(self) -> dict[str, Any]:
        return self.plugin._config

    def _lerp(self, a: float, b: float, t: float) -> float:
        return a + (b - a) * max(0.0, min(1.0, t))

    def capture_baseline(self) -> None:
        """捕获当前所有设备的位姿作为情感偏移的基准值。"""
        for dev in DEVICE_KEYS:
            cfg = self._config.get(f"{dev}_pose", {})
            self._baseline_pose[dev] = {
                "px": cfg.get("position_x", 0.0),
                "py": cfg.get("position_y", 0.0),
                "pz": cfg.get("position_z", 0.0),
                "rx": cfg.get("rotation_x", 0.0),
                "ry": cfg.get("rotation_y", 0.0),
                "rz": cfg.get("rotation_z", 0.0),
                "rw": cfg.get("rotation_w", 1.0),
            }

    def apply_emotion(self, emotion: str, intensity: float = 1.0) -> dict[str, Any]:
        """将情感预设叠加到基线位姿，强度 0~1 控制偏移幅度，同时设置双手手势。"""
        preset = EMOTION_PRESETS.get(emotion, EMOTION_PRESETS["neutral"])
        if not self._baseline_pose:
            self.capture_baseline()

        i = max(0.0, min(1.0, intensity))
        result: dict[str, Any] = {}

        for dev in DEVICE_KEYS:
            base = self._baseline_pose.get(dev, {})
            mod = preset.get(dev, {})
            if dev in ("hip", "left_foot", "right_foot"):
                continue
            key = f"{dev}_pose"
            cfg = self._config.setdefault(key, {})
            cfg["position_x"] = self._lerp(base.get("px", 0.0), base.get("px", 0.0) + mod.get("px", 0.0), i)
            cfg["position_y"] = self._lerp(base.get("py", 0.0), base.get("py", 0.0) + mod.get("py", 0.0), i)
            cfg["position_z"] = self._lerp(base.get("pz", 0.0), base.get("pz", 0.0) + mod.get("pz", 0.0), i)
            if dev == "hmd":
                half = mod.get("ry", 0.0) * i * 0.5
                cfg["rotation_y"] = math.sin(half)
                cfg["rotation_w"] = math.cos(half)

            result[dev] = {
                "position": [cfg["position_x"], cfg["position_y"], cfg["position_z"]],
                "rotation": [cfg.get("rotation_x", 0.0), cfg.get("rotation_y", 0.0), cfg.get("rotation_z", 0.0), cfg.get("rotation_w", 1.0)],
            }

        gesture = preset.get("gesture", "open")
        self.plugin.input_service._do_gesture("left", gesture)
        self.plugin.input_service._do_gesture("right", gesture)
        result["gesture"] = gesture

        self._current_emotion = emotion
        self._emotion_intensity = i
        return result


    def blend_emotions(self, emotion_a: str, emotion_b: str, ratio: float = 0.5) -> dict[str, Any]:
        """按 ratio 混合两种情感预设的偏移量，ratio=0 为纯 A，ratio=1 为纯 B。"""
        t = max(0.0, min(1.0, ratio))
        pa = EMOTION_PRESETS.get(emotion_a, EMOTION_PRESETS["neutral"])
        pb = EMOTION_PRESETS.get(emotion_b, EMOTION_PRESETS["neutral"])
        if not self._baseline_pose:
            self.capture_baseline()

        result: dict[str, Any] = {}
        for dev in DEVICE_KEYS:
            if dev in ("hip", "left_foot", "right_foot"):
                continue
            base = self._baseline_pose.get(dev, {})
            ma = pa.get(dev, {})
            mb = pb.get(dev, {})
            key = f"{dev}_pose"
            cfg = self._config.setdefault(key, {})
            for axis, field in [("px", "position_x"), ("py", "position_y"), ("pz", "position_z")]:
                da = ma.get(axis, 0.0); db = mb.get(axis, 0.0)
                cfg[field] = self._lerp(base.get(axis, 0.0) + da, base.get(axis, 0.0) + db, t)
            if dev == "hmd":
                half_y = (self._lerp(ma.get("ry", 0.0), mb.get("ry", 0.0), t)) * 0.5
                cfg["rotation_y"] = math.sin(half_y)
                cfg["rotation_w"] = math.cos(half_y)
            result[dev] = {
                "position": [cfg["position_x"], cfg["position_y"], cfg["position_z"]],
                "rotation": [cfg.get("rotation_x", 0.0), cfg.get("rotation_y", 0.0), cfg.get("rotation_z", 0.0), cfg.get("rotation_w", 1.0)],
            }
        gesture = pa.get("gesture", "open") if t < 0.5 else pb.get("gesture", "open")
        self.plugin.input_service._do_gesture("left", gesture)
        self.plugin.input_service._do_gesture("right", gesture)
        result["gesture"] = gesture
        return result

    def get_emotion_state(self) -> dict[str, Any]:
        return {
            "current_emotion": self._current_emotion,
            "intensity": self._emotion_intensity,
            "available_emotions": list(EMOTION_PRESETS.keys()),
        }
