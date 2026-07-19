from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


class VrConfigService:
    """JSON 配置持久化：默认值 → 文件加载(深度合并) → 保存 → 更新。"""

    DEFAULTS: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": 39570,
        "stream_rate_hz": 20,
        "max_packet_bytes": 8192,
        "max_abs_position": 10.0,
        "max_y": 2.0,
        "send_hmd_pose": True,
        "send_controller_poses": True,
        "send_tracker_poses": True,
        "reset_hmd_y": 1.5,
        "translation_sensitivity": 0.002,
        "rotation_sensitivity": 0.08,
        "pitch_limit_degrees": 80.0,
        "hmd_pose": {"position_x": 0.0, "position_y": 1.5, "position_z": 0.0, "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0, "rotation_w": 1.0},
        "left_controller_pose": {"position_x": -0.26, "position_y": 1.1, "position_z": -0.54, "rotation_x": 0.77, "rotation_y": 0.1, "rotation_z": -0.16, "rotation_w": 0.61},
        "right_controller_pose": {"position_x": 0.27, "position_y": 1.57, "position_z": -0.54, "rotation_x": 0.77, "rotation_y": -0.1, "rotation_z": 0.16, "rotation_w": 0.61},
        "hip_pose": {"position_x": 0.0, "position_y": 1.07, "position_z": -0.05, "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0, "rotation_w": 1.0},
        "left_foot_pose": {"position_x": -0.09, "position_y": 0.26, "position_z": 0.1, "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0, "rotation_w": 1.0},
        "right_foot_pose": {"position_x": 0.09, "position_y": 0.26, "position_z": 0.1, "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0, "rotation_w": 1.0},
        "left_controller_input": {"trigger_click": False, "trigger_value": 0.0, "menu_click": False, "system_click": False, "a_click": False, "b_click": False, "grip_click": False, "grip_value": 0.0, "joystick_x": 0.0, "joystick_y": 0.0, "trackpad_x": 0.0, "trackpad_y": 0.0},
        "right_controller_input": {"trigger_click": False, "trigger_value": 0.0, "menu_click": False, "system_click": False, "a_click": False, "b_click": False, "grip_click": False, "grip_value": 0.0, "joystick_x": 0.0, "joystick_y": 0.0, "trackpad_x": 0.0, "trackpad_y": 0.0},
        "left_finger_bends": {"thumb": 0.0, "index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
        "right_finger_bends": {"thumb": 0.0, "index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
        "dance_height": 1.5, "dance_speed": 1.0, "dance_fps": 60.0, "dance_hand_reach": 1.22, "dance_loop": True, "dance_vmd_path": "",
        "mirror_hands": False, "mirror_feet": False,
        "manipulation_frame": "hmd",
        "always_on_top": False, "ui_mode": "full",
        "current_emotion": "neutral", "emotion_intensity": 1.0,
        "tracking_enabled": False, "track_lerp_factor": 0.12,
        "idle_enabled": False, "sway_amount": 0.01,
        "auto_look_enabled": False, "camera_fov_h": 70.0, "camera_fov_v": 50.0, "tracking_smooth": 0.15,
        "look_distance": 2.0, "react_to_expression": True, "react_to_gesture": True,
        "avatar_height": 1.5, "fbt_calibrated": False,
        "capture_monitor_index": 0, "capture_quality": 75,
        "capture_scale": 1.0, "capture_format": "jpeg",
        "anyadance_path": "",
    }

    def __init__(self, data_dir: str):
        self._file = Path(data_dir) / "config.json"
        self._config: dict[str, Any] = {}

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """递归深度合并两个字典，override 中的嵌套字典会与 base 合并而非完全替换。"""
        result = copy.deepcopy(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def default_config(self) -> dict[str, Any]:
        return copy.deepcopy(self.DEFAULTS)

    async def load(self) -> dict[str, Any]:
        try:
            if self._file.exists():
                raw = self._file.read_text(encoding="utf-8")
                saved = json.loads(raw)
                if isinstance(saved, dict):
                    self._config = self._deep_merge(self.DEFAULTS, saved)
                    return self._config
        except Exception:
            pass
        self._config = copy.deepcopy(self.DEFAULTS)
        return self._config

    async def save(self) -> bool:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(json.dumps(self._config, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except OSError:
            return False

    async def exists(self) -> bool:
        return self._file.exists()

    def get_config(self) -> dict[str, Any]:
        return self._config

    def update(self, updates: dict[str, Any]) -> None:
        self._config = self._deep_merge(self._config, updates)
