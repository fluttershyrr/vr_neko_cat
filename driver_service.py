from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any


class VrDriverService:
    """SteamVR 驱动管理：注册/注销 AnyaDance 驱动 + SteamVR 重启。

    工作流程：
    1. 注册驱动到 SteamVR（一次性操作，通过 vrpathreg adddriver）
    2. 重启 SteamVR，驱动自动加载并监听 UDP 端口
    3. 通过 UDP 协议包控制 avatar 行为

    不需要手动启停 AnyaDance.exe——SteamVR 启动时会自动加载驱动。

    性能优化：
    - 驱动目录 / vrpathreg 路径在插件启动时扫描一次并持久化到配置；
    - 后续 get_driver_state 轮询直接从配置读取，不再重复扫描文件系统。
    """

    _PERSIST_KEY_DRIVER_DIR = "_persisted_driver_dir"
    _PERSIST_KEY_VRPATHREG = "_persisted_vrpathreg_path"

    def __init__(self, plugin: Any):
        self.plugin = plugin
        # 仅内存缓存，启动时从配置恢复或扫描一次
        self._driver_dir_cache: str = ""
        self._vrpathreg_cache: str = ""
        self._scanned_at_startup: bool = False

    @property
    def _config(self) -> dict[str, Any]:
        return self.plugin._config

    def _plugin_dir(self) -> Path:
        try:
            return Path(__file__).resolve().parent
        except Exception:
            return Path.cwd()

    # ────────── 启动时一次性扫描 ──────────

    async def ensure_startup_scan(self) -> None:
        """插件 startup 时调用一次：扫描驱动目录 & vrpathreg，写入配置持久化。"""
        if self._scanned_at_startup:
            return

        # 1. 扫描驱动目录
        driver_dir = self._do_scan_driver_dir()
        if driver_dir:
            self._driver_dir_cache = driver_dir
            self._config[self._PERSIST_KEY_DRIVER_DIR] = driver_dir
            self.plugin.logger.info(f"[driver] 启动扫描完成，驱动目录: {driver_dir}")
        else:
            # 尝试从旧持久化恢复
            cached = self._config.get(self._PERSIST_KEY_DRIVER_DIR, "")
            if cached:
                self._driver_dir_cache = str(cached)
                self.plugin.logger.info(f"[driver] 从配置恢复驱动目录: {cached}")
            else:
                self.plugin.logger.warning("[driver] 启动扫描未找到驱动目录，请在设置中配置 anyadance_path")

        # 2. 扫描 vrpathreg
        vrpathreg = self._do_scan_vrpathreg()
        if vrpathreg:
            self._vrpathreg_cache = vrpathreg
            self._config[self._PERSIST_KEY_VRPATHREG] = vrpathreg
        else:
            cached = self._config.get(self._PERSIST_KEY_VRPATHREG, "")
            if cached:
                self._vrpathreg_cache = str(cached)

        self._scanned_at_startup = True

    def _do_scan_driver_dir(self) -> str:
        """实际扫描一次驱动目录（不缓存，不写配置）。"""
        # 优先用户配置
        path = self._config.get("anyadance_path", "")
        if path and (Path(path) / "driver.vrdrivermanifest").exists():
            return str(Path(path).resolve())

        plugin_dir = self._plugin_dir()
        workspace_root = plugin_dir
        for _ in range(6):
            if (workspace_root / "anyadance").is_dir():
                break
            parent = workspace_root.parent
            if parent == workspace_root:
                break
            workspace_root = parent

        candidates = [
            plugin_dir / "anyadance",
            workspace_root / "anyadance",
            Path(os.environ.get("ANYADANCE_ROOT", "")),
            Path.cwd() / "anyadance",
        ]
        for d in candidates:
            if d and d.is_dir() and (d / "driver.vrdrivermanifest").exists():
                return str(d.resolve())

        return ""

    def _do_scan_vrpathreg(self) -> str:
        """实际扫描一次 vrpathreg.exe（不缓存）。"""
        steam_dirs = [
            Path(os.environ.get("STEAMVR_ROOT", "")),
            Path("C:/Program Files (x86)/Steam/steamapps/common/SteamVR"),
            Path("C:/Program Files/Steam/steamapps/common/SteamVR"),
            Path("D:/Steam/steamapps/common/SteamVR"),
            Path("D:/SteamLibrary/steamapps/common/SteamVR"),
            Path("E:/Steam/steamapps/common/SteamVR"),
            Path("E:/SteamLibrary/steamapps/common/SteamVR"),
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

    # ────────── 获取驱动目录（只读缓存/配置，不扫描） ──────────

    def _get_driver_dir(self) -> str:
        """获取驱动目录（优先内存缓存 → 持久化配置 → 不扫描文件系统）。"""
        if self._driver_dir_cache:
            return self._driver_dir_cache
        cached = self._config.get(self._PERSIST_KEY_DRIVER_DIR, "")
        if cached:
            self._driver_dir_cache = str(cached)
            return self._driver_dir_cache
        return ""

    def _get_vrpathreg(self) -> str:
        """获取 vrpathreg 路径（优先内存缓存 → 持久化配置）。"""
        if self._vrpathreg_cache:
            return self._vrpathreg_cache
        cached = self._config.get(self._PERSIST_KEY_VRPATHREG, "")
        if cached:
            self._vrpathreg_cache = str(cached)
            return self._vrpathreg_cache
        return ""

    def invalidate_cache(self) -> None:
        """清除缓存，强制下次从配置重新读取。注册/注销后调用。"""
        self._driver_dir_cache = ""
        self._vrpathreg_cache = ""

    def _read_openvr_paths(self) -> list[str]:
        """读取 openvrpaths.vrpath 中的 external_drivers 列表。"""
        openvr_paths = Path(os.environ.get("LOCALAPPDATA", "")) / "openvr" / "openvrpaths.vrpath"
        if not openvr_paths.exists():
            openvr_paths = Path.home() / "AppData" / "Local" / "openvr" / "openvrpaths.vrpath"
        if not openvr_paths.exists():
            return []
        try:
            with open(openvr_paths, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [str(Path(p).resolve()).lower() for p in (data.get("external_drivers") or []) if p]
        except Exception:
            return []

    # ────────── steamvr.vrsettings 管理（参考 register_driver.ps1） ──────────

    def _get_steamvr_settings_path(self) -> Path:
        """获取 steamvr.vrsettings 文件路径。"""
        openvr_paths = Path(os.environ.get("LOCALAPPDATA", "")) / "openvr" / "openvrpaths.vrpath"
        if not openvr_paths.exists():
            openvr_paths = Path.home() / "AppData" / "Local" / "openvr" / "openvrpaths.vrpath"
        if openvr_paths.exists():
            try:
                with open(openvr_paths, "r", encoding="utf-8") as f:
                    data = json.load(f)
                config_dirs = data.get("config")
                if config_dirs and len(config_dirs) > 0:
                    return Path(config_dirs[0]) / "steamvr.vrsettings"
            except Exception:
                pass
        return Path("C:/Program Files (x86)/Steam/config/steamvr.vrsettings")

    def _get_backup_dir(self) -> Path:
        """AnyaDance 备份目录（与 register_driver.ps1 一致）。"""
        return Path(os.environ.get("LOCALAPPDATA", "")) / "AnyaDance"

    def _get_backup_path(self) -> Path:
        """steamvr.vrsettings 备份文件路径。"""
        return self._get_backup_dir() / "steamvr.vrsettings.backup"

    def _get_registered_path_record(self) -> Path:
        """已注册驱动路径记录文件。"""
        return self._get_backup_dir() / "registered_driver_path.txt"

    async def _apply_virtual_mode_settings(self, driver_dir: str) -> bool:
        """写入 steamvr.vrsettings 中的全虚拟模式设置（参考 register_driver.ps1）。

        关键设置：
        - steamvr.forcedDriver = "anyadance"  → 强制使用 AnyaDance 作为主驱动
        - steamvr.activateMultipleDrivers = true
        - steamvr.requireHmd = true
        - driver_anyadance.enable / enable_hmd / enable_controllers / enable_trackers = true
        - power.turnOffScreensTimeout = 86400 → 防休眠
        - power.pauseCompositorOnStandby = false
        """
        settings_path = self._get_steamvr_settings_path()
        backup_path = self._get_backup_path()
        record_path = self._get_registered_path_record()

        backup_dir = self._get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)

        # 仅在无备份时备份原始设置（和 PS1 脚本行为一致）
        if settings_path.exists() and not backup_path.exists():
            try:
                import shutil
                shutil.copy2(str(settings_path), str(backup_path))
                self.plugin.logger.info(f"[driver] 备份 steamvr.vrsettings → {backup_path}")
            except Exception as e:
                self.plugin.logger.warning(f"[driver] 备份 steamvr.vrsettings 失败: {e}")

        # 读取现有设置
        settings: dict = {}
        if settings_path.exists():
            try:
                raw = settings_path.read_text(encoding="utf-8")
                settings = json.loads(raw)
                if not isinstance(settings, dict):
                    settings = {}
            except Exception:
                settings = {}

        # 写入 steamvr 段
        steamvr_section = settings.setdefault("steamvr", {})
        steamvr_section["activateMultipleDrivers"] = True
        steamvr_section["forcedDriver"] = "anyadance"
        steamvr_section["requireHmd"] = True

        # 写入 driver_anyadance 段
        driver_section = settings.setdefault("driver_anyadance", {})
        driver_section["enable"] = True
        driver_section["enable_hmd"] = True
        driver_section["enable_controllers"] = True
        driver_section["enable_trackers"] = True

        # 写入 power 段（防休眠，让 compositor 持续运行）
        power_section = settings.setdefault("power", {})
        power_section["turnOffScreensTimeout"] = 86400.0
        power_section["pauseCompositorOnStandby"] = False

        # 写回
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
            self.plugin.logger.info(f"[driver] 已写入全虚拟模式设置 → {settings_path}")
        except Exception as e:
            self.plugin.logger.error(f"[driver] 写入 steamvr.vrsettings 失败: {e}")
            return False

        # 记录已注册路径（供后续注销使用）
        try:
            record_path.write_text(driver_dir, encoding="utf-8")
        except Exception:
            pass

        return True

    async def _restore_virtual_mode_settings(self) -> bool:
        """恢复 steamvr.vrsettings 备份（参考 unregister_driver.ps1）。"""
        settings_path = self._get_steamvr_settings_path()
        backup_path = self._get_backup_path()
        record_path = self._get_registered_path_record()

        if backup_path.exists():
            try:
                import shutil
                shutil.copy2(str(backup_path), str(settings_path))
                backup_path.unlink()
                self.plugin.logger.info(f"[driver] 已从备份恢复 steamvr.vrsettings，并删除备份文件")
            except Exception as e:
                self.plugin.logger.warning(f"[driver] 恢复 steamvr.vrsettings 失败: {e}")
                return False
        else:
            self.plugin.logger.info("[driver] 无 steamvr.vrsettings 备份，跳过恢复")

        # 删除路径记录
        if record_path.exists():
            try:
                record_path.unlink()
            except Exception:
                pass

        return True


    # ────────── 以下为兼容别名（废弃，保留向后兼容） ──────────

    def _find_driver_dir(self, force: bool = False) -> str:
        """[废弃] 请使用 _get_driver_dir。保留以兼容旧调用。"""
        return self._get_driver_dir()

    def _find_vrpathreg(self) -> str:
        """[废弃] 请使用 _get_vrpathreg。保留以兼容旧调用。"""
        return self._get_vrpathreg()

    def _find_steam_root(self) -> str:
        for reg in [r"HKCU\Software\Valve\Steam", r"HKLM\SOFTWARE\WOW6432Node\Valve\Steam"]:
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER if "HKCU" in reg else winreg.HKEY_LOCAL_MACHINE,
                    reg.split("\\", 1)[1],
                )
                val, _ = winreg.QueryValueEx(key, "SteamPath")
                winreg.CloseKey(key)
                return str(val)
            except Exception:
                continue
        return str(Path("C:/Program Files (x86)/Steam"))

    def _run_subprocess(self, args: list[str], timeout: int = 15) -> dict[str, Any]:
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return {
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "stdout": "", "stderr": "Timeout", "code": -1}
        except FileNotFoundError:
            return {"ok": False, "stdout": "", "stderr": "Executable not found", "code": -1}

    def _is_driver_registered(self) -> bool:
        """检查驱动是否已注册（会执行 vrpathreg finddriver，但不会扫描目录）。"""
        vrpathreg = self._get_vrpathreg()
        if not vrpathreg:
            return False

        r = self._run_subprocess([vrpathreg, "finddriver", "anyadance"])
        out = (r.get("stdout") or "") + (r.get("stderr") or "")

        if r.get("ok"):
            return True

        # 兼容某些 SteamVR 版本：输出里包含驱动名/路径也视为已注册
        if out and "anyadance" in out.lower():
            return True

        driver_dir = self._get_driver_dir()
        if driver_dir and driver_dir in out:
            return True

        # 兜底：读取 openvrpaths.vrpath 的 external_drivers
        try:
            if driver_dir:
                registered_dirs = self._read_openvr_paths()
                if registered_dirs and str(Path(driver_dir).resolve()).lower() in registered_dirs:
                    return True
        except Exception:
            pass

        return False

    def get_driver_state(self) -> dict[str, Any]:
        """获取驱动状态（纯读缓存/配置，零文件系统扫描）。"""
        driver_dir = self._get_driver_dir()
        vrpathreg_found = bool(self._get_vrpathreg())
        registered = self._is_driver_registered() if driver_dir else False

        return {
            "driver_dir": driver_dir,
            "driver_found": bool(driver_dir),
            "vrpathreg_found": vrpathreg_found,
            "driver_registered": registered,
        }

    async def register_driver(self) -> dict[str, Any]:
        """向 SteamVR 注册 AnyaDance 驱动 + 写入全虚拟模式设置（参考 register_driver.ps1）。"""
        vrpathreg = self._get_vrpathreg()
        if not vrpathreg:
            return {"ok": False, "error": "未找到 SteamVR 安装目录，无法定位 vrpathreg.exe"}

        driver_dir = self._get_driver_dir()
        if not driver_dir:
            return {"ok": False, "error": "未找到 AnyaDance 驱动目录（需要包含 driver.vrdrivermanifest），请在设置中配置 anyadance_path"}

        if self._is_driver_registered():
            # 已注册也要确保 settings 正确（用户可能之前只注册了驱动没写 settings）
            await self._apply_virtual_mode_settings(driver_dir)
            return {"ok": True, "status": "already_registered"}

        r = self._run_subprocess([vrpathreg, "adddriver", driver_dir])
        self.invalidate_cache()
        if r["ok"]:
            self.plugin.logger.info(f"[driver] 驱动注册成功: {driver_dir}")
            # 写入全虚拟模式设置（关键：forcedDriver=anyadance 等）
            settings_ok = await self._apply_virtual_mode_settings(driver_dir)
            return {
                "ok": True,
                "status": "registered",
                "path": driver_dir,
                "settings_applied": settings_ok,
            }
        return {"ok": False, "error": r.get("stderr", "注册失败")}

    async def unregister_driver(self) -> dict[str, Any]:
        """从 SteamVR 注销 AnyaDance 驱动 + 恢复 steamvr.vrsettings 备份。"""
        vrpathreg = self._get_vrpathreg()
        if not vrpathreg:
            return {"ok": False, "error": "未找到 vrpathreg.exe"}

        driver_dir = self._get_driver_dir()
        if not driver_dir:
            return {"ok": False, "error": "未找到 AnyaDance 驱动目录"}

        if not self._is_driver_registered():
            # 即使未注册也尝试恢复 settings（可能残留）
            await self._restore_virtual_mode_settings()
            return {"ok": True, "status": "not_registered"}

        r = self._run_subprocess([vrpathreg, "removedriver", driver_dir])
        self.invalidate_cache()
        if r["ok"]:
            self.plugin.logger.info(f"[driver] 驱动注销成功: {driver_dir}")
        # 恢复 steamvr.vrsettings 备份
        settings_restored = await self._restore_virtual_mode_settings()
        return {
            "ok": r["ok"],
            "status": "unregistered" if r["ok"] else "error",
            "error": r.get("stderr", ""),
            "settings_restored": settings_restored,
        }


    async def restart_steamvr(self) -> dict[str, Any]:
        """强制停止并重新启动 SteamVR（注册驱动后需要重启才能生效）。"""
        for name in ["vrserver", "vrmonitor", "vrcompositor"]:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", f"{name}.exe"],
                    capture_output=True, timeout=5,
                )
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
