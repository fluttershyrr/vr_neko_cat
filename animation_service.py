from __future__ import annotations

import asyncio
import math
import random
from typing import Any


class VrAnimationService:
    """预设动画动作：点头/摇头/歪头/挥手/鞠躬 + 待机循环(呼吸+微晃) + 音频律动响应。"""

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._animating = False
        self._anim_task: asyncio.Task | None = None
        self._idle_task: asyncio.Task | None = None
        self._idle_enabled = False
        self._sway_amount = 0.01
        self._breath_phase = 0.0

    @property
    def _config(self) -> dict[str, Any]:
        return self.plugin._config

    def _get_hmd(self) -> dict[str, Any]:
        return self._config.setdefault("hmd_pose", {})

    def _get_hand(self, side: str) -> dict[str, Any]:
        return self._config.setdefault(f"{side}_controller_pose", {})

    async def nod_head(self, count: int = 1, speed: float = 1.0) -> dict[str, Any]:
        """通过 HMD rotation_x 正弦变化实现点头动画。"""
        hmd = self._get_hmd()
        orig_rx, orig_ry, orig_rz, orig_rw = (
            hmd.get("rotation_x", 0.0), hmd.get("rotation_y", 0.0),
            hmd.get("rotation_z", 0.0), hmd.get("rotation_w", 1.0),
        )
        dur = 0.2 / max(0.1, speed)
        for _ in range(count):
            half = math.radians(15)
            hmd["rotation_x"] = math.sin(-half)
            hmd["rotation_w"] = math.cos(half)
            await asyncio.sleep(dur)
            hmd["rotation_x"] = math.sin(half)
            hmd["rotation_w"] = math.cos(half)
            await asyncio.sleep(dur)
        hmd["rotation_x"] = orig_rx
        hmd["rotation_y"] = orig_ry
        hmd["rotation_z"] = orig_rz
        hmd["rotation_w"] = orig_rw
        return {"action": "nod", "count": count}

    async def shake_head(self, count: int = 1, speed: float = 1.0) -> dict[str, Any]:
        """通过 HMD rotation_y 正弦变化实现摇头动画。"""
        hmd = self._get_hmd()
        orig_rx, orig_ry, orig_rz, orig_rw = (
            hmd.get("rotation_x", 0.0), hmd.get("rotation_y", 0.0),
            hmd.get("rotation_z", 0.0), hmd.get("rotation_w", 1.0),
        )
        dur = 0.15 / max(0.1, speed)
        for _ in range(count):
            half = math.radians(20)
            hmd["rotation_y"] = math.sin(-half)
            hmd["rotation_w"] = math.cos(half)
            await asyncio.sleep(dur)
            hmd["rotation_y"] = math.sin(half)
            hmd["rotation_w"] = math.cos(half)
            await asyncio.sleep(dur)
        hmd["rotation_y"] = orig_ry
        hmd["rotation_x"] = orig_rx
        hmd["rotation_z"] = orig_rz
        hmd["rotation_w"] = orig_rw
        return {"action": "shake", "count": count}

    async def tilt_head(self, direction: str = "left", amount: float = 15.0) -> dict[str, Any]:
        """通过 HMD rotation_z 实现歪头动画，1.5 秒后恢复。"""
        hmd = self._get_hmd()
        half = math.radians(amount) * (0.5 if direction == "left" else -0.5)
        hmd["rotation_x"] = 0.0
        hmd["rotation_z"] = math.sin(half)
        hmd["rotation_w"] = math.cos(half)
        await asyncio.sleep(1.5)
        hmd["rotation_z"] = 0.0
        hmd["rotation_w"] = 1.0
        return {"action": "tilt", "direction": direction}

    async def wave_hand(self, side: str = "right", style: str = "hello") -> dict[str, Any]:
        """通过控制器 rotation_z 摆动实现挥手动画，支持 hello/bye/excited 三种风格。"""
        hand = self._get_hand(side)
        orig_rx, orig_ry, orig_rz, orig_rw = (
            hand.get("rotation_x", 0.0), hand.get("rotation_y", 0.0),
            hand.get("rotation_z", 0.0), hand.get("rotation_w", 1.0),
        )
        counts = {"hello": 4, "bye": 5, "excited": 8}
        speed_map = {"hello": 0.12, "bye": 0.15, "excited": 0.07}
        n = counts.get(style, 4)
        dur = speed_map.get(style, 0.12)
        handedness = 1.0 if side == "right" else -1.0
        for i in range(n):
            angle = handedness * math.radians(35 if i % 2 == 0 else -35)
            hand["rotation_z"] = math.sin(angle * 0.5)
            hand["rotation_w"] = math.cos(angle * 0.5)
            hand["rotation_x"] = 0.7
            await asyncio.sleep(dur)
        hand["rotation_x"] = orig_rx
        hand["rotation_y"] = orig_ry
        hand["rotation_z"] = orig_rz
        hand["rotation_w"] = orig_rw
        return {"action": "wave", "side": side, "style": style}

    async def bow(self, depth: float = 30.0) -> dict[str, Any]:
        """HMD 前倾 + 髋部后移实现鞠躬动画，停留 0.8 秒后恢复。"""
        hmd = self._get_hmd()
        hip = self._config.setdefault("hip_pose", {})
        orig_hmd_y, orig_hmd_z = hmd.get("position_y", 1.5), hmd.get("position_z", 0.0)
        orig_hip_z = hip.get("position_z", -0.05)
        dur = 0.4
        half = math.radians(depth)
        hmd["rotation_x"] = math.sin(-half * 0.5)
        hmd["rotation_w"] = math.cos(half * 0.5)
        hmd["position_y"] = orig_hmd_y - 0.15
        hmd["position_z"] = orig_hmd_z + 0.1
        hip["position_z"] = orig_hip_z + 0.08
        await asyncio.sleep(dur * 2)
        await asyncio.sleep(0.8)
        hmd["rotation_x"] = 0.0
        hmd["rotation_w"] = 1.0
        hmd["position_y"] = orig_hmd_y
        hmd["position_z"] = orig_hmd_z
        hip["position_z"] = orig_hip_z
        return {"action": "bow"}


    async def _idle_loop(self) -> None:
        """30Hz 待机循环：正弦呼吸起伏(HMD Y) + 身体微晃(髋部 X + Z 旋转)。"""
        while self._idle_enabled:
            t = asyncio.get_event_loop().time()
            self._breath_phase = (self._breath_phase + 0.02) % (math.pi * 2)
            breath_offset = math.sin(self._breath_phase) * 0.008
            hmd = self._get_hmd()
            hmd["position_y"] = hmd.get("position_y", 1.5) + breath_offset

            sway = math.sin(t * 0.7) * self._sway_amount
            hip = self._config.setdefault("hip_pose", {})
            hip["position_x"] = sway
            hip["rotation_z"] = math.sin(sway * 2) * 0.02
            await asyncio.sleep(1.0 / 30)

    async def start_idle(self) -> dict[str, Any]:
        self._idle_enabled = True
        self._breath_phase = 0.0
        if self._idle_task is None or self._idle_task.done():
            self._idle_task = asyncio.get_event_loop().create_task(self._idle_loop())
        return {"idle_started": True}

    async def stop_idle(self) -> dict[str, Any]:
        self._idle_enabled = False
        if self._idle_task:
            self._idle_task.cancel()
            try:
                await self._idle_task
            except asyncio.CancelledError:
                pass
            self._idle_task = None
        return {"idle_stopped": True}

    async def react_to_audio(self, level: float, freq_band: str = "full") -> dict[str, Any]:
        """音频律动 → HMD 和双手 Y 轴微动 + HMD 旋转，level 越大动作幅度越大。"""
        l = max(0.0, min(1.0, level))
        hmd = self._get_hmd()
        hmd["position_y"] = 1.5 + l * 0.03
        if l > 0.4:
            half = math.sin(l * 0.5) * 0.15
            hmd["rotation_y"] = math.sin(half)
            hmd["rotation_w"] = math.cos(half)
        for s in ("left", "right"):
            hand = self._get_hand(s)
            hand["position_y"] = hand.get("position_y", 1.1) + l * 0.08
        return {"audio_level": l, "freq_band": freq_band}

    def get_animation_state(self) -> dict[str, Any]:
        return {
            "idle_enabled": self._idle_enabled,
            "sway_amount": self._sway_amount,
            "breath_phase": self._breath_phase,
        }

    async def stop_all(self) -> None:
        await self.stop_idle()
