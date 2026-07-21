from __future__ import annotations

import asyncio
import json
import socket
import time
from typing import Any


class VrUdpService:
    """UDP 通信层：将设备位姿/输入序列化为 AnyaDance 协议 JSON，发送到 127.0.0.1:39570。"""

    PROTOCOL_VERSION = 1
    MAX_PACKET_BYTES = 8192
    MAX_ABS_POSITION = 10.0
    MAX_DEVICE_Y = 2.0
    CONSECUTIVE_FAIL_THRESHOLD = 10
    LOG_EVERY_N_SUCCESS = 300

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._sock: socket.socket | None = None
        self._lock = asyncio.Lock()
        self._consecutive_fails: int = 0
        self._total_sends: int = 0
        self._total_failures: int = 0
        self._last_send_time: float = 0.0
        self._is_connected: bool = True
        self._dumped_first: bool = False  # 是否已打印首帧诊断
        self._port_checked: bool = False   # 是否已做过端口探测
        self._port_alive: bool | None = None  # None=未探测, True=有监听, False=无监听

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
        """构建符合 AnyaDance 协议的 JSON 数据包。

        驱动端 ParsePoseFrame 遍历 kDevices，用 device.id (短名) 作为 key 查找：
          "hmd", "left_controller", "right_controller", "hip", "left_foot", "right_foot"
        """
        cfg = self._settings
        send_hmd = bool(cfg.get("send_hmd_pose", True))
        send_controllers = bool(cfg.get("send_controller_poses", True))
        send_trackers = bool(cfg.get("send_tracker_poses", True))

        devices: dict[str, Any] = {}
        if send_hmd:
            devices["hmd"] = self._get_device_pose("hmd_pose")
        if send_controllers:
            devices["left_controller"] = self._get_device_pose("left_controller_pose")
            devices["right_controller"] = self._get_device_pose("right_controller_pose")
        if send_trackers:
            devices["hip"] = self._get_device_pose("hip_pose")
            devices["left_foot"] = self._get_device_pose("left_foot_pose")
            devices["right_foot"] = self._get_device_pose("right_foot_pose")

        inputs: dict[str, Any] = {}
        if send_controllers:
            inputs["left_controller"] = self._get_controller_input("left_controller_input")
            inputs["right_controller"] = self._get_controller_input("right_controller_input")
        return {"version": self.PROTOCOL_VERSION, "devices": devices, "inputs": inputs}

    def _check_port_alive(self) -> bool:
        """探测目标 UDP 端口是否有进程在监听（通过尝试连接判断）。
        UDP 无连接协议，这里用发送 0 字节数据 + 检查是否报错来判断端口可达性。
        返回 True=端口可达/有监听, False=无监听。
        """
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.settimeout(0.3)
            # 发送空探测包，如果端口无监听，某些系统会返回 ICMP Port Unreachable
            probe.sendto(b"\x00", (self.host, self.port))
            # 尝试接收（不会真的收到数据，但超时说明没有 ICMP 错误）
            try:
                probe.recvfrom(1)
            except (socket.timeout, OSError):
                pass
            probe.close()
            return True  # 没有立即报错，认为可达
        except OSError as e:
            self.plugin.logger.warning(f"[UDP] 端口 {self.host}:{self.port} 探测失败: {e}")
            return False

    def send_sync(self) -> bool:
        """同步发送 UDP 数据包（由异步方法在线程中调用）。"""
        # 首次发送时探测端口（仅一次）
        if not self._port_checked:
            self._port_checked = True
            self._port_alive = self._check_port_alive()
            if not self._port_alive:
                self.plugin.logger.error(
                    f"[UDP] ⚠️ 目标端口 {self.host}:{self.port} 无进程监听！\n"
                    f"  请确认:\n"
                    f"  1) SteamVR 正在运行\n"
                    f"  2) AnyaDance 驱动已注册 (点击'注册驱动')\n"
                    f"  3) 注册后已重启 SteamVR\n"
                    f"  4) SteamVR 设置中可见 'anyadance' 驱动"
                )
            else:
                self.plugin.logger.info(f"[UDP] ✓ 端口 {self.host}:{self.port} 可达，驱动已就绪")
        packet = self.build_packet()
        raw = json.dumps(packet, ensure_ascii=False, indent=None).encode("utf-8")
        # 诊断：打印首帧完整 JSON + 每 1000 帧一次采样
        if not self._dumped_first or (self._total_sends > 0 and self._total_sends % 1000 == 0):
            self._dumped_first = True
            pretty = json.dumps(packet, ensure_ascii=False, indent=2)
            self.plugin.logger.info(f"[UDP-DIAG] 第 {self._total_sends + 1} 帧 ({len(raw)}B):\n{pretty}")
        if len(raw) >= self.MAX_PACKET_BYTES:
            self.plugin.logger.warning(f"数据包过大 ({len(raw)}B)，已跳过")
            return False
        try:
            if self._sock is None:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
                except OSError:
                    pass
            self._sock.sendto(raw, (self.host, self.port))
            now = time.monotonic()
            prev = self._last_send_time
            self._consecutive_fails = 0
            self._total_sends += 1
            self._last_send_time = now
            if not self._is_connected:
                self._is_connected = True
                self.plugin.logger.info("[UDP] 连接恢复")
            if self._total_sends % self.LOG_EVERY_N_SUCCESS == 0:
                interval_ms = (now - prev) * 1000 if prev > 0 else 0.0
                self.plugin.logger.debug(
                    f"[UDP] 已发送 {self._total_sends} 帧，间隔≈{interval_ms:.1f}ms"
                )
            return True
        except OSError as e:
            self._consecutive_fails += 1
            self._total_failures += 1
            was_connected = self._is_connected
            if self._consecutive_fails >= self.CONSECUTIVE_FAIL_THRESHOLD and was_connected:
                self._is_connected = False
                self.plugin.logger.error(
                    f"[UDP] 连接疑似断开！连续失败 {self._consecutive_fails} 次: {e}"
                )
            elif self._consecutive_fails <= 3:
                self.plugin.logger.warning(f"[UDP] 发送失败 ({self._consecutive_fails}): {e}")
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            return False

    async def send(self) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self.send_sync)

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_sends": self._total_sends,
            "total_failures": self._total_failures,
            "consecutive_fails": self._consecutive_fails,
            "is_connected": self._is_connected,
            "last_send_interval_ms": (
                (time.monotonic() - self._last_send_time) * 1000
                if self._last_send_time > 0 else -1.0
            ),
        }

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
