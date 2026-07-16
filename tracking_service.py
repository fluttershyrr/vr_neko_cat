from __future__ import annotations

import asyncio
import math
from typing import Any


class VrTrackingService:
    """HMD 注视追踪：计算世界坐标到 Yaw/Pitch 角度 → 四元数旋转 HMD → 支持平滑插值和 60Hz 持续追踪。"""

    MAX_PITCH_DEGREES = 60.0

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._track_target: tuple[float, float, float] | None = None
        self._track_enabled = False
        self._track_task: asyncio.Task | None = None
        self._lerp_factor = 0.12
        self._current_yaw = 0.0
        self._current_pitch = 0.0

    @property
    def _config(self) -> dict[str, Any]:
        return self.plugin._config

    @staticmethod
    def _quat_from_euler(yaw: float, pitch: float, roll: float = 0.0) -> tuple[float, float, float, float]:
        """欧拉角(Yaw/Pitch/Roll) → 四元数(x,y,z,w)，YPR 旋转顺序。"""
        cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)
        cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
        cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
        return (
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
            cr * cp * cy + sr * sp * sy,
        )

    @staticmethod
    def _slerp_value(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    def _compute_look_at(self, tx: float, ty: float, tz: float,
                         px: float = 0.0, py: float = 1.5, pz: float = 0.0) -> tuple[float, float]:
        """从 HMD 位置(px,py,pz) 计算到目标点(tx,ty,tz) 的 Yaw/Pitch 角度，Pitch 限制 ±MAX_PITCH_DEGREES。"""
        dx = tx - px
        dy = ty - py
        dz = tz - pz
        dist = math.sqrt(dx * dx + dz * dz)
        if dist < 0.001:
            return (self._current_yaw, 0.0)
        target_yaw = math.atan2(dx, abs(dz) if abs(dz) > 0.001 else 0.001)
        target_pitch = -math.atan2(dy, dist)
        max_pitch_rad = math.radians(self.MAX_PITCH_DEGREES)
        target_pitch = max(-max_pitch_rad, min(max_pitch_rad, target_pitch))
        return (target_yaw, target_pitch)

    def look_at(self, x: float, y: float, z: float, smooth: float = -1.0) -> dict[str, Any]:
        hmd_cfg = self._config.get("hmd_pose", {})
        px = float(hmd_cfg.get("position_x", 0.0))
        py = float(hmd_cfg.get("position_y", 1.5))
        pz = float(hmd_cfg.get("position_z", 0.0))
        lf = smooth if smooth >= 0 else self._lerp_factor

        target_yaw, target_pitch = self._compute_look_at(x, y, z, px, py, pz)
        self._current_yaw = self._slerp_value(self._current_yaw, target_yaw, lf)
        self._current_pitch = self._slerp_value(self._current_pitch, target_pitch, lf)

        qx, qy, qz, qw = self._quat_from_euler(self._current_yaw, self._current_pitch, 0.0)
        self._config.setdefault("hmd_pose", {}).update({
            "rotation_x": qx, "rotation_y": qy, "rotation_z": qz, "rotation_w": qw,
        })
        return {
            "target": [x, y, z],
            "hmd_pos": [px, py, pz],
            "yaw_deg": math.degrees(self._current_yaw),
            "pitch_deg": math.degrees(self._current_pitch),
        }

    def look_at_direction(self, yaw_deg: float = 0.0, pitch_deg: float = 0.0, smooth: float = -1.0) -> dict[str, Any]:
        lf = smooth if smooth >= 0 else self._lerp_factor
        target_yaw = math.radians(yaw_deg)
        target_pitch = math.radians(max(-self.MAX_PITCH_DEGREES, min(self.MAX_PITCH_DEGREES, pitch_deg)))
        self._current_yaw = self._slerp_value(self._current_yaw, target_yaw, lf)
        self._current_pitch = self._slerp_value(self._current_pitch, target_pitch, lf)

        qx, qy, qz, qw = self._quat_from_euler(self._current_yaw, self._current_pitch, 0.0)
        self._config.setdefault("hmd_pose", {}).update({
            "rotation_x": qx, "rotation_y": qy, "rotation_z": qz, "rotation_w": qw,
        })
        return {"yaw_deg": yaw_deg, "pitch_deg": pitch_deg, "current_yaw": math.degrees(self._current_yaw)}

    def reset_head(self) -> dict[str, Any]:
        self._current_yaw = 0.0
        self._current_pitch = 0.0
        self._config.setdefault("hmd_pose", {}).update({
            "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0, "rotation_w": 1.0,
        })
        return {"reset": True}

    async def _track_loop(self) -> None:
        while self._track_enabled and self._track_target is not None:
            self.look_at(*self._track_target)
            await self.plugin.udp_service.send()
            await asyncio.sleep(1.0 / 60)

    async def start_tracking(self, x: float, y: float, z: float) -> dict[str, Any]:
        self._track_target = (x, y, z)
        self._track_enabled = True
        if self._track_task is None or self._track_task.done():
            self._track_task = asyncio.get_event_loop().create_task(self._track_loop())
        return {"tracking": True, "target": self._track_target}

    async def update_track_target(self, x: float, y: float, z: float) -> dict[str, Any]:
        self._track_target = (x, y, z)
        return {"target_updated": True, "target": self._track_target}

    async def stop_tracking(self) -> dict[str, Any]:
        self._track_enabled = False
        self._track_target = None
        if self._track_task:
            self._track_task.cancel()
            try:
                await self._track_task
            except asyncio.CancelledError:
                pass
            self._track_task = None
        return {"tracking": False}

    def set_smooth_factor(self, factor: float) -> dict[str, Any]:
        self._lerp_factor = max(0.01, min(1.0, factor))
        return {"lerp_factor": self._lerp_factor}

    def get_tracking_state(self) -> dict[str, Any]:
        return {
            "tracking": self._track_enabled,
            "target": list(self._track_target) if self._track_target else None,
            "current_yaw_deg": math.degrees(self._current_yaw),
            "current_pitch_deg": math.degrees(self._current_pitch),
            "lerp_factor": self._lerp_factor,
        }
