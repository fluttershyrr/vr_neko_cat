from __future__ import annotations

import asyncio
import json
import socket
from typing import Any


class VrUdpService:
    """UDP 通信层：将配置中的设备位姿/输入序列化为 AnyaDance 协议 JSON，发送到 127.0.0.1:39570。"""

    PROTOCOL_VERSION = 1
    MAX_PACKET_BYTES = 8192
    MAX_ABS_POSITION = 10.0
    MAX_DEVICE_Y = 2.0

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._sock: socket.socket | None = None
        self._lock = asyncio.Lock()

    @property
    def _settings(self) -> dict[str, Any]:
        return self.plugin._config

    @property
    def host(self) -> str:
        return str(self._settings.get("host", "127.0.0.1"))

    @property
    def port(self) -> int:
        return int(self._settings.get("port", 39570))

    def _clamp(self, v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(v or 0.0)))

    def _clamp_position(self, x: float, y: float, z: float) -> list[float]:
        return [
            self._clamp(x, -self.MAX_ABS_POSITION, self.MAX_ABS_POSITION),
            self._clamp(y, -self.MAX_ABS_POSITION, self.MAX_DEVICE_Y),
            self._clamp(z, -self.MAX_ABS_POSITION, self.MAX_ABS_POSITION),
        ]

    def _clamp_rotation(self, qx: float, qy: float, qz: float, qw: float) -> list[float]:
        qx, qy, qz, qw = map(float, (qx, qy, qz, qw))
        sq = qx * qx + qy * qy + qz * qz + qw * qw
        if sq < 0.5 or sq > 1.5:
            return [0.0, 0.0, 0.0, 1.0]
        scale = 1.0 / (sq ** 0.5)
        return [qx * scale, qy * scale, qz * scale, qw * scale]

    def _clamp_input(self, v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(v or 0.0)))

    def _get_device_pose(self, device_key: str) -> dict[str, Any]:
        cfg = self._settings.get(device_key, {})
        return {
            "valid": True,
            "connected": True,
            "pose": {
                "position": self._clamp_position(
                    cfg.get("position_x", 0.0),
                    cfg.get("position_y", 0.0),
                    cfg.get("position_z", 0.0),
                ),
                "rotation_xyzw": self._clamp_rotation(
                    cfg.get("rotation_x", 0.0),
                    cfg.get("rotation_y", 0.0),
                    cfg.get("rotation_z", 0.0),
                    cfg.get("rotation_w", 1.0),
                ),
            },
        }

    def _get_controller_input(self, key: str) -> dict[str, Any]:
        cfg = self._settings.get(key, {})
        return {
            "trigger_click": bool(cfg.get("trigger_click", False)),
            "trigger_value": self._clamp_input(cfg.get("trigger_value", 0.0), 0.0, 1.0),
            "menu_click": bool(cfg.get("menu_click", False)),
            "system_click": bool(cfg.get("system_click", False)),
            "a_click": bool(cfg.get("a_click", False)),
            "b_click": bool(cfg.get("b_click", False)),
            "grip_click": bool(cfg.get("grip_click", False)),
            "grip_value": self._clamp_input(cfg.get("grip_value", 0.0), 0.0, 1.0),
            "joystick_x": self._clamp_input(cfg.get("joystick_x", 0.0), -1.0, 1.0),
            "joystick_y": self._clamp_input(cfg.get("joystick_y", 0.0), -1.0, 1.0),
            "trackpad_x": self._clamp_input(cfg.get("trackpad_x", 0.0), -1.0, 1.0),
            "trackpad_y": self._clamp_input(cfg.get("trackpad_y", 0.0), -1.0, 1.0),
            "finger_bends": self._get_finger_bends(key),
        }

    def _get_finger_bends(self, key: str) -> dict[str, float]:
        bends_key = key.replace("_input", "_finger_bends")
        cfg = self._settings.get(bends_key, {})
        return {
            "thumb": self._clamp_input(cfg.get("thumb", 0.0), 0.0, 1.0),
            "index": self._clamp_input(cfg.get("index", 0.0), 0.0, 1.0),
            "middle": self._clamp_input(cfg.get("middle", 0.0), 0.0, 1.0),
            "ring": self._clamp_input(cfg.get("ring", 0.0), 0.0, 1.0),
            "pinky": self._clamp_input(cfg.get("pinky", 0.0), 0.0, 1.0),
        }

    def build_packet(self) -> dict[str, Any]:
        """构建符合 AnyaDance 协议的 JSON 数据包：version + 6 设备位姿 + 2 控制器输入。"""
        devices = {
            "hmd": self._get_device_pose("hmd_pose"),
            "left_controller": self._get_device_pose("left_controller_pose"),
            "right_controller": self._get_device_pose("right_controller_pose"),
            "hip": self._get_device_pose("hip_pose"),
            "left_foot": self._get_device_pose("left_foot_pose"),
            "right_foot": self._get_device_pose("right_foot_pose"),
        }
        inputs = {
            "left_controller": self._get_controller_input("left_controller_input"),
            "right_controller": self._get_controller_input("right_controller_input"),
        }
        return {"version": self.PROTOCOL_VERSION, "devices": devices, "inputs": inputs}

    def send_sync(self) -> bool:
        """同步发送 UDP 数据包（由异步方法在线程中调用）。"""
        packet = self.build_packet()
        raw = json.dumps(packet, ensure_ascii=False).encode("utf-8")
        if len(raw) >= self.MAX_PACKET_BYTES:
            self.plugin.logger.warning(f"数据包过大 ({len(raw)}B)，已跳过")
            return False
        try:
            if self._sock is None:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.sendto(raw, (self.host, self.port))
            return True
        except OSError as e:
            self.plugin.logger.error(f"UDP 发送失败: {e}")
            self._sock = None
            return False

    async def send(self) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self.send_sync)

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
