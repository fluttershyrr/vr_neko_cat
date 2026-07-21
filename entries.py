"""vr_neko_cat 插件：全部 plugin_entry 方法。"""

from __future__ import annotations

from typing import Any

import asyncio
from plugin.sdk.plugin import NekoPluginBase as PluginBase, Ok, Err, ui, plugin_entry
from plugin.sdk.shared.i18n import tr


class VrPluginEntries:
    """全部 @plugin_entry 方法的 Mixin，与 VrNekoCatPlugin 组合使用。"""

    # ── 设备位姿 ──

    async def set_device_pose(self, **kwargs):
        await self._ensure_streaming("set_device_pose")
        r = await self.ui_api.set_device_pose(**kwargs)
        await self.udp_service.send()
        return r

    async def set_finger_bends(self, **kwargs):
        await self._ensure_streaming("set_finger_bends")
        r = await self.ui_api.set_finger_bends(**kwargs)
        await self.udp_service.send()
        return r

    async def set_joystick(self, **kwargs):
        await self._ensure_streaming("set_joystick")
        r = await self.ui_api.set_joystick(**kwargs)
        await self.udp_service.send()
        return r

    async def press_button(self, **kwargs):
        await self._ensure_streaming("press_button")
        r = await self.ui_api.press_button(**kwargs)
        await self.udp_service.send()
        return r

    async def hand_gesture(self, **kwargs):
        await self._ensure_streaming("hand_gesture")
        r = await self.ui_api.hand_gesture(**kwargs)
        await self.udp_service.send()
        return r

    # ── 舞蹈 ──

    async def play_dance(self, vmd_path: str = "", **_):
        await self._ensure_streaming("play_dance")
        async with self._anim_lock:
            await self._stop_conflicting_modes(keep="dance")
        r = await self.ui_api.play_dance(vmd_path=vmd_path)
        self._notify_ai(f"开始播放舞蹈: {vmd_path}", priority=7)
        return r

    async def stop_dance(self, **_):
        r = await self.dance_service.stop()
        self._notify_ai("停止播放舞蹈", priority=7)
        return r

    async def mirror_hands(self, **_):
        await self._ensure_streaming("mirror_hands")
        r = await self.ui_api.mirror_hands()
        await self.udp_service.send()
        self._notify_ai("已切换左右手镜像", priority=7)
        return r

    async def set_emotion(self, emotion: str = "", intensity: float = 0.5, **_):
        await self._ensure_streaming("set_emotion")
        if not emotion:
            return Err("emotion 不能为空")
        r = await self.animation_service.set_emotion(emotion, intensity)
        self._notify_ai(f"表情切换为 {emotion}，强度 {intensity}", priority=7)
        return Ok(r)

    # ── 追踪 ──

    async def start_tracking(self, x: float = 0.0, y: float = 1.5, z: float = -3.0, **_):
        await self._ensure_streaming("start_tracking")
        async with self._anim_lock:
            await self._stop_conflicting_modes(keep="track")
        return await self.ui_api.start_tracking(x, y, z)

    async def stop_tracking(self, **_):
        return await self.ui_api.stop_tracking()

    async def set_tracking_smooth(self, factor: float = 0.3, **_):
        return await self.ui_api.set_tracking_smooth(factor)

    # ── 动画 ──

    async def look_at(self, x: float = 0.0, y: float = 1.5, z: float = -3.0, **_):
        await self._ensure_streaming("look_at")
        return await self.ui_api.look_at(x, y, z)

    async def nod_head(self, **_):
        await self._ensure_streaming("nod_head")
        r = await self.animation_service.nod_head()
        await self.udp_service.send()
        return Ok(r)

    async def tilt_head(self, direction: str = "left", **_):
        await self._ensure_streaming("tilt_head")
        r = await self.animation_service.tilt_head(direction)
        await self.udp_service.send()
        return Ok(r)

    async def wave_hand(self, side: str = "right", style: str = "hello", **_):
        await self._ensure_streaming("wave_hand")
        r = await self.animation_service.wave_hand(side, style)
        await self.udp_service.send()
        return Ok(r)

    async def bow(self, depth: float = 30.0, **_):
        await self._ensure_streaming("bow")
        r = await self.animation_service.bow(depth)
        await self.udp_service.send()
        return Ok(r)

    async def start_idle(self, **_):
        await self._ensure_streaming("start_idle")
        async with self._anim_lock:
            await self._stop_conflicting_modes(keep="idle")
        return await self.ui_api.start_idle()

    async def stop_idle(self, **_):
        return await self.ui_api.stop_idle()

    async def react_to_audio(self, level: float = 0.5, freq_band: str = "full", **_):
        await self._ensure_streaming("react_to_audio")
        r = await self.animation_service.react_to_audio(level, freq_band)
        await self.udp_service.send()
        return Ok(r)

    # ── 视觉截图 ──

    async def vision_capture(self, quality: int = -1, **_) -> dict[str, Any]:
        try:
            result = await self.screen_capture.capture_active_window(quality)
            if isinstance(result, dict) and result.get("ok"):
                b64 = result.get("image_base64", "")
                if not b64:
                    return {"ok": False, "error": "无图像数据"}
                return {
                    "ok": True,
                    "image_base64": b64,
                    "preview": f"data:image/jpeg;base64,{b64}",
                    "width": result.get("width", 0),
                    "height": result.get("height", 0),
                    "size_kb": result.get("size_kb", 0),
                }
            return result or {"ok": False}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def vision_face(self, quality: int = -1, **_) -> dict[str, Any]:
        try:
            result = await self.screen_capture.capture_game_region(
                left=960, top=200, width=400, height=450, quality=quality
            )
            if isinstance(result, dict) and result.get("ok"):
                b64 = result.get("image_base64", "")
                if not b64:
                    return {"ok": False, "error": "无图像数据"}
                return {
                    "ok": True,
                    "image_base64": b64,
                    "preview": f"data:image/jpeg;base64,{b64}",
                    "width": result.get("width", 0),
                    "height": result.get("height", 0),
                }
            return result or {"ok": False, "error": "截图失败"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def vision_config(self, **kwargs) -> dict[str, Any]:
        filtered = {k: v for k, v in kwargs.items() if v is not None}
        self.screen_capture.set_config(**filtered)
        return Ok({"config_updated": True})

    # ── VRChat 专用操作 ──

    async def vrc_gesture(self, name: str = "", **_):
        await self._ensure_streaming("vrc_gesture")
        r = await self.ui_api.vrc_gesture(name)
        await self.udp_service.send()
        self._notify_ai(f"执行 VRChat 手势: {name}", priority=7)
        return r

    async def vrc_left_menu(self, pressed: bool = True, **_):
        await self._ensure_streaming("vrc_left_menu")
        r = await self.ui_api.vrc_left_menu(pressed)
        await self.udp_service.send()
        return r

    async def vrc_right_menu(self, pressed: bool = True, **_):
        await self._ensure_streaming("vrc_right_menu")
        r = await self.ui_api.vrc_right_menu(pressed)
        await self.udp_service.send()
        return r

    async def vrc_select(self, side: str = "right", pressed: bool = True, **_):
        await self._ensure_streaming("vrc_select")
        r = await self.ui_api.vrc_select(side, pressed)
        await self.udp_service.send()
        return r

    async def vrc_drag_start(self, side: str = "right", **_):
        await self._ensure_streaming("vrc_drag_start")
        r = await self.ui_api.vrc_drag_start(side)
        await self.udp_service.send()
        self._notify_ai(f"开始拖拽 ({side})", priority=7)
        return r

    async def vrc_drag_end(self, **_):
        await self._ensure_streaming("vrc_drag_end")
        r = await self.ui_api.vrc_drag_end()
        await self.udp_service.send()
        self._notify_ai("结束拖拽", priority=7)
        return r

    async def vrc_available_gestures(self, **_):
        return Ok(list(self.animation_service.GESTURE_MAP.keys()))

    # ── 状态查询 & 辅助 ──

    async def get_dashboard_state(self, **_):
        return Ok(await self.dashboard_service.build_dashboard_state())

    async def save_settings(self, **kwargs):
        return Ok(await self.dashboard_service.save_settings(**kwargs))

    async def load_settings(self, **_):
        return Ok(await self.config_service.load())

    async def get_driver_state(self, **_):
        return Ok(self.driver_service.get_driver_state())

    async def register_driver(self, **kwargs):
        r = await self.driver_service.register_driver()
        self._notify_ai("驱动注册完成", priority=8)
        return Ok(r)

    async def unregister_driver(self, **_):
        r = await self.driver_service.unregister_driver()
        self._notify_ai("驱动已注销", priority=8)
        return Ok(r)

    async def restart_steamvr(self, **_):
        svr = await self.driver_service.restart_steamvr()
        self._notify_ai("SteamVR 已重启", priority=8)
        return Ok(svr)

    async def driver_oneclick(self, **_):
        """一键启动：注册驱动 → 重启SteamVR → 流送（与老版本 __init__.py 一致）"""
        reg = await self.driver_service.register_driver()

        if not reg.get("ok") and reg.get("status") != "already_registered":
            return Err(f"驱动注册失败: {reg.get('error', 'unknown')}")

        await asyncio.sleep(0.5)
        actually_registered = self.driver_service.get_driver_state().get("driver_registered", False)

        svr = await self.driver_service.restart_steamvr()

        if actually_registered:
            self._notify_ai("一键启动完成: 驱动已注册 → SteamVR 重启中", priority=8)
        else:
            self._notify_ai("一键启动已执行，但驱动状态未确认", priority=6)

        return Ok({
            "ok": True, "status": "done",
            "registered": actually_registered,
            "steps": {"register": reg, "restart_steamvr": svr}
        })

    async def screen_capture_config(self, **kwargs):
        return Ok(self.screen_capture.set_config(**{k: v for k, v in kwargs.items() if v is not None}))
