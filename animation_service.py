from __future__ import annotations

import asyncio
import math
from typing import Any


class VrAnimationService:
    """预设动画动作：点头/摇头/歪头/挥手/鞠躬 + 待机循环(呼吸+微晃) + 音频律动响应。

    每个动画在关键帧主动调用 UDP 发送，不再依赖全局 60Hz 流送循环，
    因此即使流送未启动也能让模型动起来。
    """

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._animating = False
        self._anim_task: asyncio.Task[Any] | None = None
        self._idle_task: asyncio.Task[Any] | None = None
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

    async def _send_frame(self, reason: str = "animation") -> None:
        """立即发送一帧 UDP 数据，并记录发送结果用于诊断。"""
        ok = await self.plugin.udp_service.send()
        if not ok:
            self.plugin.logger.warning(
                f"[{reason}] UDP 发送失败：请确认 AnyaDance 已启动且驱动已注册"
            )

    async def _ensure_streaming(self) -> None:
        """如果全局流送未启动，则自动启动它，确保后续动作能被驱动接收。"""
        if not self.plugin._streaming:
            await self.plugin.ui_api.start_stream()
            self.plugin.logger.info("动画自动启动 UDP 流送")

    async def nod_head(self, count: int = 1, speed: float = 1.0) -> dict[str, Any]:
        """通过 HMD rotation_x 正弦变化实现点头动画。"""
        await self._ensure_streaming()
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
            await self._send_frame("nod")
            await asyncio.sleep(dur)
            hmd["rotation_x"] = math.sin(half)
            hmd["rotation_w"] = math.cos(half)
            await self._send_frame("nod")
            await asyncio.sleep(dur)
        hmd["rotation_x"] = orig_rx
        hmd["rotation_y"] = orig_ry
        hmd["rotation_z"] = orig_rz
        hmd["rotation_w"] = orig_rw
        await self._send_frame("nod_restore")
        return {"action": "nod", "count": count}

    async def shake_head(self, count: int = 1, speed: float = 1.0) -> dict[str, Any]:
        """通过 HMD rotation_y 正弦变化实现摇头动画。"""
        await self._ensure_streaming()
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
            await self._send_frame("shake")
            await asyncio.sleep(dur)
            hmd["rotation_y"] = math.sin(half)
            hmd["rotation_w"] = math.cos(half)
            await self._send_frame("shake")
            await asyncio.sleep(dur)
        hmd["rotation_y"] = orig_ry
        hmd["rotation_x"] = orig_rx
        hmd["rotation_z"] = orig_rz
        hmd["rotation_w"] = orig_rw
        await self._send_frame("shake_restore")
        return {"action": "shake", "count": count}

    async def tilt_head(self, direction: str = "left", amount: float = 15.0) -> dict[str, Any]:
        """通过 HMD rotation_z 实现歪头动画，1.5 秒后恢复。"""
        await self._ensure_streaming()
        hmd = self._get_hmd()
        half = math.radians(amount) * (0.5 if direction == "left" else -0.5)
        hmd["rotation_x"] = 0.0
        hmd["rotation_z"] = math.sin(half)
        hmd["rotation_w"] = math.cos(half)
        await self._send_frame("tilt")
        await asyncio.sleep(1.5)
        hmd["rotation_z"] = 0.0
        hmd["rotation_w"] = 1.0
        await self._send_frame("tilt_restore")
        return {"action": "tilt", "direction": direction}

    async def wave_hand(self, side: str = "right", style: str = "hello") -> dict[str, Any]:
        """挥手动画：先抬手到肩高，再左右摆动前臂，动作更明显。"""
        await self._ensure_streaming()
        hand = self._get_hand(side)
        orig_px = hand.get("position_x", -0.26 if side == "left" else 0.27)
        orig_py = hand.get("position_y", 1.1 if side == "left" else 1.57)
        orig_pz = hand.get("position_z", -0.54)
        orig_rx, orig_ry, orig_rz, orig_rw = (
            hand.get("rotation_x", 0.0), hand.get("rotation_y", 0.0),
            hand.get("rotation_z", 0.0), hand.get("rotation_w", 1.0),
        )

        counts = {"hello": 5, "bye": 6, "excited": 10}
        speed_map = {"hello": 0.10, "bye": 0.13, "excited": 0.06}
        n = counts.get(style, 5)
        dur = speed_map.get(style, 0.10)
        s = 1.0 if side == "right" else -1.0

        # 抬手到肩高并略微外翻，让 VRChat 能看到完整手臂
        hand["position_x"] = orig_px + s * 0.25
        hand["position_y"] = max(orig_py, 1.45)
        hand["position_z"] = orig_pz - 0.15
        hand["rotation_x"] = 0.65
        hand["rotation_y"] = s * 0.15
        await self._send_frame("wave_raise")
        await asyncio.sleep(dur)

        # 左右摆动：rotation_z 在 ±35° 之间切换，同时轻微前后移动
        for i in range(n):
            angle = s * math.radians(35 if i % 2 == 0 else -35)
            hand["rotation_z"] = math.sin(angle * 0.5)
            hand["rotation_w"] = math.cos(angle * 0.5)
            hand["position_z"] = orig_pz - 0.15 + (0.04 if i % 2 == 0 else -0.04)
            await self._send_frame("wave")
            await asyncio.sleep(dur)

        # 恢复原始位姿
        hand["position_x"] = orig_px
        hand["position_y"] = orig_py
        hand["position_z"] = orig_pz
        hand["rotation_x"] = orig_rx
        hand["rotation_y"] = orig_ry
        hand["rotation_z"] = orig_rz
        hand["rotation_w"] = orig_rw
        await self._send_frame("wave_restore")
        return {"action": "wave", "side": side, "style": style}

    async def bow(self, depth: float = 30.0) -> dict[str, Any]:
        """HMD 前倾 + 髋部后移实现鞠躬动画，停留 0.8 秒后恢复。"""
        await self._ensure_streaming()
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
        await self._send_frame("bow")
        await asyncio.sleep(dur * 2)
        await asyncio.sleep(0.8)
        hmd["rotation_x"] = 0.0
        hmd["rotation_w"] = 1.0
        hmd["position_y"] = orig_hmd_y
        hmd["position_z"] = orig_hmd_z
        hip["position_z"] = orig_hip_z
        await self._send_frame("bow_restore")
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
