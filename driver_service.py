from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any


class VrDriverService:
    
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

        plugin_dir = self._plugin_dir()
        
        self.plugin.logger.info(f"[driver] 开始扫描驱动目录...")
        self.plugin.logger.info(f"[driver] plugin_dir = {plugin_dir}")
        self.plugin.logger.info(f"[dir] cwd = {Path.cwd()}")
        self.plugin.logger.info(f"[env] ANYADANCE_ROOT = {os.environ.get('ANYADANCE_ROOT', '(未设置)')}")
        self.plugin.logger.info(f"[env] STEAMVR_ROOT = {os.environ.get('STEAMVR_ROOT', '(未设置)')}")

        # ── 策略1: 用户配置 ──
        path = self._config.get("anyadance_path", "")
        if path:
            p = Path(path)
            manifest = p / "driver.vrdrivermanifest"
            self.plugin.logger.debug(f"[driver] 检查 anyadance_path: {path}")
            if manifest.exists():
                resolved = str(p.resolve())
                self.plugin.logger.info(f"[driver] ✓ 配置 anyadance_path 有效: {resolved} (manifest={manifest})")
                return resolved
            else:
                self.plugin.logger.warning(
                    f"[driver] ✗ 配置的 anyadance_path 无效 (manifest不存在): {path}"
                    f"\n  实际: path exists={p.is_dir()}, manifest exists={manifest.exists()}"
                )

        # ── 策略2: 环境变量 ──
        env_root = os.environ.get("ANYADANCE_ROOT", "").strip()
        if env_root:
            env_path = Path(env_root)
            manifest = env_path / "driver.vrdrivermanifest"
            self.plugin.logger.debug(f"[driver] 检查 ANYADANCE_ROOT: {env_root}")
            if manifest.exists():
                resolved = str(env_path.resolve())
                self.plugin.logger.info(f"[driver] ✓ ANYADANCE_ROOT 有效: {resolved}")
                return resolved

        # ── 策略3: 从 plugin_dir 向上逐级搜索 anyadance/ ──
        search_start = plugin_dir
        for depth in range(10):
            candidate = search_start / "anyadance"
            manifest = candidate / "driver.vrdrivermanifest"
            self.plugin.logger.debug(f"[driver] 向上搜索 depth={depth}: {candidate}")
            
            if candidate.is_dir() and manifest.exists():
                resolved = str(candidate.resolve())
                self.plugin.logger.info(f"[driver] ✓ 在 {depth} 层父目录找到: {resolved}")
                return resolved
            
            # 继续向上
            parent = search_start.parent
            if parent == search_start or not parent.exists():
                self.plugin.logger.debug(f"[driver] 到达根目录，停止向上搜索")
                break
            search_start = parent

        # ── 策略4: 当前工作目录 ──
        cwd_candidate = Path.cwd() / "anyadance"
        if (cwd_candidate / "driver.vrdrivermanifest").exists():
            resolved = str(cwd_candidate.resolve())
            self.plugin.logger.info(f"[driver] ✓ CWD 下找到: {resolved}")
            return resolved

        # ── 全部失败 ──
        # 列出实际存在的候选目录供调试
        debug_dirs = []
        for d in [plugin_dir, Path.cwd(), Path(os.environ.get("ANYADANCE_ROOT", ""))]:
            ad = d / "anyadance" if d else None
            if ad and ad.exists():
                has_manifest = (ad / "driver.vrdrivermanifest").exists()
                debug_dirs.append(f"  - {ad} (is_dir=True, manifest={has_manifest})")
            elif d and d.exists():
                children = [str(c.name) for c in d.iterdir() if c.is_dir()]
                debug_dirs.append(f"  - {d}/anyadance 不存在, 子目录: {children[:15]}")

        self.plugin.logger.warning(
            f"[driver] ✗ 未找到 anyadance 驱动目录!\n"
            f"  已检查位置:\n"
            + ("\n".join(debug_dirs) if debug_dirs else "    无可检查目录\n")
            + f"\n  解决方案:\n"
            f"  1) 确保 anyadance 文件夹在插件目录下或上级目录\n"
            f"  2) 设置环境变量 ANYADANCE_ROOT=驱动目录绝对路径\n"
            f"  3) 在设置中手动配置 anyadance_path"
        )
        return ""

    def _do_scan_vrpathreg(self) -> str:
        """扫描 vrpathreg.exe（动态搜索，优先环境变量和注册表）。

        搜索策略：
        1. 环境变量 STEAMVR_ROOT
        2. Windows 注册表 Steam 安装路径 → steamapps/common/SteamVR/bin/win64/vrpathreg.exe
        3. 系统 PATH (where 命令)
        """
        self.plugin.logger.info(f"[driver] 开始扫描 vrpathreg...")

        # ── 策略1: 环境变量 ──
        env_root = os.environ.get("STEAMVR_ROOT", "").strip()
        if env_root:
            p = Path(env_root) / "bin" / "win64" / "vrpathreg.exe"
            if p.exists():
                self.plugin.logger.info(f"[driver] ✓ STEAMVR_ROOT: {p}")
                return str(p)

        # ── 策略2: Windows 注册表 ──
        try:
            import winreg
            
            # 尝试多个注册表路径（兼容不同安装方式）
            reg_paths = [
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            ]
            
            for hkey, subkey in reg_paths:
                try:
                    key = winreg.OpenKey(hkey, subkey)
                    val, _ = winreg.QueryValueEx(key, "SteamPath")
                    winreg.CloseKey(key)
                    
                    if val:
                        steam_path = Path(val).resolve()
                        p = steam_path / "steamapps" / "common" / "SteamVR" / "bin" / "win64" / "vrpathreg.exe"
                        if p.exists():
                            resolved = str(p)
                            self.plugin.logger.info(f"[driver] ✓ 从注册表找到 Steam 安装: {resolved}")
                            return resolved
                        else:
                            self.plugin.logger.debug(f"[driver] Steam 路径存在但无 vrpathreg: {p}")
                except (FileNotFoundError, OSError):
                    continue
                    
        except ImportError:
            self.plugin.logger.debug("[driver] winreg 模块不可用 (非Windows?)")
        except Exception as e:
            self.plugin.logger.debug(f"[driver] 注册表查询失败: {e}")

        # ── 策略3: 系统 PATH ──
        try:
            result = subprocess.run(
                ["where", "vrpathreg"],
                capture_output=True,
                text=True,
                timeout=5,
                env={**os.environ, "PATH": os.environ.get("PATH", "")}
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip().splitlines()[0].strip()
                if Path(path).exists():
                    self.plugin.logger.info(f"[driver] ✓ 从 PATH 找到: {path}")
                    return path
        except Exception as e:
            self.plugin.logger.debug(f"[driver] where 命令失败: {e}")

        # ── 全部失败 ──
        self.plugin.logger.warning(
            f"[driver] ✗ 未找到 vrpathreg.exe\n"
            f"  解决方案:\n"
            f"  1) 设置 STEAMVR_ROOT=C:\\你的\\SteamVR\\目录\n"
            f"  2) 确保 SteamVR 已正确安装\n"
            f"  3) 将 vrpathreg.exe 所在目录添加到系统 PATH"
        )
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
        """获取 steamvr.vrsettings 文件路径（优先从 openvrpaths.vrpath 或注册表动态获取）。"""
        # ── 策略1: 从 openvrpaths.vrpath 获取 config 目录 ──
        for candidate in [
            Path(os.environ.get("LOCALAPPDATA", "")) / "openvr" / "openvrpaths.vrpath",
            Path.home() / "AppData" / "Local" / "openvr" / "openvrpaths.vrpath",
        ]:
            if not candidate.exists():
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                config_dirs = data.get("config")
                if config_dirs and len(config_dirs) > 0:
                    return Path(config_dirs[0]) / "steamvr.vrsettings"
            except Exception:
                continue

        # ── 策略2: 从 Windows 注册表 SteamPath 推导 ──
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            ]
            for hkey, subkey in reg_paths:
                try:
                    key = winreg.OpenKey(hkey, subkey)
                    val, _ = winreg.QueryValueEx(key, "SteamPath")
                    winreg.CloseKey(key)
                    if val:
                        return Path(val) / "config" / "steamvr.vrsettings"
                except (FileNotFoundError, OSError):
                    continue
        except ImportError:
            pass
        except Exception:
            pass

        # ── 策略3: 兜底（仅用于极端情况，此时大概率无法正常工作） ──
        self.plugin.logger.warning(
            "[driver] 无法从 openvrpaths 或注册表确定 steamvr.vrsettings 路径"
        )
        return Path.home() / "AppData" / "Local" / "openvr" / "steamvr.vrsettings"

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
        """强制停止并重新启动 SteamVR（注册驱动后需要重启才能生效）。
        
        注意：必须使用异步方式避免阻塞事件循环，否则会导致 UDP 流送中断 → SteamVR 崩溃。
        """
        # 异步终止 SteamVR 进程（不阻塞事件循环）
        for name in ["vrserver", "vrmonitor", "vrcompositor"]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "taskkill", "/F", "/IM", f"{name}.exe",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            except Exception:
                pass
        
        # 给进程清理时间
        await asyncio.sleep(0.5)
        
        # 启动 SteamVR
        try:
            proc = await asyncio.create_subprocess_exec(
                "cmd", "/c", "start", "steam://run/250820",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # 不等待完成，让 SteamVR 后台启动
            return {"ok": True, "status": "restarting"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
