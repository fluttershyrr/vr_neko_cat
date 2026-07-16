from __future__ import annotations

import asyncio
import math
from typing import Any


class VrVisionBridge:
    """AI 视觉 → VR 行为桥接：人脸检测→注视、表情→情感、手势→手指、物体→注视、自动环视。"""

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._face_pos: tuple[float, float, float] | None = None
        self._face_expression: str = "neutral"
        self._last_gesture: str = ""
        self._auto_look_enabled = False
        self._auto_look_task: asyncio.Task | None = None
        self._vision_config = {
            "camera_fov_h": 70.0,
            "camera_fov_v": 50.0,
            "tracking_smooth": 0.15,
            "react_to_expression": True,
            "react_to_gesture": True,
            "look_distance": 2.0,
        }

    @property
    def tracking(self):
        return self.plugin.tracking_service

    @property
    def emotion(self):
        return self.plugin.emotion_service

    @property
    def anim(self):
        return self.plugin.animation_service

    def on_face_detected(self, screen_x: float = 0.5, screen_y: float = 0.4,
                         screen_w: float = 0.15, screen_h: float = 0.2,
                         distance_estimate: float = 2.0) -> dict[str, Any]:
        """人脸屏幕坐标 → 世界坐标 → HMD 注视目标，使用相机 FOV 和预设距离转换。"""
        fov_h = math.radians(self._vision_config["camera_fov_h"])
        fov_v = math.radians(self._vision_config["camera_fov_v"])

        angle_h = (screen_x - 0.5) * fov_h
        angle_v = -(screen_y - 0.5) * fov_v

        dist = self._vision_config["look_distance"]
        wx = math.sin(angle_h) * dist
        wy = math.sin(angle_v) * dist + 1.5
        wz = -math.cos(angle_h) * dist

        self._face_pos = (wx, wy, wz)
        self._face_expression = "neutral"
        result = self.tracking.look_at(wx, wy, wz, self._vision_config["tracking_smooth"])
        result["world_pos"] = [wx, wy, wz]
        result["screen_pos"] = [screen_x, screen_y]
        return result

    def on_face_lost(self) -> dict[str, Any]:
        self._face_pos = None
        return {"face_lost": True}

    def on_expression_detected(self, expression: str, confidence: float = 0.0) -> dict[str, Any]:
        """面部表情识别结果 → 映射到 VR 情感并应用到姿态。"""
        emo_map = {
            "happy": "happy", "sad": "sad", "angry": "angry",
            "surprise": "surprised", "fear": "scared",
            "disgust": "angry", "neutral": "neutral",
        }
        vr_emotion = emo_map.get(expression, "neutral")
        intensity = max(0.2, min(1.0, confidence)) if confidence > 0 else 0.6
        self._face_expression = expression
        if self._vision_config["react_to_expression"]:
            self.emotion.apply_emotion(vr_emotion, intensity)
        return {"expression_detected": expression, "vr_emotion": vr_emotion, "intensity": intensity}

    def on_body_landmarks(self, landmarks: dict[str, Any]) -> dict[str, Any]:
        """人体关键点 → 手腕位置映射到 VR 控制器位姿（缩放后偏移到身体前方）。"""
        result: dict[str, Any] = {"mapped": {}}
        pose = self.plugin.pose_service
        for side, wrist_key in [("left", "left_wrist"), ("right", "right_wrist")]:
            if wrist_key in landmarks:
                pos = landmarks[wrist_key]
                dev = f"{side}_controller"
                pose.set_device_position(dev, pos[0] * 0.5, pos[1] * 0.5 + 1.0, pos[2] * 0.4 - 0.5)
                result["mapped"][wrist_key] = pos
        return result

    def on_gesture_detected(self, gesture: str, side: str = "right",
                             confidence: float = 0.0) -> dict[str, Any]:
        """手势识别结果 → 映射到 VR 手指弯曲。"""
        gesture_map = {
            "open": "open", "fist": "fist", "point": "point",
            "peace": "peace", "thumbs_up": "thumbs_up",
            "ok": "point", "rock": "peace",
        }
        vr_gesture = gesture_map.get(gesture, "open")
        if self._vision_config["react_to_gesture"]:
            self.plugin.input_service._do_gesture(side, vr_gesture)
        self._last_gesture = gesture
        return {"gesture_detected": gesture, "side": side, "vr_gesture": vr_gesture}

    def on_object_detected(self, obj_type: str, world_x: float = 0.0,
                           world_y: float = 1.0, world_z: float = -3.0) -> dict[str, Any]:
        """物体检测结果 → HMD 注视目标位置。"""
        self.tracking.look_at(world_x, world_y, world_z, 0.2)
        return {"object": obj_type, "looking_at": [world_x, world_y, world_z]}

    async def _auto_look_loop(self) -> None:
        """15Hz 自动环视循环：无人脸时正弦扫描 ±30°，模拟自然环顾行为。"""
        while self._auto_look_enabled:
            if self._face_pos is None:
                t = asyncio.get_event_loop().time()
                angle = math.sin(t * 0.3) * 30
                self.tracking.look_at_direction(yaw_deg=angle, pitch_deg=0.0, smooth=0.05)
            await asyncio.sleep(1.0 / 15)

    async def start_auto_look(self) -> dict[str, Any]:
        self._auto_look_enabled = True
        if self._auto_look_task is None or self._auto_look_task.done():
            self._auto_look_task = asyncio.get_event_loop().create_task(self._auto_look_loop())
        return {"auto_look_started": True}

    async def stop_auto_look(self) -> dict[str, Any]:
        self._auto_look_enabled = False
        if self._auto_look_task:
            self._auto_look_task.cancel()
            try:
                await self._auto_look_task
            except asyncio.CancelledError:
                pass
            self._auto_look_task = None
        return {"auto_look_stopped": True}

    def set_vision_config(self, **kwargs) -> dict[str, Any]:
        for k, v in kwargs.items():
            if k in self._vision_config:
                self._vision_config[k] = v
        return {"vision_config": self._vision_config}

    def get_vision_state(self) -> dict[str, Any]:
        return {
            "face_detected": self._face_pos is not None,
            "face_position": list(self._face_pos) if self._face_pos else None,
            "expression": self._face_expression,
            "last_gesture": self._last_gesture,
            "auto_look": self._auto_look_enabled,
            "config": self._vision_config,
        }
