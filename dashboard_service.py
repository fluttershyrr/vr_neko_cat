from __future__ import annotations

import asyncio
from typing import Any


class VrDashboardService:
    """仪表板服务：聚合所有子服务的状态 → 构建统一仪表板 + 保存配置。"""

    def __init__(self, plugin: Any):
        self.plugin = plugin

    @property
    def config_service(self):
        return self.plugin.config_service

    @property
    def pose_service(self):
        return self.plugin.pose_service

    @property
    def input_service(self):
        return self.plugin.input_service

    @property
    def dance_service(self):
        return self.plugin.dance_service

    @property
    def emotion_service(self):
        return self.plugin.emotion_service

    @property
    def tracking_service(self):
        return self.plugin.tracking_service

    @property
    def animation_service(self):
        return self.plugin.animation_service

    @property
    def vision_bridge(self):
        return self.plugin.vision_bridge

    @property
    def vrchat_service(self):
        return self.plugin.vrchat_service

    @property
    def driver_service(self):
        return self.plugin.driver_service

    @property
    def screen_capture(self):
        return self.plugin.screen_capture

    async def build_dashboard_state(self) -> dict[str, Any]:
        cfg = self.config_service.get_config()
        return {
            "driver": self.driver_service.get_driver_state(),
            "connection": {
                "host": cfg.get("host", "127.0.0.1"),
                "port": cfg.get("port", 39570),
                "stream_rate_hz": cfg.get("stream_rate_hz", 20),
                "streaming": self.plugin._streaming,
            },
            "devices": self.pose_service.get_all_device_states(),
            "inputs": {
                "left": self.input_service.get_controller_state("left"),
                "right": self.input_service.get_controller_state("right"),
            },
            "dance": self.dance_service.get_state(),
            "emotion": self.emotion_service.get_emotion_state(),
            "tracking": self.tracking_service.get_tracking_state(),
            "animation": self.animation_service.get_animation_state(),
            "vision": self.vision_bridge.get_vision_state(),
            "screen_capture": self.screen_capture.get_state(),
            "vrchat": self.vrchat_service.get_vrchat_state(),
            "settings": {
                "mirror_hands": cfg.get("mirror_hands", False),
                "mirror_feet": cfg.get("mirror_feet", False),
                "manipulation_frame": cfg.get("manipulation_frame", "hmd"),
                "always_on_top": cfg.get("always_on_top", False),
                "ui_mode": cfg.get("ui_mode", "full"),
                "avatar_height": cfg.get("avatar_height", 1.5),
                "fbt_calibrated": cfg.get("fbt_calibrated", False),
                "translation_sensitivity": cfg.get("translation_sensitivity", 0.002),
                "rotation_sensitivity": cfg.get("rotation_sensitivity", 0.08),
                "pitch_limit_degrees": cfg.get("pitch_limit_degrees", 80.0),
                "send_hmd_pose": cfg.get("send_hmd_pose", True),
                "send_controller_poses": cfg.get("send_controller_poses", True),
                "send_tracker_poses": cfg.get("send_tracker_poses", True),
            },
            "dance_config": {
                "height": cfg.get("dance_height", 1.5),
                "speed": cfg.get("dance_speed", 1.0),
                "fps": cfg.get("dance_fps", 60.0),
                "hand_reach": cfg.get("dance_hand_reach", 1.22),
                "loop": cfg.get("dance_loop", True),
                "vmd_path": cfg.get("dance_vmd_path", ""),
            },
        }

    async def build_dashboard_context(self) -> dict[str, Any]:
        return await self.build_dashboard_state()

    async def save_settings(self, **kwargs: Any) -> dict[str, Any]:
        """将 kwargs 中的设置项分类写入配置（简单值/位姿/输入/手指弯曲）并持久化。"""
        cfg = self.config_service.get_config()

        simple_keys = [
            "host", "port", "stream_rate_hz",
            "send_hmd_pose", "send_controller_poses", "send_tracker_poses",
            "mirror_hands", "mirror_feet", "manipulation_frame",
            "always_on_top", "ui_mode", "avatar_height", "fbt_calibrated",
            "translation_sensitivity", "rotation_sensitivity", "pitch_limit_degrees",
            "dance_height", "dance_speed", "dance_fps", "dance_hand_reach",
            "dance_loop", "dance_vmd_path",
            "anyadance_path",
        ]
        for k in simple_keys:
            if k in kwargs and kwargs[k] is not None:
                cfg[k] = kwargs[k]

        pose_devices = ["hmd_pose", "left_controller_pose", "right_controller_pose", "hip_pose", "left_foot_pose", "right_foot_pose"]
        for dev_key in pose_devices:
            if dev_key in kwargs and isinstance(kwargs[dev_key], dict):
                cfg.setdefault(dev_key, {}).update(kwargs[dev_key])

        input_devices = ["left_controller_input", "right_controller_input"]
        for dev_key in input_devices:
            if dev_key in kwargs and isinstance(kwargs[dev_key], dict):
                cfg.setdefault(dev_key, {}).update(kwargs[dev_key])

        finger_keys = ["left_finger_bends", "right_finger_bends"]
        for dev_key in finger_keys:
            if dev_key in kwargs and isinstance(kwargs[dev_key], dict):
                cfg.setdefault(dev_key, {}).update(kwargs[dev_key])

        self.plugin._config = cfg
        await self.config_service.save()
        return {"persisted": True}

    async def open_ui(self) -> dict[str, Any]:
        return {"available": True, "path": f"/plugin/{self.plugin.plugin_id}/ui/"}
