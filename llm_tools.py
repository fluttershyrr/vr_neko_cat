"""vr_neko_cat 插件：全部 LLM 工具方法。"""

from __future__ import annotations

from typing import Any
from plugin.sdk.plugin import NekoPluginBase as PluginBase, Ok, Err, ui, plugin_entry, llm_tool
from plugin.sdk.shared.i18n import tr


class VrLlmTools:
    """全部 @llm_tool 方法的 Mixin，与 VrNekoCatPlugin 组合使用。"""

    # ── 身体位姿控制 ──

    async def llm_vr_set_device_pose(self, **kwargs):
        await self._ensure_streaming("llm_vr_set_device_pose")
        r = await self.ui_api.set_device_pose(**kwargs)
        await self.udp_service.send()
        return {"image_url": "", "text":f"设备位姿已更新: {r}", "data": r}

    async def llm_vr_set_finger_bends(self, **kwargs):
        await self._ensure_streaming("llm_vr_set_finger_bends")
        r = await self.ui_api.set_finger_bends(**kwargs)
        await self.udp_service.send()
        return {"image_url": "", "text":f"手指弯曲已设置: {r}", "data": r}

    async def llm_vr_press_button(self, side: str = "right", button: str = "trigger_click", pressed: bool = True, **_):
        await self._ensure_streaming("llm_vr_press_button")
        r = await self.input_service.press_button(side=side, button=button, pressed=pressed)
        await self.udp_service.send()
        action_str = "按下" if pressed else "松开"
        return {"image_url": "", "text": f"已{action_str} {side} {button}"}

    async def llm_vr_set_joystick(self, side: str = "right", x: float = 0.0, y: float = 0.0, **_):
        await self._ensure_streaming("llm_vr_set_joystick")
        r = await self.input_service.set_joystick(side=side, x=x, y=y)
        await self.udp_service.send()
        txt = f"{side} 摇杆已设置为 ({x}, {y})"
        return {"image_url": "", "text": txt, "data": {"joystick": {"x": x, "y": y}}}

    async def llm_vr_hand_gesture(self, gesture_name: str = "idle", side: str | None = None, **_):
        await self._ensure_streaming("llm_vr_hand_gesture")
        if gesture_name == "fist":
            return {"image_url": "", "text": "已握拳（手指弯曲度 1.0）"}
        elif gesture_name == "open":
            return {"image_url": "", "text": "已张开手（手指弯曲度 0）"}
        elif gesture_name == "point":
            bends = {"thumb": 0.8, "index": 0.0, "middle": 0.8, "ring": 0.8, "pinky": 0.8}
            s = side or "right"
            await self.ui_api.set_finger_bends(side=s, **bends)
            await self.udp_service.send()
            return {"image_url": "", "text": f"{s} 手已做出指向手势（食指伸直）"}
        elif gesture_name == "rock":
            bends = {"thumb": 0.9, "index": 0.8, "middle": 0.3, "ring": 0.3, "pinky": 0.9}
            s = side or "right"
            await self.ui_api.set_finger_bends(side=s, **bends)
            await self.udp_service.send()
            return {"image_url": "", "text": f"{s} 手已做出摇滚手势 ✌️"}
        else:
            r = await self.animation_service.hand_gesture(gesture_name, side or "both")
            await self.udp_service.send()
            return {"image_url": "", "text": f"手势 '{gesture_name}' 已执行", "data": r}

    # ── 头部动作 ──

    async def llm_vr_nod(self, **_):
        await self._ensure_streaming("llm_vr_nod")
        r = await self.animation_service.nod_head()
        await self.udp_service.send()
        return {"image_url": "", "text":"点头完成 ✓", "data": r}

    async def llm_vr_tilt(self, direction: str = "left", amount: float = 15.0, **_):
        await self._ensure_streaming("llm_vr_tilt")
        r = await self.animation_service.tilt_head(direction, amount)
        await self.udp_service.send()
        return {"image_url": "", "text":f"向{direction}歪头 {amount}° 完成", "data": r}

    async def llm_vr_look_at(self, target: str = "", x: float = 0.0, y: float = 1.5, z: float = -3.0, **_):
        await self._ensure_streaming("llm_vr_look_at")
        r = await self.tracking_service.look_at(x, y, z)
        return {"image_url": "", "text": f"视线转向 {target or f'({x},{y},{z})'}", "data": r}

    async def llm_vr_wave(self, hand: str = "right", style: str = "hello", **_):
        await self._ensure_streaming("llm_vr_wave")
        r = await self.animation_service.wave_hand(hand, style)
        await self.udp_service.send()
        emoji = {"hello": "👋", "bye": "👋", "yes": "✅", "no": "❌", "peace": "✌️"}
        return {"image_url": "", "text": f"{hand}手{style}{emoji.get(style, '')}", "data": r}

    async def llm_vr_bow(self, depth: float = 30.0, **_):
        await self._ensure_streaming("llm_vr_bow")
        r = await self.animation_service.bow(depth)
        await self.udp_service.send()
        return {"image_url": "", "text":f"鞠躬 {depth}° 完成 🙇", "data": r}

    # ── 舞蹈 & 待机 ──

    async def llm_vr_play_dance(self, vmd_path: str = "", **_):
        await self._ensure_streaming("llm_vr_play_dance")
        path = vmd_path or self._config.get("dance_vmd_path", "")
        ok = await self.dance_service.play(path)
        if not ok:
            return Err(f"播放失败：VMD 文件不存在或格式错误 → {path}")
        return {"image_url": "", "text": f"💃 开始跳舞！\n文件: {path}\n提示: 用 stop_dance() 停止", "data": {"vmd_path": path, "playing": True}}

    async def llm_vr_stop_dance(self, **_):
        r = await self.dance_service.stop()
        return {"image_url": "", "text":"舞蹈已停止", "data": r}

    async def llm_vr_start_idle(self, **_):
        await self._ensure_streaming("llm_vr_start_idle")
        r = await self.animation_service.start_idle()
        return {"image_url": "", "text":"待机模式开启（呼吸+微晃）", "data": r}

    async def llm_vr_stop_idle(self, **_):
        r = await self.animation_service.stop_idle()
        return {"image_url": "", "text":"待机模式关闭", "data": r}

    async def llm_vr_start_tracking(self, x: float = 0.0, y: float = 1.5, z: float = -3.0, **_):
        await self._ensure_streaming("llm_vr_start_tracking")
        r = await self.tracking_service.start_tracking(x, y, z)
        return {"image_url": "", "text":f"追踪模式开启 (目标: {x}, {y}, {z})", "data": r}

    async def llm_vr_stop_tracking(self, **_):
        r = await self.tracking_service.stop_tracking()
        return {"image_url": "", "text":"追踪模式已关闭", "data": r}

    async def llm_vr_react_audio(self, level: float = 0.5, freq_band: str = "full", **_):
        await self._ensure_streaming("llm_vr_react_audio")
        r = await self.animation_service.react_to_audio(level, freq_band)
        await self.udp_service.send()
        band_names = {"full": "全频段", "low": "低频(贝斯)", "mid": "中频(人声)", "high": "高频(镲片)"}
        return {"image_url": "", "text":f"音频律动反应 (强度: {int(level*100)}% | 频段: {band_names.get(freq_band, freq_band)})", "data": r}

    # ── 表情 ──

    async def llm_vr_emotion(self, emotion: str = "happy", intensity: float = 0.7, **_):
        await self._ensure_streaming("llm_vr_emotion")
        valid = ["neutral", "happy", "sad", "angry", "surprised", "sleepy", "love"]
        if emotion.lower() not in [v.lower() for v in valid]:
            return Err(f"无效表情: {emotion}. 可用: {', '.join(valid)}")
        r = await self.animation_service.set_emotion(emotion, intensity)
        txt = f"表情切换为 {emotion}（强度 {int(intensity*100)}%）"
        return {"image_url": "", "text": txt, "data": {"emotion": emotion, "intensity": intensity}}

    # ── VRChat 交互 ──

    async def llm_vrc_menu(self, hand: str = "left", action: str = "open", **_):
        await self._ensure_streaming("llm_vrc_menu")
        if action == "open":
            await self.ui_api.vrc_left_menu(pressed=True) if hand == "left" else await self.ui_api.vrc_right_menu(pressed=True)
        elif action == "close":
            await self.ui_api.vrc_left_menu(pressed=False) if hand == "left" else await self.ui_api.vrc_right_menu(pressed=False)
        elif action == "select":
            await self.ui_api.vrc_select(side=hand)
        await self.udp_service.send()
        return {"image_url": "", "text": f"VRChat {hand}手菜单: {action}"}

    async def llm_vrc_gesture(self, gesture: str = "wave", **_):
        await self._ensure_streaming("llm_vrc_gesture")
        r = await self.ui_api.vrc_gesture(gesture)
        await self.udp_service.send()
        return {"image_url": "", "text":f"VRChat 快捷手势: {gesture}", "data": r}

    async def llm_vrc_drag(self, action: str = "start", hand: str = "right", duration: float = 2.0, **_):
        await self._ensure_streaming("llm_vrc_drag")
        if action == "start":
            await self.ui_api.vrc_drag_start(side=hand)
        elif action == "end":
            await self.ui_api.vrc_drag_end()
        else:
            await self.ui_api.vrc_drag_start(side=hand)
            await asyncio.sleep(min(max(duration, 0.1), 10.0))
            await self.ui_api.vrc_drag_end()
        await self.udp_service.send()
        return {"image_url": "", "text": f"拖拽: {action} ({hand})"}

    # ── 截图 ──

    async def llm_vision_capture(self, quality: int = -1, **_) -> dict[str, Any]:
        try:
            result = await self.screen_capture.capture_active_window(quality)
            if isinstance(result, dict) and result.get("ok"):
                b64 = result.get("image_base64", "")
                if not b64:
                    return {"image_url": "", "text": "截图失败：无图像数据", "data": {"ok": False}}
                return {
                    "image_url": f"data:image/jpeg;base64,{b64}",
                    "text": f"当前游戏画面 ({result.get('width',0)}x{result.get('height',0)}, {result.get('size_kb',0)}KB)",
                    "data": result,
                }
            return result or {"image_url": "", "text": "截图失败", "data": {"ok": False}}
        except Exception as e:
            return {"image_url": "", "text": f"截图异常: {e}", "data": {"ok": False}}

    async def llm_vision_face(self, quality: int = -1, **_) -> dict[str, Any]:
        try:
            result = await self.screen_capture.capture_game_region(
                left=960, top=200, width=400, height=450, quality=quality,
            )
            if isinstance(result, dict) and result.get("ok"):
                b64 = result.get("image_base64", "")
                if not b64:
                    return {"image_url": "", "text": "面部截图失败：无图像数据", "data": {"ok": False}}
                return {
                    "image_url": f"data:image/jpeg;base64,{b64}",
                    "text": f"VRChat 面部区域 ({result.get('width',0)}x{result.get('height',0)})",
                    "data": result,
                }
            return result or {"image_url": "", "text": "截图失败", "data": {"ok": False}}
        except Exception as e:
            return {"image_url": "", "text": f"截图异常: {e}", "data": {"ok": False}}

    async def llm_vision_config(self, **kwargs) -> dict[str, Any]:
        filtered = {k: v for k, v in kwargs.items() if v is not None}
        self.screen_capture.set_config(**filtered)
        return {"image_url": "", "text": f"视觉配置已更新: {list(filtered.keys())}"}
