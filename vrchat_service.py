from __future__ import annotations

import asyncio
from typing import Any

# VRChat 8 种标准手势 → 五指弯曲值映射表 (0=伸直, 1=弯曲)
VRC_GESTURES: dict[str, dict[str, float]] = {
    "neutral":  {"thumb": 0.0, "index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
    "fist":     {"thumb": 1.0, "index": 1.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0},
    "hand_open":{"thumb": 0.0, "index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
    "point":    {"thumb": 1.0, "index": 0.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0},
    "peace":    {"thumb": 1.0, "index": 0.0, "middle": 0.0, "ring": 1.0, "pinky": 1.0},
    "rock":     {"thumb": 1.0, "index": 0.0, "middle": 1.0, "ring": 1.0, "pinky": 0.0},
    "gun":      {"thumb": 0.0, "index": 0.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0},
    "thumbs_up":{"thumb": 0.0, "index": 1.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0},
}

# 4 种 VRChat 角色身高预设（米）
VRC_AVATAR_HEIGHTS = {
    "short": 1.2,
    "medium": 1.5,
    "tall": 1.8,
    "tower": 2.0,
}

# FBT 校准后各设备的基准偏移（相对于默认 1.5m 身高），按比例缩放
FBT_OFFSETS = {
    "hmd":              (0.00, 0.95, 0.00),
    "left_controller":  (-0.18, 0.73, -0.36),
    "right_controller": (0.18, 0.73, -0.36),
    "hip":              (0.00, 0.55, -0.03),
    "left_foot":        (-0.06, 0.00, 0.06),
    "right_foot":       (0.06, 0.00, 0.06),
}


class VrChatService:
    """VRChat 专用适配: 手势/移动/FBT 校准/交互辅助"""

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._locomotion_task: asyncio.Task | None = None
        self._locomoting = False
        self._avatar_height = 1.5

    @property
    def _config(self) -> dict[str, Any]:
        return self.plugin._config

    @property
    def input_svc(self):
        return self.plugin.input_service

    @property
    def pose_svc(self):
        return self.plugin.pose_service

    @property
    def udp_svc(self):
        return self.plugin.udp_service

    def apply_vrc_gesture(self, side: str, gesture: str) -> dict[str, Any]:
        bends = VRC_GESTURES.get(gesture, VRC_GESTURES["neutral"])
        self.input_svc.set_finger_bends(side, bends)
        return {"side": side, "gesture": gesture, "bends": bends}

    def apply_vrc_gesture_both(self, gesture: str) -> dict[str, Any]:
        bends = VRC_GESTURES.get(gesture, VRC_GESTURES["neutral"])
        self.input_svc.set_finger_bends("left", bends)
        self.input_svc.set_finger_bends("right", bends)
        return {"gesture": gesture, "bends": bends}

    def walk(self, direction: str = "forward") -> dict[str, Any]:
        """通过左摇杆控制 VRChat 角色移动方向。"""
        speed = {
            "forward": (0.0, 1.0), "backward": (0.0, -1.0),
            "left": (-1.0, 0.0), "right": (1.0, 0.0),
        }
        x, y = speed.get(direction, (0.0, 0.0))
        self.input_svc.set_joystick("left", x, y)
        return {"action": "walk", "direction": direction, "joystick": [x, y]}

    def turn(self, direction: str = "right", speed: float = 0.5) -> dict[str, Any]:
        """通过右摇杆控制 VRChat 角色视角转向。"""
        x = speed if direction == "right" else -speed
        self.input_svc.set_joystick("right", x, 0.0)
        return {"action": "turn", "direction": direction, "speed": speed}

    def stop_locomotion(self) -> dict[str, Any]:
        self.input_svc.set_joystick("left", 0.0, 0.0)
        self.input_svc.set_joystick("right", 0.0, 0.0)
        return {"locomotion": "stopped"}

    async def _loco_loop(self, direction: str, duration: float) -> None:
        """定时移动：行走 duration 秒后自动停止。"""
        self.walk(direction)
        await asyncio.sleep(duration)
        self.stop_locomotion()
        self._locomoting = False

    async def walk_for(self, direction: str = "forward", duration: float = 2.0) -> dict[str, Any]:
        self._locomoting = True
        if self._locomotion_task and not self._locomotion_task.done():
            self._locomotion_task.cancel()
        self._locomotion_task = asyncio.get_event_loop().create_task(
            self._loco_loop(direction, duration))
        return {"walking": direction, "duration_s": duration}

    def pickup(self, side: str = "right") -> dict[str, Any]:
        self.input_svc.set_grip(side, 1.0)
        self.input_svc.set_trigger(side, 1.0)
        return {"action": "pickup", "side": side}

    def drop(self, side: str = "right") -> dict[str, Any]:
        self.input_svc.set_grip(side, 0.0)
        self.input_svc.set_trigger(side, 0.0)
        return {"action": "drop", "side": side}

    def use_action(self, side: str = "right") -> dict[str, Any]:
        self.input_svc.set_button(side, "a_click", True)
        return {"action": "use", "side": side}

    def open_menu(self, side: str = "left") -> dict[str, Any]:
        self.input_svc.set_button(side, "menu_click", True)
        return {"action": "menu", "side": side}

    def jump(self) -> dict[str, Any]:
        self.input_svc.set_button("right", "a_click", True)
        return {"action": "jump"}

    def calibrate_fbt(self, height: str = "medium") -> dict[str, Any]:
        """根据角色身高缩放 FBT 设备偏移量，实现全身追踪校准。"""
        h = VRC_AVATAR_HEIGHTS.get(height, 1.5)
        self._avatar_height = h
        for dev, (rx, ry, rz) in FBT_OFFSETS.items():
            self.pose_svc.set_device_position(dev, rx * h / 1.5, ry * h / 1.5, rz * h / 1.5)
        self._config["avatar_height"] = h
        return {"action": "fbt_calibrated", "height": h}

    def set_avatar_height(self, height: float) -> dict[str, Any]:
        h = max(0.5, min(2.5, height))
        self._avatar_height = h
        self.calibrate_fbt()
        return {"avatar_height": h}

    async def sit(self) -> dict[str, Any]:
        """坐姿预设：降低 HMD/髋部，手臂和脚部前移，然后重捕获基线。"""
        self.pose_svc.set_device_position("hmd", 0.0, 1.05, 0.0)
        self.pose_svc.set_device_position("hip", 0.0, 0.55, 0.0)
        self.pose_svc.set_device_position("left_controller", -0.28, 0.65, -0.15)
        self.pose_svc.set_device_position("right_controller", 0.28, 0.65, -0.15)
        self.pose_svc.set_device_position("left_foot", -0.12, 0.0, 0.3)
        self.pose_svc.set_device_position("right_foot", 0.12, 0.0, 0.3)
        self.plugin.emotion_service.capture_baseline()
        return {"preset": "sit"}

    async def crouch(self) -> dict[str, Any]:
        """蹲姿预设：大幅降低 HMD 和髋部高度，0.3 秒后重捕获基线。"""
        self.pose_svc.set_device_position("hmd", 0.0, 0.9, 0.0)
        self.pose_svc.set_device_position("hip", 0.0, 0.32, 0.0)
        await asyncio.sleep(0.3)
        self.plugin.emotion_service.capture_baseline()
        return {"preset": "crouch"}

    async def handshake(self, side: str = "right") -> dict[str, Any]:
        """握手动画：伸出一只手到前方，张开手掌，1 秒后握拳。"""
        s = 1.0 if side == "right" else -1.0
        self.pose_svc.set_device_position(f"{side}_controller", 0.35 * s, 1.25, -0.7)
        self.input_svc.open_hand(side)
        await asyncio.sleep(1.0)
        self.input_svc.make_fist(side, True)
        return {"preset": "handshake", "side": side}

    def set_expression_param(self, param: str, value: float) -> dict[str, Any]:
        known = {
            "gesture_left": lambda v: self.input_svc.set_finger_bends("left",
                {k: v for k in ("thumb", "index", "middle", "ring", "pinky")}),
            "gesture_right": lambda v: self.input_svc.set_finger_bends("right",
                {k: v for k in ("thumb", "index", "middle", "ring", "pinky")}),
        }
        if param in known:
            known[param](max(0.0, min(1.0, value)))
        return {"param": param, "value": value}

    def get_available_gestures(self) -> dict[str, Any]:
        return {
            "gestures": list(VRC_GESTURES.keys()),
            "gesture_details": {
                name: {k: round(v, 1) for k, v in bends.items()}
                for name, bends in VRC_GESTURES.items()
            },
            "avatar_heights": VRC_AVATAR_HEIGHTS,
        }

    def get_vrchat_state(self) -> dict[str, Any]:
        return {
            "avatar_height": self._avatar_height,
            "locomoting": self._locomoting,
            "available_gestures": list(VRC_GESTURES.keys()),
        }
