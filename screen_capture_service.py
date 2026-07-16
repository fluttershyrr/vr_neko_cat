from __future__ import annotations

import base64
import ctypes
import io
import os
import platform
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

try:
    import mss
    import mss.tools
    _HAS_MSS = True
except ImportError:
    _HAS_MSS = False

from PIL import Image, ImageGrab


class VrScreenCapture:
    """屏幕截图服务：mss(优先)/PIL 后端 → 全屏/窗口/区域截图 → base64 JPEG/PNG 供 AI 视觉分析。"""

    TEMP_DIR = Path(os.environ.get("TEMP", "/tmp")) / "vr_neko_cat_captures"

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._last_capture: dict[str, Any] | None = None
        self._capture_count = 0
        self._config = {
            "monitor_index": 0,
            "quality": 75,
            "scale": 1.0,
            "format": "jpeg",
            "auto_save": False,
        }
        self._screens: list[dict[str, Any]] = []

    @property
    def config_service(self):
        return self.plugin.config_service

    def _get_monitors(self) -> list[dict[str, Any]]:
        if self._screens:
            return self._screens
        monitors: list[dict[str, Any]] = []
        try:
            if _HAS_MSS:
                with mss.MSS() as sct:
                    for i, m in enumerate(sct.monitors):
                        monitors.append({
                            "index": i,
                            "width": m["width"],
                            "height": m["height"],
                            "left": m.get("left", 0),
                            "top": m.get("top", 0),
                            "primary": i == 1,
                        })
            else:
                img = ImageGrab.grab()
                monitors.append({
                    "index": 0,
                    "width": img.width,
                    "height": img.height,
                    "left": 0,
                    "top": 0,
                    "primary": True,
                })
        except Exception:
            monitors.append({
                "index": 0, "width": 1920, "height": 1080,
                "left": 0, "top": 0, "primary": True,
            })
        self._screens = monitors
        return monitors

    def _build_region(self, monitor_info: dict[str, Any], scale: float) -> dict[str, int] | None:
        """构建 mss 截图区域字典，应用缩放；PIL 后端返回 None。"""
        if _HAS_MSS:
            return {
                "left": monitor_info["left"],
                "top": monitor_info["top"],
                "width": int(monitor_info["width"] * scale),
                "height": int(monitor_info["height"] * scale),
            }
        return None

    def capture(self, monitor_index: int = -1, quality: int = -1,
                scale: float = -1.0) -> dict[str, Any]:
        """全屏/指定显示器截图，返回 base64 编码图像和元信息。"""
        if quality <= 0:
            quality = self._config["quality"]
        if scale <= 0:
            scale = self._config["scale"]
        if monitor_index < 0:
            monitor_index = self._config["monitor_index"]

        monitors = self._get_monitors()
        if monitor_index >= len(monitors):
            monitor_index = 0
        monitor_info = monitors[monitor_index]

        t0 = time.perf_counter()
        pil_img: Image.Image | None = None

        try:
            if _HAS_MSS:
                region = self._build_region(monitor_info, scale)
                with mss.MSS() as sct:
                    raw = sct.grab(region)
                    pil_img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            else:
                pil_img = ImageGrab.grab(all_screens=False if monitor_index > 0 else True)
                if scale != 1.0 and pil_img:
                    new_size = (int(pil_img.width * scale), int(pil_img.height * scale))
                    pil_img = pil_img.resize(new_size, Image.LANCZOS)
        except Exception as e:
            return {"ok": False, "error": str(e), "backend": "mss" if _HAS_MSS else "pil"}

        if pil_img is None:
            return {"ok": False, "error": "capture returned None"}

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        buf = io.BytesIO()
        fmt = self._config["format"]
        pil_img.save(buf, format="JPEG" if fmt == "jpeg" else "PNG",
                     quality=quality if fmt == "jpeg" else None,
                     optimize=True)
        img_bytes = buf.getvalue()
        b64 = base64.b64encode(img_bytes).decode("ascii")

        w, h = pil_img.width, pil_img.height
        size_kb = round(len(img_bytes) / 1024, 1)

        filepath = ""
        if self._config["auto_save"]:
            self.TEMP_DIR.mkdir(parents=True, exist_ok=True)
            self._capture_count += 1
            ext = fmt if fmt == "png" else "jpg"
            filepath = str(self.TEMP_DIR / f"capture_{self._capture_count:04d}.{ext}")
            pil_img.save(filepath, quality=quality if ext == "jpg" else None)

        self._last_capture = {
            "monitor_index": monitor_index,
            "width": w, "height": h,
            "size_kb": size_kb,
            "format": fmt,
            "elapsed_ms": elapsed_ms,
            "backend": "mss" if _HAS_MSS else "pil",
            "filepath": filepath,
            "timestamp": time.time(),
        }
        return {
            "ok": True,
            "image_base64": b64,
            "width": w, "height": h,
            "size_kb": size_kb,
            "format": fmt,
            "elapsed_ms": elapsed_ms,
            "monitor_index": monitor_index,
        }

    def get_monitors(self) -> list[dict[str, Any]]:
        return self._get_monitors()

    def get_state(self) -> dict[str, Any]:
        monitors = self._get_monitors()
        return {
            "last_capture": self._last_capture,
            "monitors": monitors,
            "config": self._config,
            "backend": "mss" if _HAS_MSS else "pil",
        }

    def set_config(self, **kwargs) -> dict[str, Any]:
        for k, v in kwargs.items():
            if k in self._config:
                self._config[k] = v
        return {"screen_capture_config": self._config}

    @staticmethod
    def get_active_window_rect() -> dict[str, int] | None:
        """获取前台窗口矩形区域，兼容全屏/无边框游戏窗口。"""
        if platform.system() != "Windows":
            return None
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
            return {
                "left": left, "top": top, "right": right, "bottom": bottom,
                "width": right - left, "height": bottom - top,
            }
        except Exception:
            return None

    @staticmethod
    def get_active_window_title_raw() -> str | None:
        """获取前台窗口标题。"""
        if platform.system() != "Windows":
            return None
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return None
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return None

    def capture_active_window(self, quality: int = -1) -> dict[str, Any]:
        """截取当前前台窗口区域，不包含 NEKO 自身覆盖层。"""
        rect = self.get_active_window_rect()
        if rect is None:
            return {"ok": False, "error": "无法获取前台窗口区域"}
        if rect["width"] <= 0 or rect["height"] <= 0:
            return {"ok": False, "error": f"窗口尺寸无效 {rect['width']}x{rect['height']}"}

        if quality <= 0:
            quality = self._config["quality"]

        t0 = time.perf_counter()
        pil_img: Image.Image | None = None

        try:
            if _HAS_MSS:
                region = {
                    "left": rect["left"], "top": rect["top"],
                    "width": rect["width"], "height": rect["height"],
                }
                with mss.MSS() as sct:
                    raw = sct.grab(region)
                    pil_img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            else:
                pil_img = ImageGrab.grab(bbox=(
                    rect["left"], rect["top"],
                    rect["left"] + rect["width"], rect["top"] + rect["height"],
                ))
        except Exception as e:
            return {"ok": False, "error": str(e), "backend": "mss" if _HAS_MSS else "pil"}

        if pil_img is None:
            return {"ok": False, "error": "capture returned None"}

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        buf = io.BytesIO()
        fmt = self._config["format"]
        pil_img.save(buf, format="JPEG" if fmt == "jpeg" else "PNG",
                     quality=quality if fmt == "jpeg" else None,
                     optimize=True)
        img_bytes = buf.getvalue()
        b64 = base64.b64encode(img_bytes).decode("ascii")

        w, h = pil_img.width, pil_img.height
        size_kb = round(len(img_bytes) / 1024, 1)

        window_title = self.get_active_window_title_raw() or ""

        self._last_capture = {
            "type": "active_window",
            "window_title": window_title,
            "window_rect": rect,
            "width": w, "height": h,
            "size_kb": size_kb,
            "format": fmt,
            "elapsed_ms": elapsed_ms,
            "backend": "mss" if _HAS_MSS else "pil",
            "timestamp": time.time(),
        }
        return {
            "ok": True,
            "image_base64": b64,
            "width": w, "height": h,
            "size_kb": size_kb,
            "format": fmt,
            "elapsed_ms": elapsed_ms,
            "window_rect": rect,
            "window_title": window_title,
        }

    def capture_game_region(self, left: int, top: int, width: int, height: int,
                            quality: int = -1) -> dict[str, Any]:
        """截取屏幕指定坐标区域。"""
        if quality <= 0:
            quality = self._config["quality"]
        if width <= 0 or height <= 0:
            return {"ok": False, "error": f"区域尺寸无效 {width}x{height}"}

        t0 = time.perf_counter()
        pil_img: Image.Image | None = None

        try:
            if _HAS_MSS:
                region = {"left": left, "top": top, "width": width, "height": height}
                with mss.MSS() as sct:
                    raw = sct.grab(region)
                    pil_img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            else:
                pil_img = ImageGrab.grab(bbox=(left, top, left + width, top + height))
        except Exception as e:
            return {"ok": False, "error": str(e), "backend": "mss" if _HAS_MSS else "pil"}

        if pil_img is None:
            return {"ok": False, "error": "capture returned None"}

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        buf = io.BytesIO()
        fmt = self._config["format"]
        pil_img.save(buf, format="JPEG" if fmt == "jpeg" else "PNG",
                     quality=quality if fmt == "jpeg" else None,
                     optimize=True)
        img_bytes = buf.getvalue()
        b64 = base64.b64encode(img_bytes).decode("ascii")

        w, h = pil_img.width, pil_img.height
        size_kb = round(len(img_bytes) / 1024, 1)

        return {
            "ok": True,
            "image_base64": b64,
            "width": w, "height": h,
            "size_kb": size_kb,
            "format": fmt,
            "elapsed_ms": elapsed_ms,
            "region": {"left": left, "top": top, "width": width, "height": height},
        }

    def load_config_from_plugin(self) -> None:
        """从插件全局配置中同步截图相关参数到本服务配置。"""
        cfg = self.config_service.get_config()
        for k in self._config:
            key = f"capture_{k}"
            if key in cfg:
                self._config[k] = cfg[key]
