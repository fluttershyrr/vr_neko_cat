from __future__ import annotations

import math
from typing import Any


class VrPoseService:
    """管理 6 个 VR 追踪设备的 3D 位姿（位置 + 四元数旋转），支持预设/手动设置/镜像/Yaw 旋转。"""

    PRESETS = {
        "standing": {
            "hmd": (0.0, 1.5, 0.0, 0, 0, 0, 1),
            "left_controller": (-0.26, 1.1, -0.54, 0.77, 0.1, -0.16, 0.61),
            "right_controller": (0.27, 1.57, -0.54, 0.77, -0.1, 0.16, 0.61),
            "hip": (0.0, 0.85, 0.0, 0, 0, 0, 1),
            "left_foot": (-0.12, -0.01, 0.0, 0, 0, 0, 1),
            "right_foot": (0.12, -0.01, 0.0, 0, 0, 0, 1),
        },
        "t_pose": {
            "hmd": (0.0, 1.5, 0.0, 0, 0, 0, 1),
            "left_controller": (-0.6, 1.5, 0.0, 0, 0, 0, 1),
            "right_controller": (0.6, 1.5, 0.0, 0, 0, 0, 1),
            "hip": (0.0, 0.85, 0.0, 0, 0, 0, 1),
            "left_foot": (-0.12, -0.01, 0.0, 0, 0, 0, 1),
            "right_foot": (0.12, -0.01, 0.0, 0, 0, 0, 1),
        },
        "menu": {
            "hmd": (0.0, 1.5, 0.0, 0, 0, 0, 1),
            "left_controller": (-0.26, 1.1, -0.54, 0.77, 0.1, -0.16, 0.61),
            "right_controller": (0.27, 1.57, -0.54, 0.77, -0.1, 0.16, 0.61),
            "hip": (0.0, 1.07, -0.05, 0, 0, 0, 1),
            "left_foot": (-0.09, 0.26, 0.1, 0, 0, 0, 1),
            "right_foot": (0.09, 0.26, 0.1, 0, 0, 0, 1),
        },
    }

    DEVICE_KEYS = ["hmd_pose", "left_controller_pose", "right_controller_pose", "hip_pose", "left_foot_pose", "right_foot_pose"]
    PRESET_KEYS = ["hmd", "left_controller", "right_controller", "hip", "left_foot", "right_foot"]

    def __init__(self, plugin: Any):
        self.plugin = plugin

    @property
    def _config(self) -> dict[str, Any]:
        return self.plugin._config

    def apply_preset(self, preset_name: str) -> None:
        preset = self.PRESETS.get(preset_name)
        if not preset:
            return
        for dev_key, preset_key in zip(self.DEVICE_KEYS, self.PRESET_KEYS):
            values = preset.get(preset_key)
            if values is None:
                continue
            px, py, pz, rx, ry, rz, rw = values
            if dev_key not in self._config:
                self._config[dev_key] = {}
            self._config[dev_key].update({
                "position_x": px, "position_y": py, "position_z": pz,
                "rotation_x": rx, "rotation_y": ry, "rotation_z": rz, "rotation_w": rw,
            })

    def set_device_position(self, device: str, x: float, y: float, z: float) -> None:
        key = f"{device}_pose"
        if key not in self._config:
            self._config[key] = {}
        self._config[key].update({"position_x": float(x), "position_y": float(y), "position_z": float(z)})

    def set_device_rotation(self, device: str, rx: float, ry: float, rz: float, rw: float = 1.0) -> None:
        key = f"{device}_pose"
        if key not in self._config:
            self._config[key] = {}
        self._config[key].update({"rotation_x": float(rx), "rotation_y": float(ry), "rotation_z": float(rz), "rotation_w": float(rw)})

    def move_relative(self, device: str, dx: float, dy: float, dz: float) -> None:
        key = f"{device}_pose"
        cfg = self._config.setdefault(key, {})
        cfg["position_x"] = cfg.get("position_x", 0.0) + float(dx)
        cfg["position_y"] = cfg.get("position_y", 0.0) + float(dy)
        cfg["position_z"] = cfg.get("position_z", 0.0) + float(dz)

    def rotate_yaw(self, device: str, degrees: float) -> None:
        key = f"{device}_pose"
        cfg = self._config.setdefault(key, {})
        rad = math.radians(float(degrees))
        half = rad * 0.5
        cfg["rotation_x"] = 0.0
        cfg["rotation_y"] = math.sin(half)
        cfg["rotation_z"] = 0.0
        cfg["rotation_w"] = math.cos(half)

    def mirror_hands(self) -> None:
        left = self._config.setdefault("left_controller_pose", {})
        right = self._config.setdefault("right_controller_pose", {})
        right["position_x"] = -left.get("position_x", -0.26)
        right["position_y"] = left.get("position_y", 1.1)
        right["position_z"] = left.get("position_z", -0.54)
        for k in ("rotation_x", "rotation_y", "rotation_z", "rotation_w"):
            right[k] = left.get(k, 0.0)

    def mirror_feet(self) -> None:
        left = self._config.setdefault("left_foot_pose", {})
        right = self._config.setdefault("right_foot_pose", {})
        right["position_x"] = -left.get("position_x", -0.09)
        right["position_y"] = left.get("position_y", 0.26)
        right["position_z"] = left.get("position_z", 0.1)
        for k in ("rotation_x", "rotation_y", "rotation_z", "rotation_w"):
            right[k] = left.get(k, 0.0)

    def get_all_device_states(self) -> dict[str, Any]:
        result = {}
        for dev in ["hmd", "left_controller", "right_controller", "hip", "left_foot", "right_foot"]:
            cfg = self._config.get(f"{dev}_pose", {})
            result[dev] = {
                "position": [cfg.get("position_x", 0.0), cfg.get("position_y", 0.0), cfg.get("position_z", 0.0)],
                "rotation": [cfg.get("rotation_x", 0.0), cfg.get("rotation_y", 0.0), cfg.get("rotation_z", 0.0), cfg.get("rotation_w", 1.0)],
            }
        return result
