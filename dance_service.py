from __future__ import annotations

import asyncio
import os
import struct
import time
from pathlib import Path
from typing import Any

from .pose_service import VrPoseService


class VrDanceService:
    """VMD 舞蹈文件解析与播放：二进制解析 → 骨骼→VR设备映射 → 帧循环驱动 6 设备位姿。"""

    FLOAT_SIZE = 4
    VMD_MAGIC = b"Vocaloid Motion Data 0002"

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._playing = False
        self._task: asyncio.Task | None = None
        self._frame_index = 0
        self._bone_frames: list[dict[str, Any]] = []
        self._total_frames = 0

    @property
    def _config(self) -> dict[str, Any]:
        return self.plugin._config

    @property
    def pose_service(self) -> VrPoseService:
        return self.plugin.pose_service

    @property
    def udp_service(self):
        return self.plugin.udp_service

    @property
    def is_playing(self) -> bool:
        return self._playing

    def _read_null_terminated(self, data: bytes, offset: int, max_len: int) -> str:
        end = offset
        while end < min(offset + max_len, len(data)):
            if data[end] == 0:
                break
            end += 1
        return data[offset:end].decode("shift_jis", errors="replace")

    def load_vmd(self, path: str) -> bool:
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            self.plugin.logger.error(f"读取 VMD 文件失败: {e}")
            return False

        if len(data) < len(self.VMD_MAGIC) + 2 or data[:len(self.VMD_MAGIC)] != self.VMD_MAGIC:
            self.plugin.logger.error("无效的 VMD 文件（magic 不匹配）")
            return False

        offset = len(self.VMD_MAGIC)
        model_name = self._read_null_terminated(data, offset, 20)
        offset += 20

        bone_count = struct.unpack_from("<I", data, offset)[0]
        offset += 4

        self._bone_frames = []
        for _ in range(bone_count):
            bone_name = self._read_null_terminated(data, offset, 15)
            offset += 15
            frame_no, px, py, pz, rx, ry, rz, rw = struct.unpack_from("<I3f4f", data, offset)
            offset += 32
            interp = list(data[offset:offset + 64])
            offset += 64
            self._bone_frames.append({
                "bone": bone_name, "frame": frame_no,
                "position": [px, py, pz],
                "rotation": [rx, ry, rz, rw],
                "interpolation": interp,
            })

        self._bone_frames.sort(key=lambda f: f["frame"])
        self._total_frames = len(self._bone_frames)
        self._frame_index = 0
        self.plugin.logger.info(f"VMD 加载完成: {self._total_frames} 骨骼帧")
        return True

    def _map_bone_to_vr(self, bone_name: str) -> tuple[str, float, float, float]:
        """将 MMD 骨骼名映射为 VR 设备 ID + 基准位置偏移。返回空字符串表示跳过。"""
        name_lower = bone_name.lower()
        if "頭" in bone_name or "head" in name_lower:
            return ("hmd", 0.0, 1.5, 0.0)
        if "左腕" in bone_name or "left wrist" in name_lower or "左手首" in bone_name:
            return ("left_controller", -0.26, 1.1, -0.54)
        if "右腕" in bone_name or "right wrist" in name_lower or "右手首" in bone_name:
            return ("right_controller", 0.27, 1.57, -0.54)
        if "腰" in bone_name or "hip" in name_lower or "下半身" in bone_name:
            return ("hip", 0.0, 1.07, -0.05)
        if "左足" in bone_name or "left ankle" in name_lower or "左足首" in bone_name:
            return ("left_foot", -0.09, 0.26, 0.1)
        if "右足" in bone_name or "right ankle" in name_lower or "右足首" in bone_name:
            return ("right_foot", 0.09, 0.26, 0.1)
        if "左ひじ" in bone_name or "left elbow" in name_lower:
            return ("left_controller", -0.35, 1.2, -0.4)
        if "右ひじ" in bone_name or "right elbow" in name_lower:
            return ("right_controller", 0.35, 1.2, -0.4)
        return ("", 0.0, 0.0, 0.0)

    def apply_frame(self, frame_data: dict[str, Any]) -> None:
        """将单帧骨骼数据写入对应 VR 设备位姿，应用手部可达范围和高度偏移。"""
        dev, base_x, base_y, base_z = self._map_bone_to_vr(frame_data["bone"])
        if not dev:
            return
        speed = float(self._config.get("dance_speed", 1.0))
        height = float(self._config.get("dance_height", 1.5))
        hand_reach = float(self._config.get("dance_hand_reach", 1.22))

        px, py, pz = frame_data["position"]
        rx, ry, rz, rw = frame_data["rotation"]

        if dev in ("left_controller", "right_controller"):
            px *= hand_reach
            pz *= hand_reach

        self.pose_service.set_device_position(dev, base_x + px * speed, base_y + py + (height - 1.5), base_z + pz * speed)
        self.pose_service.set_device_rotation(dev, rx, ry, rz, rw)

    async def _play_loop(self) -> None:
        """舞蹈播放主循环：逐帧应用到设备位姿 → 发送 UDP → 支持循环播放。"""
        fps = float(self._config.get("dance_fps", 60.0))
        frame_interval = 1.0 / max(1.0, fps)
        while self._playing and self._frame_index < self._total_frames:
            self.apply_frame(self._bone_frames[self._frame_index])
            await self.udp_service.send()
            self._frame_index += 1
            await asyncio.sleep(frame_interval)
        if self._playing:
            loop = bool(self._config.get("dance_loop", True))
            if loop and self._total_frames > 0:
                self._frame_index = 0
                self._task = asyncio.create_task(self._play_loop())
            else:
                self._playing = False

    async def play(self, vmd_path: str = "") -> bool:
        path = vmd_path or self._config.get("dance_vmd_path", "")
        if not path or not os.path.exists(path):
            self.plugin.logger.error(f"VMD 文件不存在: {path}")
            return False
        if not self.load_vmd(path):
            return False
        self._playing = True
        self._frame_index = 0
        self._task = asyncio.create_task(self._play_loop())
        return True

    async def stop(self) -> None:
        self._playing = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def get_state(self) -> dict[str, Any]:
        return {
            "playing": self._playing,
            "current_frame": self._frame_index,
            "total_frames": self._total_frames,
            "progress": self._frame_index / max(1, self._total_frames) if self._total_frames > 0 else 0.0,
        }
