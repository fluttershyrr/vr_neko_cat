from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path
from typing import Any


class VrDriverService:
    """AnyaDance 驱动生命周期管理：查找/启动/停止 AnyaDance.exe + SteamVR 驱动注册/注销 + SteamVR 重启。"""

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._process: subprocess.Popen | None = None
        self._running = False

    @property
    def _config(self) -> dict[str, Any]:
        return self.plugin._config

    def _anyadance_dir(self) -> str:
        """查找 AnyaDance 目录：优先用户配置 → 插件内置 → 工作区 → 环境变量 → 当前目录。"""
        path = self._config.get("anyadance_path", "")
        if path and Path(path).is_dir():
            return path
        candidates = [
            Path(__file__).resolve().parent / "anyadance",
            Path(__file__).resolve().parent.parent.parent.parent.parent / "anyadance",
            Path(os.environ.get("ANYADANCE_ROOT", "")),
            Path.cwd() / "anyadance",
        ]
        for d in candidates:
            if d.is_dir() and (d / "AnyaDance.exe").exists():
                return str(d.resolve())
        return ""

    def _anyadance_exe(self) -> str:
        d = self._anyadance_dir()
        if not d:
            return ""
        p = Path(d) / "AnyaDance.exe"
        return str(p) if p.exists() else ""

    def _find_vrpathreg(self) -> str:
        """查找 SteamVR 的 vrpathreg.exe：环境变量 → 默认路径 → 注册表 → where 命令。"""
        steam_dirs = [
            Path(os.environ.get("STEAMVR_ROOT", "")),
            Path("C:/Program Files (x86)/Steam/steamapps/common/SteamVR"),
        ]
        for d in steam_dirs:
            p = d / "bin" / "win64" / "vrpathreg.exe"
            if p.exists():
                return str(p)
        steam_root = self._find_steam_root()
        if steam_root:
            p = Path(steam_root) / "steamapps" / "common" / "SteamVR" / "bin" / "win64" / "vrpathreg.exe"
            if p.exists():
                return str(p)
        try:
            result = subprocess.run(["where", "vrpathreg"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().splitlines()[0].strip()
        except Exception:
            pass
        return ""

    def _find_steam_root(self) -> str:
        """通过 Windows 注册表查找 Steam 安装目录。"""
        for reg in [r"HKCU\Software\Valve\Steam", r"HKLM\SOFTWARE\WOW6432Node\Valve\Steam"]:
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER if "HKCU" in reg else winreg.HKEY_LOCAL_MACHINE,
                                     reg.split("\\", 1)[1])
                val, _ = winreg.QueryValueEx(key, "SteamPath")
                winreg.CloseKey(key)
                return str(val)
            except Exception:
                continue
        return str(Path("C:/Program Files (x86)/Steam"))

    def _run_subprocess(self, args: list[str], timeout: int = 15) -> dict[str, Any]:
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return {"ok": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr, "code": result.returncode}
        except subprocess.TimeoutExpired:
            return {"ok": False, "stdout": "", "stderr": "Timeout", "code": -1}
        except FileNotFoundError:
            return {"ok": False, "stdout": "", "stderr": "Executable not found", "code": -1}

    def _is_driver_registered(self) -> bool:
        vrpathreg = self._find_vrpathreg()
        if not vrpathreg:
            return False
        r = self._run_subprocess([vrpathreg, "finddriver", "anyadance"])
        return r.get("ok", False)

    def is_anyadance_running(self) -> bool:
        if self._process is not None and self._process.poll() is None:
            return True
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq AnyaDance.exe", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return "AnyaDance.exe" in result.stdout
        except Exception:
            return False

    def get_driver_state(self) -> dict[str, Any]:
        ad_dir = self._anyadance_dir()
        exe = self._anyadance_exe()
        ad_running = self.is_anyadance_running()
        registered = self._is_driver_registered() if ad_dir else False

        state = {
            "anyadance_path": ad_dir,
            "anyadance_exe": exe,
            "anyadance_running": ad_running,
            "driver_registered": registered,
            "anyadance_found": bool(ad_dir),
            "vrpathreg_found": bool(self._find_vrpathreg()),
        }

        if ad_running:
            state["udp_listening"] = self._check_udp_port()
        return state

    def _check_udp_port(self) -> bool:
        """检测 AnyaDance UDP 端口是否已监听（发送空包，收到拒绝=端口已被占用=AnyaDance 在监听）。"""
        import socket
        host = self._config.get("host", "127.0.0.1")
        port = self._config.get("port", 39570)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.bind(("127.0.0.1", 0))
            s.sendto(b"\x00", (host, port))
            s.recvfrom(1)
            s.close()
            return False
        except (ConnectionRefusedError, ConnectionResetError):
            return True
        except Exception:
            return True

    async def register_driver(self) -> dict[str, Any]:
        vrpathreg = self._find_vrpathreg()
        if not vrpathreg:
            return {"ok": False, "error": "未找到 SteamVR 安装目录，无法定位 vrpathreg.exe"}
        ad_dir = self._anyadance_dir()
        if not ad_dir:
            return {"ok": False, "error": "未找到 AnyaDance 目录，请在设置中配置 anyadance_path"}

        if self._is_driver_registered():
            return {"ok": True, "status": "already_registered"}

        r = self._run_subprocess([vrpathreg, "adddriver", ad_dir])
        if r["ok"]:
            record_path = Path(os.environ["LOCALAPPDATA"]) / "AnyaDance" / "registered_driver_path.txt"
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_text(ad_dir, encoding="utf-8")
            return {"ok": True, "status": "registered", "path": ad_dir}
        return {"ok": False, "error": r.get("stderr", "注册失败")}

    async def unregister_driver(self) -> dict[str, Any]:
        vrpathreg = self._find_vrpathreg()
        if not vrpathreg:
            return {"ok": False, "error": "未找到 vrpathreg.exe"}
        ad_dir = self._anyadance_dir()
        if not ad_dir:
            return {"ok": False, "error": "未找到 AnyaDance 目录"}

        if not self._is_driver_registered():
            return {"ok": True, "status": "not_registered"}

        r = self._run_subprocess([vrpathreg, "removedriver", ad_dir])
        record_path = Path(os.environ["LOCALAPPDATA"]) / "AnyaDance" / "registered_driver_path.txt"
        if record_path.exists():
            try:
                record_path.unlink()
            except OSError:
                pass
        backup = Path(os.environ["LOCALAPPDATA"]) / "AnyaDance" / "steamvr.vrsettings.backup"
        if backup.exists():
            try:
                backup.unlink()
            except OSError:
                pass
        return {"ok": r["ok"], "status": "unregistered" if r["ok"] else "error", "error": r.get("stderr", "")}

    async def start_anyadance(self) -> dict[str, Any]:
        if self.is_anyadance_running():
            return {"ok": True, "status": "already_running"}

        exe = self._anyadance_exe()
        if not exe:
            return {"ok": False, "error": "未找到 AnyaDance.exe"}
        if not self._is_driver_registered():
            reg = await self.register_driver()
            if not reg.get("ok") and reg.get("status") != "already_registered":
                return reg

        try:
            self._process = subprocess.Popen(
                [exe],
                cwd=str(Path(exe).parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.sleep(0.3)
            if self._process.poll() is not None:
                return {"ok": False, "error": f"AnyaDance.exe 启动失败，退出码: {self._process.returncode}"}
            self._running = True
            return {"ok": True, "status": "started", "pid": self._process.pid}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def stop_anyadance(self) -> dict[str, Any]:
        stopped = False
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
            stopped = True

        try:
            r = subprocess.run(
                ["taskkill", "/F", "/IM", "AnyaDance.exe"],
                capture_output=True, timeout=10,
            )
            if r.returncode == 0:
                stopped = True
        except Exception:
            pass

        self._process = None
        self._running = False
        return {"ok": True, "status": "stopped" if stopped else "not_running"}

    async def restart_steamvr(self) -> dict[str, Any]:
        for name in ["vrserver", "vrmonitor", "vrcompositor"]:
            try:
                subprocess.run(["taskkill", "/F", "/IM", f"{name}.exe"], capture_output=True, timeout=5)
            except Exception:
                pass
        await asyncio.sleep(1)
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "steam://run/250820"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return {"ok": True, "status": "restarting"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
