from __future__ import annotations

import asyncio
from typing import Any

from plugin.sdk.plugin import (
    NekoPluginBase, lifecycle, llm_tool, neko_plugin, plugin_entry, tr, ui, Ok,
)

from .config_service import VrConfigService
from .udp_service import VrUdpService
from .pose_service import VrPoseService
from .input_service import VrInputService
from .dance_service import VrDanceService
from .emotion_service import VrEmotionService
from .tracking_service import VrTrackingService
from .animation_service import VrAnimationService
from .vision_bridge import VrVisionBridge
from .vrchat_service import VrChatService
from .dashboard_service import VrDashboardService
from .driver_service import VrDriverService
from .screen_capture_service import VrScreenCapture
from .ui_api import VrUiApi


@neko_plugin
class VRControllerPlugin(NekoPluginBase):
    """VR N.E.K.O.cat — UDP → AnyaDance → SteamVR → VRChat 全功能插件"""

    STREAM_RATE_HZ = 60

    def __init__(self, ctx):
        super().__init__(ctx)
        self.logger = self.enable_file_logging(log_level="INFO")

        self.config_service = VrConfigService(self.data_path())
        self._config: dict[str, Any] = self.config_service.default_config()

        self.udp_service = VrUdpService(self)
        self.pose_service = VrPoseService(self)
        self.input_service = VrInputService(self)
        self.dance_service = VrDanceService(self)
        self.emotion_service = VrEmotionService(self)
        self.tracking_service = VrTrackingService(self)
        self.animation_service = VrAnimationService(self)
        self.vision_bridge = VrVisionBridge(self)
        self.vrchat_service = VrChatService(self)
        self.dashboard_service = VrDashboardService(self)
        self.driver_service = VrDriverService(self)
        self.screen_capture = VrScreenCapture(self)
        self.ui_api = VrUiApi(self)

        self._streaming = False
        self._stream_task: asyncio.Task | None = None
        self._loop = asyncio.get_event_loop()

    async def _stream_loop(self) -> None:
        """60Hz UDP 位姿流送主循环，不断将当前配置中的设备位姿/输入发送到 AnyaDance。"""
        interval = 1.0 / max(1.0, self.STREAM_RATE_HZ)
        while self._streaming:
            await self.udp_service.send()
            await asyncio.sleep(interval)

    def _notify_ai(self, text: str, priority: int = 5, respond: bool = True) -> None:
        """向 N.E.K.O 消息总线推送通知，让 AI 感知 VR 操作结果。"""
        self.push_message(
            source=self.plugin_id,
            visibility=[],
            ai_behavior="respond" if respond else "read",
            parts=[{"type": "text", "text": f"[VR N.E.K.O.cat] {text}"}],
            priority=priority,
        )

    @lifecycle(id="startup")
    async def startup(self, **_):
        self._config = await self.config_service.load()
        self.register_static_ui("static")
        self.set_list_actions([{
            "id": "open_ui",
            "label": self.i18n.t("ui.actions.open", default="打开控制面板"),
            "kind": "ui",
            "target": f"/plugin/{self.plugin_id}/ui/",
            "open_in": "new_tab",
        }])
        self.emotion_service.capture_baseline()
        return Ok({"status": "ready"})

    @lifecycle(id="shutdown")
    async def shutdown(self, **_):
        self._streaming = False
        if self._stream_task:
            self._stream_task.cancel()
        await self.dance_service.stop()
        await self.tracking_service.stop_tracking()
        await self.animation_service.stop_all()
        await self.vision_bridge.stop_auto_look()
        self.vrchat_service.stop_locomotion()
        self.udp_service.close()
        await self.driver_service.stop_anyadance()
        return Ok({"status": "shutdown"})

    @ui.context(id="dashboard")
    async def get_dashboard_context(self):
        return await self.dashboard_service.build_dashboard_context()

    @ui.action(id="open_ui", label=tr("ui.actions.open", default="打开控制面板"))
    async def open_ui(self, **_):
        return await self.dashboard_service.open_ui()

    # ──────────────────── 流送 ────────────────────

    @ui.action(id="start_stream", label=tr("actions.start_stream", default="开始流送"), refresh_context=True)
    @plugin_entry(id="start_stream", name=tr("entries.start_stream.name", default="开始 UDP 流送"), description=tr("entries.start_stream.description", default="以 60Hz 向 AnyaDance 发送 UDP 位姿数据包，驱动 VRChat FBT"))
    async def start_stream(self, **_): return await self.ui_api.start_stream()

    @ui.action(id="stop_stream", label=tr("actions.stop_stream", default="停止流送"), refresh_context=True)
    @plugin_entry(id="stop_stream", name=tr("entries.stop_stream.name", default="停止 UDP 流送"), description=tr("entries.stop_stream.description", default="停止 UDP 数据包发送"))
    async def stop_stream(self, **_): return await self.ui_api.stop_stream()

    # ──────────────────── 预设位姿 ────────────────────

    @ui.action(id="apply_preset", label=tr("actions.apply_preset", default="应用预设"), refresh_context=True)
    @plugin_entry(id="apply_preset", name=tr("entries.apply_preset.name", default="应用预设位姿"), description=tr("entries.apply_preset.description", default="VRChat FBT 预设位姿"), input_schema={"type": "object", "properties": {"preset": {"type": "string", "enum": ["standing", "t_pose", "menu"], "default": "standing"}}})
    async def apply_preset(self, preset: str = "standing", **_): return await self.ui_api.apply_preset(preset)

    @plugin_entry(id="set_device_pose", name=tr("entries.set_device_pose.name", default="设置设备位姿"), description=tr("entries.set_device_pose.description", default="设置 VRChat tracker 的 3D 位置和四元数旋转"), input_schema={"type": "object", "properties": {"device": {"type": "string", "enum": ["hmd", "left_controller", "right_controller", "hip", "left_foot", "right_foot"]}, "position_x": {"type": "number"}, "position_y": {"type": "number"}, "position_z": {"type": "number"}, "rotation_x": {"type": "number"}, "rotation_y": {"type": "number"}, "rotation_z": {"type": "number"}, "rotation_w": {"type": "number"}}, "required": ["device"]})
    async def set_device_pose(self, device: str = "", **kwargs): return await self.ui_api.set_device_pose(device=device, **kwargs)

    # ──────────────────── 手指/摇杆/按键/手势 ────────────────────

    @plugin_entry(id="set_finger_bends", name=tr("entries.set_finger_bends.name", default="设置手指弯曲"), description=tr("entries.set_finger_bends.description", default="设置手指弯曲值，驱动 VRChat Index 骨骼手势 (0=伸直, 1=弯曲)"), input_schema={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"]}, "thumb": {"type": "number"}, "index": {"type": "number"}, "middle": {"type": "number"}, "ring": {"type": "number"}, "pinky": {"type": "number"}}, "required": ["side"]})
    async def set_finger_bends(self, side: str = "left", **kwargs): return await self.ui_api.set_finger_bends(side=side, **kwargs)

    @plugin_entry(id="set_joystick", name=tr("entries.set_joystick.name", default="设置摇杆"), description=tr("entries.set_joystick.description", default="VRChat 移动摇杆 X/Y 值"), input_schema={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"]}, "x": {"type": "number"}, "y": {"type": "number"}}, "required": ["side"]})
    async def set_joystick(self, side: str = "left", x: float = 0.0, y: float = 0.0, **_): return await self.ui_api.set_joystick(side=side, x=x, y=y)

    @plugin_entry(id="press_button", name=tr("entries.press_button.name", default="按键"), description=tr("entries.press_button.description", default="VRChat 控制器按键 (trigger/menu/grip/a/b)"), input_schema={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"]}, "button": {"type": "string", "enum": ["trigger_click", "menu_click", "system_click", "a_click", "b_click", "grip_click"]}, "pressed": {"type": "boolean", "default": True}}, "required": ["side", "button"]})
    async def press_button(self, side: str = "left", button: str = "", pressed: bool = True, **_): return await self.ui_api.press_button(side=side, button=button, pressed=pressed)

    @plugin_entry(id="hand_gesture", name=tr("entries.hand_gesture.name", default="手部手势"), description=tr("entries.hand_gesture.description", default="VRChat Index 标准手势"), input_schema={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"]}, "gesture": {"type": "string", "enum": ["open", "fist", "point", "peace", "thumbs_up", "rock", "gun"]}}, "required": ["side", "gesture"]})
    async def hand_gesture(self, side: str = "left", gesture: str = "open", **_):
        r = await self.ui_api.hand_gesture(side=side, gesture=gesture)
        self._notify_ai(f"{'右手' if side == 'right' else '左手'}做出了 {gesture} 手势")
        return r

    # ──────────────────── 舞蹈 ────────────────────

    @plugin_entry(id="play_dance", name=tr("entries.play_dance.name", default="播放舞蹈"), description=tr("entries.play_dance.description", default="加载 VMD 并驱动 VRChat 模型跳舞"), input_schema={"type": "object", "properties": {"vmd_path": {"type": "string"}}})
    async def play_dance(self, vmd_path: str = "", **_):
        r = await self.ui_api.play_dance(vmd_path=vmd_path)
        self._notify_ai(f"开始播放舞蹈: {vmd_path}", priority=7)
        return r

    @plugin_entry(id="stop_dance", name=tr("entries.stop_dance.name", default="停止舞蹈"), description=tr("entries.stop_dance.description", default="停止 VRChat 舞蹈"))
    async def stop_dance(self, **_):
        r = await self.ui_api.stop_dance()
        self._notify_ai("舞蹈已停止")
        return r

    # ──────────────────── 镜像 ────────────────────

    @plugin_entry(id="mirror_hands", name=tr("entries.mirror_hands.name", default="镜像手部"), description=tr("entries.mirror_hands.description", default="左手→右手 VRChat 位姿镜像"))
    async def mirror_hands_entry(self, enabled: bool = True, **_): return await self.ui_api.mirror_hands(enabled=enabled)

    @plugin_entry(id="mirror_feet", name=tr("entries.mirror_feet.name", default="镜像脚部"), description=tr("entries.mirror_feet.description", default="左脚→右脚 VRChat 位姿镜像"))
    async def mirror_feet_entry(self, enabled: bool = True, **_): return await self.ui_api.mirror_feet(enabled=enabled)

    # ──────────────────── 情感 ────────────────────

    @ui.action(id="set_emotion", label=tr("actions.set_emotion", default="设置情感"), refresh_context=True)
    @plugin_entry(id="set_emotion", name=tr("entries.set_emotion.name", default="设置情感"), description=tr("entries.set_emotion.description", default="VRChat 角色情感→全身姿态 (12种)"), input_schema={"type": "object", "properties": {"emotion": {"type": "string", "enum": ["happy", "sad", "angry", "surprised", "scared", "excited", "shy", "confident", "relaxed", "curious", "tired", "neutral"], "default": "neutral"}, "intensity": {"type": "number", "default": 1.0, "minimum": 0.0, "maximum": 1.0}}})
    async def set_emotion(self, emotion: str = "neutral", intensity: float = 1.0, **_):
        r = await self.ui_api.set_emotion(emotion, intensity)
        self._notify_ai(f"情感切换为 {emotion}，强度 {intensity:.0%}", priority=6)
        return r

    @plugin_entry(id="blend_emotions", name=tr("entries.blend_emotions.name", default="混合情感"), description=tr("entries.blend_emotions.description", default="VRChat 双情感混合"), input_schema={"type": "object", "properties": {"emotion_a": {"type": "string"}, "emotion_b": {"type": "string"}, "ratio": {"type": "number", "default": 0.5, "minimum": 0.0, "maximum": 1.0}}})
    async def blend_emotions(self, emotion_a: str = "neutral", emotion_b: str = "happy", ratio: float = 0.5, **_):
        r = await self.ui_api.blend_emotions(emotion_a, emotion_b, ratio)
        self._notify_ai(f"情感混合 {emotion_a}{ratio:.0%}+{emotion_b}{1-ratio:.0%}")
        return r

    @plugin_entry(id="capture_baseline", name=tr("entries.capture_baseline.name", default="捕获基准位姿"), description=tr("entries.capture_baseline.description", default="捕获当前 VRChat 位姿为情感基准"))
    async def capture_baseline(self, **_): return await self.ui_api.capture_baseline()

    # ──────────────────── 追踪 ────────────────────

    @plugin_entry(id="look_at", name=tr("entries.look_at.name", default="注视目标"), description=tr("entries.look_at.description", default="VRChat HMD 平滑注视世界坐标"), input_schema={"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number", "default": 1.5}, "z": {"type": "number"}, "smooth": {"type": "number", "default": -1}}})
    async def look_at(self, x: float = 0.0, y: float = 1.5, z: float = -3.0, smooth: float = -1.0, **_): return await self.ui_api.look_at(x, y, z, smooth)

    @plugin_entry(id="look_at_direction", name=tr("entries.look_at_direction.name", default="朝向角度"), description=tr("entries.look_at_direction.description", default="HMD Yaw/Pitch 角度"), input_schema={"type": "object", "properties": {"yaw": {"type": "number"}, "pitch": {"type": "number", "default": 0.0}, "smooth": {"type": "number", "default": -1}}})
    async def look_at_direction(self, yaw: float = 0.0, pitch: float = 0.0, smooth: float = -1.0, **_): return await self.ui_api.look_at_direction(yaw, pitch, smooth)

    @ui.action(id="reset_head", label=tr("actions.reset_head", default="重置头部"), refresh_context=True)
    @plugin_entry(id="reset_head", name=tr("entries.reset_head.name", default="重置头部朝向"), description=tr("entries.reset_head.description", default="VRChat HMD 旋转归零"))
    async def reset_head(self, **_): return await self.ui_api.reset_head()

    @plugin_entry(id="start_tracking", name=tr("entries.start_tracking.name", default="开始追踪"), description=tr("entries.start_tracking.description", default="60Hz 持续追踪 VRChat 目标"), input_schema={"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number", "default": 1.5}, "z": {"type": "number"}}})
    async def start_tracking(self, x: float = 0.0, y: float = 1.5, z: float = -3.0, **_): return await self.ui_api.start_tracking(x, y, z)

    @plugin_entry(id="stop_tracking", name=tr("entries.stop_tracking.name", default="停止追踪"), description=tr("entries.stop_tracking.description", default="停止持续追踪"))
    async def stop_tracking(self, **_): return await self.ui_api.stop_tracking()

    @plugin_entry(id="set_tracking_smooth", name=tr("entries.set_tracking_smooth.name", default="追踪平滑度"), description=tr("entries.set_tracking_smooth.description", default="注视平滑插值"), input_schema={"type": "object", "properties": {"factor": {"type": "number", "default": 0.12, "minimum": 0.01, "maximum": 1.0}}})
    async def set_tracking_smooth(self, factor: float = 0.12, **_): return await self.ui_api.set_tracking_smooth(factor)

    # ──────────────────── 动画 ────────────────────

    @ui.action(id="nod_head", label=tr("actions.nod_head", default="点头"), refresh_context=True)
    @plugin_entry(id="nod_head", name=tr("entries.nod_head.name", default="点头"), description=tr("entries.nod_head.description", default="VRChat 模型点头"), input_schema={"type": "object", "properties": {"count": {"type": "integer", "default": 1}, "speed": {"type": "number", "default": 1.0}}})
    async def nod_head(self, count: int = 1, speed: float = 1.0, **_): return await self.ui_api.do_nod_head(count, speed)

    @ui.action(id="shake_head", label=tr("actions.shake_head", default="摇头"), refresh_context=True)
    @plugin_entry(id="shake_head", name=tr("entries.shake_head.name", default="摇头"), description=tr("entries.shake_head.description", default="VRChat 模型摇头"), input_schema={"type": "object", "properties": {"count": {"type": "integer", "default": 1}, "speed": {"type": "number", "default": 1.0}}})
    async def shake_head(self, count: int = 1, speed: float = 1.0, **_): return await self.ui_api.do_shake_head(count, speed)

    @plugin_entry(id="tilt_head", name=tr("entries.tilt_head.name", default="歪头"), description=tr("entries.tilt_head.description", default="VRChat 模型歪头"))
    async def tilt_head(self, direction: str = "left", amount: float = 15.0, **_): return await self.ui_api.do_tilt_head(direction, amount)

    @ui.action(id="wave_hand", label=tr("actions.wave_hand", default="挥手"), refresh_context=True)
    @plugin_entry(id="wave_hand", name=tr("entries.wave_hand.name", default="挥手"), description=tr("entries.wave_hand.description", default="VRChat 模型挥手"), input_schema={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"], "default": "right"}, "style": {"type": "string", "enum": ["hello", "bye", "excited"], "default": "hello"}}})
    async def wave_hand(self, side: str = "right", style: str = "hello", **_):
        r = await self.ui_api.do_wave_hand(side, style)
        self._notify_ai(f"正在挥手 ({style})")
        return r

    @plugin_entry(id="bow", name=tr("entries.bow.name", default="鞠躬"), description=tr("entries.bow.description", default="VRChat 模型鞠躬"))
    async def bow(self, depth: float = 30.0, **_):
        r = await self.ui_api.do_bow(depth)
        self._notify_ai("正在鞠躬")
        return r

    @ui.action(id="start_idle", label=tr("actions.start_idle", default="待机动画"), refresh_context=True)
    @plugin_entry(id="start_idle", name=tr("entries.start_idle.name", default="开启待机动画"), description=tr("entries.start_idle.description", default="VRChat 呼吸+微晃待机"))
    async def start_idle(self, **_): return await self.ui_api.start_idle()

    @plugin_entry(id="stop_idle", name=tr("entries.stop_idle.name", default="停止待机动画"), description=tr("entries.stop_idle.description", default="停止 VRChat 待机动画"))
    async def stop_idle(self, **_): return await self.ui_api.stop_idle()

    @plugin_entry(id="react_to_audio", name=tr("entries.react_to_audio.name", default="音频同步"), description=tr("entries.react_to_audio.description", default="VRChat 音频律动同步"), input_schema={"type": "object", "properties": {"level": {"type": "number", "minimum": 0.0, "maximum": 1.0}, "freq_band": {"type": "string", "default": "full"}}})
    async def react_to_audio(self, level: float = 0.0, freq_band: str = "full", **_): return await self.ui_api.react_to_audio(level, freq_band)

    # ──────────────────── AI 视觉 ────────────────────

    @plugin_entry(id="vision_face", name=tr("entries.vision_face.name", default="视觉:人脸"), description=tr("entries.vision_face.description", default="摄像头人脸→VRChat HMD 注视"), input_schema={"type": "object", "properties": {"screen_x": {"type": "number", "default": 0.5}, "screen_y": {"type": "number", "default": 0.4}, "screen_w": {"type": "number", "default": 0.15}, "screen_h": {"type": "number", "default": 0.2}, "distance": {"type": "number", "default": 2.0}}})
    async def vision_face(self, screen_x: float = 0.5, screen_y: float = 0.4, screen_w: float = 0.15, screen_h: float = 0.2, distance: float = 2.0, **_):
        r = await self.ui_api.vision_face(screen_x, screen_y, screen_w, screen_h, distance)
        self._notify_ai("检测到人脸，VR 正在注视")
        return r

    @plugin_entry(id="vision_face_lost", name=tr("entries.vision_face_lost.name", default="视觉:人脸丢失"), description=tr("entries.vision_face_lost.description", default="通知人脸已丢失"))
    async def vision_face_lost(self, **_):
        r = await self.ui_api.vision_face_lost()
        self._notify_ai("人脸已丢失，停止注视")
        return r

    @plugin_entry(id="vision_expression", name=tr("entries.vision_expression.name", default="视觉:表情"), description=tr("entries.vision_expression.description", default="表情识别→VRChat 情感"), input_schema={"type": "object", "properties": {"expression": {"type": "string", "enum": ["happy", "sad", "angry", "surprise", "fear", "disgust", "neutral"]}, "confidence": {"type": "number", "default": 0.0}}})
    async def vision_expression(self, expression: str = "neutral", confidence: float = 0.0, **_):
        r = await self.ui_api.vision_expression(expression, confidence)
        if confidence > 0.5:
            self._notify_ai(f"检测到用户表情: {expression} (置信度 {confidence:.0%})", priority=6)
        return r

    @plugin_entry(id="vision_gesture", name=tr("entries.vision_gesture.name", default="视觉:手势"), description=tr("entries.vision_gesture.description", default="手势识别→VRChat 手指"), input_schema={"type": "object", "properties": {"gesture": {"type": "string", "enum": ["open", "fist", "point", "peace", "thumbs_up", "ok", "rock"]}, "side": {"type": "string", "enum": ["left", "right"], "default": "right"}, "confidence": {"type": "number", "default": 0.0}}})
    async def vision_gesture(self, gesture: str = "open", side: str = "right", confidence: float = 0.0, **_):
        r = await self.ui_api.vision_gesture(gesture, side, confidence)
        if confidence > 0.5:
            self._notify_ai(f"检测到用户手势: {gesture}")
        return r

    @plugin_entry(id="vision_object", name=tr("entries.vision_object.name", default="视觉:物体"), description=tr("entries.vision_object.description", default="物体检测→VRChat 注视"), input_schema={"type": "object", "properties": {"obj_type": {"type": "string"}, "x": {"type": "number", "default": 0.0}, "y": {"type": "number", "default": 1.0}, "z": {"type": "number", "default": -3.0}}})
    async def vision_object(self, obj_type: str = "person", x: float = 0.0, y: float = 1.0, z: float = -3.0, **_):
        r = await self.ui_api.vision_object(obj_type, x, y, z)
        self._notify_ai(f"检测到物体: {obj_type}，VR 正在注视")
        return r

    @plugin_entry(id="vision_config", name=tr("entries.vision_config.name", default="视觉:配置"), description=tr("entries.vision_config.description", default="视觉桥接参数"), input_schema={"type": "object", "properties": {"camera_fov_h": {"type": "number"}, "camera_fov_v": {"type": "number"}, "tracking_smooth": {"type": "number"}, "look_distance": {"type": "number"}, "react_to_expression": {"type": "boolean"}, "react_to_gesture": {"type": "boolean"}}})
    async def vision_config(self, **kwargs): return await self.ui_api.vision_config(**kwargs)

    # ──────────────────── VRChat 专用 ────────────────────

    @ui.action(id="vrc_gesture", label=tr("actions.vrc_gesture", default="VRC手势"), refresh_context=True)
    @plugin_entry(id="vrc_gesture", name=tr("entries.vrc_gesture.name", default="VRChat 手势"), description=tr("entries.vrc_gesture.description", default="VRChat 标准 8 手势 (neutral/fist/hand_open/point/peace/rock/gun/thumbs_up)"), input_schema={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"], "default": "right"}, "gesture": {"type": "string", "enum": ["neutral", "fist", "hand_open", "point", "peace", "rock", "gun", "thumbs_up"], "default": "neutral"}}})
    async def vrc_gesture(self, side: str = "right", gesture: str = "neutral", **_):
        r = await self.ui_api.vrc_gesture(side, gesture)
        self._notify_ai(f"VRChat {'右手' if side == 'right' else '左手'}做出 {gesture} 手势")
        return r

    @plugin_entry(id="vrc_gesture_both", name=tr("entries.vrc_gesture_both.name", default="VRChat 双手手势"), description=tr("entries.vrc_gesture_both.description", default="VRChat 双手同步手势"), input_schema={"type": "object", "properties": {"gesture": {"type": "string", "enum": ["neutral", "fist", "hand_open", "point", "peace", "rock", "gun", "thumbs_up"], "default": "neutral"}}})
    async def vrc_gesture_both(self, gesture: str = "neutral", **_):
        r = await self.ui_api.vrc_gesture_both(gesture)
        self._notify_ai(f"VRChat 双手做出 {gesture} 手势", priority=6)
        return r

    @plugin_entry(id="vrc_walk", name=tr("entries.vrc_walk.name", default="VRChat 移动"), description=tr("entries.vrc_walk.description", default="VRChat 摇杆移动"), input_schema={"type": "object", "properties": {"direction": {"type": "string", "enum": ["forward", "backward", "left", "right"], "default": "forward"}}})
    async def vrc_walk(self, direction: str = "forward", **_):
        r = await self.ui_api.vrc_walk(direction)
        self._notify_ai(f"VRChat 向{direction}移动", respond=False)
        return r

    @plugin_entry(id="vrc_walk_for", name=tr("entries.vrc_walk_for.name", default="VRChat 定时移动"), description=tr("entries.vrc_walk_for.description", default="VRChat 移动指定时长后停止"), input_schema={"type": "object", "properties": {"direction": {"type": "string", "enum": ["forward", "backward", "left", "right"], "default": "forward"}, "duration": {"type": "number", "default": 2.0}}})
    async def vrc_walk_for(self, direction: str = "forward", duration: float = 2.0, **_):
        r = await self.ui_api.vrc_walk_for(direction, duration)
        self._notify_ai(f"VRChat 向{direction}移动 {duration}秒", respond=False)
        return r

    @plugin_entry(id="vrc_turn", name=tr("entries.vrc_turn.name", default="VRChat 转向"), description=tr("entries.vrc_turn.description", default="VRChat 平滑转向"), input_schema={"type": "object", "properties": {"direction": {"type": "string", "enum": ["left", "right"], "default": "right"}, "speed": {"type": "number", "default": 0.5}}})
    async def vrc_turn(self, direction: str = "right", speed: float = 0.5, **_):
        r = await self.ui_api.vrc_turn(direction, speed)
        self._notify_ai(f"VRChat 向{direction}转向", respond=False)
        return r

    @plugin_entry(id="vrc_stop_loco", name=tr("entries.vrc_stop_loco.name", default="VRChat 停止移动"), description=tr("entries.vrc_stop_loco.description", default="停止 VRChat 移动"))
    async def vrc_stop_loco(self, **_): return await self.ui_api.vrc_stop_loco()

    @plugin_entry(id="vrc_pickup", name=tr("entries.vrc_pickup.name", default="VRChat 拾取"), description=tr("entries.vrc_pickup.description", default="VRChat 抓取物体"), input_schema={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"], "default": "right"}}})
    async def vrc_pickup(self, side: str = "right", **_):
        r = await self.ui_api.vrc_pickup(side)
        self._notify_ai(f"VRChat {'右手' if side == 'right' else '左手'}拾取物体", priority=6)
        return r

    @plugin_entry(id="vrc_drop", name=tr("entries.vrc_drop.name", default="VRChat 放下"), description=tr("entries.vrc_drop.description", default="VRChat 放下物体"), input_schema={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"], "default": "right"}}})
    async def vrc_drop(self, side: str = "right", **_):
        r = await self.ui_api.vrc_drop(side)
        self._notify_ai(f"VRChat {'右手' if side == 'right' else '左手'}放下物体")
        return r

    @plugin_entry(id="vrc_jump", name=tr("entries.vrc_jump.name", default="VRChat 跳跃"), description=tr("entries.vrc_jump.description", default="VRChat 跳跃"))
    async def vrc_jump(self, **_):
        r = await self.ui_api.vrc_jump()
        self._notify_ai("VRChat 跳跃")
        return r

    @plugin_entry(id="vrc_sit", name=tr("entries.vrc_sit.name", default="VRChat 坐下"), description=tr("entries.vrc_sit.description", default="VRChat 坐姿预设"))
    async def vrc_sit(self, **_):
        r = await self.ui_api.vrc_sit()
        self._notify_ai("VRChat 坐下了")
        return r

    @plugin_entry(id="vrc_crouch", name=tr("entries.vrc_crouch.name", default="VRChat 蹲下"), description=tr("entries.vrc_crouch.description", default="VRChat 蹲姿预设"))
    async def vrc_crouch(self, **_):
        r = await self.ui_api.vrc_crouch()
        self._notify_ai("VRChat 蹲下了")
        return r

    @plugin_entry(id="vrc_handshake", name=tr("entries.vrc_handshake.name", default="VRChat 握手"), description=tr("entries.vrc_handshake.description", default="VRChat 握手动作"), input_schema={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"], "default": "right"}}})
    async def vrc_handshake(self, side: str = "right", **_):
        r = await self.ui_api.vrc_handshake(side)
        self._notify_ai("VRChat 伸手握手", priority=7)
        return r

    @plugin_entry(id="vrc_fbt_calibrate", name=tr("entries.vrc_fbt_calibrate.name", default="VRChat FBT 校准"), description=tr("entries.vrc_fbt_calibrate.description", default="VRChat 全身追踪校准"), input_schema={"type": "object", "properties": {"height": {"type": "string", "enum": ["short", "medium", "tall", "tower"], "default": "medium"}}})
    async def vrc_fbt_calibrate(self, height: str = "medium", **_): return await self.ui_api.vrc_fbt_calibrate(height)

    @plugin_entry(id="vrc_gestures_info", name=tr("entries.vrc_gestures_info.name", default="VRChat 手势列表"), description=tr("entries.vrc_gestures_info.description", default="获取可用 VRChat 手势列表"))
    async def vrc_gestures_info(self, **_): return await self.ui_api.vrc_available_gestures()

    # ──────────────────── 状态查询 & 辅助 ────────────────────

    @plugin_entry(id="get_dashboard_state", name=tr("entries.get_dashboard_state.name", default="获取完整状态"), description=tr("entries.get_dashboard_state.description", default="读取 VRChat Controller 全部状态"))
    async def get_dashboard_state(self, **_):
        return Ok(await self.dashboard_service.build_dashboard_state())

    @plugin_entry(id="send_single_packet", name=tr("entries.send_single_packet.name", default="发送单次数据包"), description=tr("entries.send_single_packet.description", default="立即发送一次 UDP 数据包"))
    async def send_single_packet(self, **_): return await self.ui_api.send_single_packet()

    @plugin_entry(id="reset_inputs", name=tr("entries.reset_inputs.name", default="重置控制器输入"), description=tr("entries.reset_inputs.description", default="重置 VRChat 控制器按键摇杆"))
    async def reset_inputs(self, side: str = "both", **_): return await self.ui_api.reset_inputs(side=side)

    @ui.action(id="save_settings", label=tr("actions.save_settings", default="保存设置"), refresh_context=True)
    @plugin_entry(id="save_settings", name=tr("entries.save_settings.name", default="保存设置"), description=tr("entries.save_settings.description", default="保存所有配置到磁盘"))
    async def save_settings(self, **kwargs): return Ok(await self.dashboard_service.save_settings(**kwargs))

    # ──────────────────── 驱动管理 ────────────────────

    @plugin_entry(id="get_driver_state", name=tr("entries.get_driver_state.name", default="驱动状态"), description=tr("entries.get_driver_state.description", default="查询 AnyaDance 驱动运行状态"))
    async def get_driver_state(self, **_):
        return Ok(self.driver_service.get_driver_state())

    @plugin_entry(id="register_driver", name=tr("entries.register_driver.name", default="注册驱动"), description=tr("entries.register_driver.description", default="向 SteamVR 注册 AnyaDance 虚拟设备驱动"))
    async def register_driver_entry(self, **_):
        r = await self.driver_service.register_driver()
        self._notify_ai("AnyaDance 驱动已注册" if r.get("ok") else f"驱动注册失败: {r.get('error')}")
        return Ok(r)

    @plugin_entry(id="unregister_driver", name=tr("entries.unregister_driver.name", default="注销驱动"), description=tr("entries.unregister_driver.description", default="从 SteamVR 注销 AnyaDance 驱动"))
    async def unregister_driver_entry(self, **_):
        r = await self.driver_service.unregister_driver()
        self._notify_ai("AnyaDance 驱动已注销" if r.get("ok") else f"驱动注销失败: {r.get('error')}")
        return Ok(r)

    @plugin_entry(id="start_anyadance", name=tr("entries.start_anyadance.name", default="启动 AnyaDance"), description=tr("entries.start_anyadance.description", default="启动 AnyaDance.exe 桌面程序"))
    async def start_anyadance_entry(self, **_):
        r = await self.driver_service.start_anyadance()
        self._notify_ai("AnyaDance 已启动" if r.get("ok") else f"启动失败: {r.get('error')}")
        return Ok(r)

    @plugin_entry(id="stop_anyadance", name=tr("entries.stop_anyadance.name", default="停止 AnyaDance"), description=tr("entries.stop_anyadance.description", default="停止 AnyaDance.exe 进程"))
    async def stop_anyadance_entry(self, **_):
        r = await self.driver_service.stop_anyadance()
        self._notify_ai("AnyaDance 已停止")
        return Ok(r)

    @plugin_entry(id="restart_steamvr", name=tr("entries.restart_steamvr.name", default="重启 SteamVR"), description=tr("entries.restart_steamvr.description", default="强制停止并重新启动 SteamVR"))
    async def restart_steamvr_entry(self, **_):
        r = await self.driver_service.restart_steamvr()
        self._notify_ai("正在重启 SteamVR...")
        return Ok(r)

    @plugin_entry(id="driver_oneclick", name=tr("entries.driver_oneclick.name", default="一键启动"), description=tr("entries.driver_oneclick.description", default="一键完成: 注册驱动 → 启动 AnyaDance → 开始流送"))
    async def driver_oneclick(self, **_):
        reg = await self.driver_service.register_driver()
        if not reg.get("ok") and reg.get("status") != "already_registered":
            return Ok({"ok": False, "step": "register", "error": reg.get("error")})
        start = await self.driver_service.start_anyadance()
        if not start.get("ok") and start.get("status") != "already_running":
            return Ok({"ok": False, "step": "start", "error": start.get("error")})
        stream = await self.ui_api.start_stream()
        self._notify_ai("AnyaDance 一键启动完成: 驱动已注册 → 进程已启动 → UDP 流送中")
        return Ok({"ok": True, "steps": {"register": reg, "start": start, "stream": stream}})

    # ──────────────────── 自主视觉截图 ────────────────────

    @plugin_entry(id="vision_capture", name=tr("entries.vision_capture.name", default="视觉:截图"), description=tr("entries.vision_capture.description", default="截取游戏画面并返回 base64 图像供 AI 自主视觉分析"), input_schema={"type": "object", "properties": {"monitor_index": {"type": "integer", "default": 0}, "quality": {"type": "integer", "default": 75}, "scale": {"type": "number", "default": 1.0}}})
    async def vision_capture(self, monitor_index: int = -1, quality: int = -1, scale: float = -1.0, **_):
        r = self.screen_capture.capture(monitor_index=monitor_index, quality=quality, scale=scale)
        if r.get("ok"):
            self._notify_ai(f"已截取游戏画面: {r['width']}x{r['height']}, {r['size_kb']}KB")
        return Ok(r)

    @plugin_entry(id="vision_capture_monitors", name=tr("entries.vision_capture_monitors.name", default="视觉:显示器列表"), description=tr("entries.vision_capture_monitors.description", default="获取可用显示器列表"))
    async def vision_capture_monitors(self, **_):
        return Ok({"monitors": self.screen_capture.get_monitors()})

    @plugin_entry(id="vision_capture_config", name=tr("entries.vision_capture_config.name", default="视觉:截图配置"), description=tr("entries.vision_capture_config.description", default="设置截图参数"), input_schema={"type": "object", "properties": {"monitor_index": {"type": "integer"}, "quality": {"type": "integer"}, "scale": {"type": "number"}, "format": {"type": "string", "enum": ["jpeg", "png"]}}})
    async def vision_capture_config(self, **kwargs):
        return Ok(self.screen_capture.set_config(**{k: v for k, v in kwargs.items() if v is not None}))

    # ════════════════════ LLM Tools: AI 可直接调用 ════════════════════

    @llm_tool(
        name="vr_emotion",
        description="设置 VRChat 中角色的情感姿态。情感会影响全身姿态、手势和身体语言。可选情感: happy/sad/angry/surprised/scared/excited/shy/confident/relaxed/curious/tired/neutral",
        parameters={"type": "object", "properties": {"emotion": {"type": "string", "enum": ["happy", "sad", "angry", "surprised", "scared", "excited", "shy", "confident", "relaxed", "curious", "tired", "neutral"]}, "intensity": {"type": "number", "default": 1.0, "minimum": 0.0, "maximum": 1.0, "description": "情感强度 0-1"}}, "required": ["emotion"]},
        timeout=5.0,
    )
    async def llm_vr_emotion(self, emotion: str = "neutral", intensity: float = 1.0, **_):
        r = await self.ui_api.set_emotion(emotion, intensity)
        self._notify_ai(f"情感切换为 {emotion}，强度 {intensity:.0%}", priority=6)
        return r

    @llm_tool(
        name="vr_gesture",
        description="让 VRChat 角色用单手做出特定手势。可选手势: neutral(默认)/fist(握拳)/hand_open(张开)/point(食指)/peace(剪刀手)/rock(摇滚)/gun(枪)/thumbs_up(点赞)",
        parameters={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"], "default": "right"}, "gesture": {"type": "string", "enum": ["neutral", "fist", "hand_open", "point", "peace", "rock", "gun", "thumbs_up"]}}, "required": ["gesture"]},
        timeout=5.0,
    )
    async def llm_vr_gesture(self, side: str = "right", gesture: str = "neutral", **_):
        r = await self.ui_api.vrc_gesture(side, gesture)
        self._notify_ai(f"VRChat {'右手' if side == 'right' else '左手'}做出 {gesture} 手势")
        return r

    @llm_tool(
        name="vr_gesture_both",
        description="让 VRChat 角色用双手同时做出同一手势。可选: neutral/fist/hand_open/point/peace/rock/gun/thumbs_up",
        parameters={"type": "object", "properties": {"gesture": {"type": "string", "enum": ["neutral", "fist", "hand_open", "point", "peace", "rock", "gun", "thumbs_up"]}}, "required": ["gesture"]},
        timeout=5.0,
    )
    async def llm_vr_gesture_both(self, gesture: str = "neutral", **_):
        r = await self.ui_api.vrc_gesture_both(gesture)
        self._notify_ai(f"VRChat 双手做出 {gesture} 手势", priority=6)
        return r

    @llm_tool(
        name="vr_walk",
        description="控制 VRChat 角色向指定方向持续行走。方向: forward(前)/backward(后)/left(左)/right(右)。移动 duration 秒后自动停止。",
        parameters={"type": "object", "properties": {"direction": {"type": "string", "enum": ["forward", "backward", "left", "right"], "default": "forward"}, "duration": {"type": "number", "default": 3.0, "description": "行走持续秒数"}}, "required": ["direction"]},
        timeout=10.0,
    )
    async def llm_vr_walk(self, direction: str = "forward", duration: float = 3.0, **_):
        r = await self.ui_api.vrc_walk_for(direction, duration)
        self._notify_ai(f"VRChat 向{direction}移动 {duration}秒", respond=False)
        return r

    @llm_tool(
        name="vr_stop_walk",
        description="立即停止 VRChat 角色的移动。",
        parameters={"type": "object", "properties": {}},
        timeout=5.0,
    )
    async def llm_vr_stop_walk(self, **_):
        return await self.ui_api.vrc_stop_loco()

    @llm_tool(
        name="vr_turn",
        description="让 VRChat 角色向左或右转向。",
        parameters={"type": "object", "properties": {"direction": {"type": "string", "enum": ["left", "right"], "default": "right"}, "speed": {"type": "number", "default": 0.5, "description": "转向速度 0-1"}}, "required": ["direction"]},
        timeout=5.0,
    )
    async def llm_vr_turn(self, direction: str = "right", speed: float = 0.5, **_):
        r = await self.ui_api.vrc_turn(direction, speed)
        self._notify_ai(f"VRChat 向{direction}转向", respond=False)
        return r

    @llm_tool(
        name="vr_look_at",
        description="让 VRChat 角色的头部(HMD)注视指定的 3D 世界坐标位置。坐标系统: X=左右, Y=上下(1.5为眼高), Z=前后(负值为前方)。",
        parameters={"type": "object", "properties": {"x": {"type": "number", "description": "目标 X 坐标"}, "y": {"type": "number", "default": 1.5, "description": "目标 Y 坐标"}, "z": {"type": "number", "description": "目标 Z 坐标"}, "smooth": {"type": "number", "default": -1, "description": "平滑度 -1=默认"}}, "required": ["x", "z"]},
        timeout=5.0,
    )
    async def llm_vr_look_at(self, x: float = 0.0, y: float = 1.5, z: float = -3.0, smooth: float = -1.0, **_):
        return await self.ui_api.look_at(x, y, z, smooth)

    @llm_tool(
        name="vr_animation",
        description="让 VRChat 角色播放动作动画。动作: nod(点头)/shake(摇头)/tilt(歪头)/wave(挥手)/bow(鞠躬)。可选指定手侧(side)和风格(style)。",
        parameters={"type": "object", "properties": {"action": {"type": "string", "enum": ["nod", "shake", "tilt", "wave", "bow"]}, "count": {"type": "integer", "default": 1, "description": "点头/摇头次数"}, "speed": {"type": "number", "default": 1.0}, "side": {"type": "string", "enum": ["left", "right"], "default": "right"}, "style": {"type": "string", "enum": ["hello", "bye", "excited"], "default": "hello"}}, "required": ["action"]},
        timeout=10.0,
    )
    async def llm_vr_animation(self, action: str = "nod", count: int = 1, speed: float = 1.0,
                               side: str = "right", style: str = "hello", **_):
        if action == "nod":
            r = await self.ui_api.do_nod_head(count, speed)
        elif action == "shake":
            r = await self.ui_api.do_shake_head(count, speed)
        elif action == "tilt":
            r = await self.ui_api.do_tilt_head("left", 15)
        elif action == "wave":
            r = await self.ui_api.do_wave_hand(side, style)
            self._notify_ai(f"正在挥手 ({style})")
        elif action == "bow":
            r = await self.ui_api.do_bow(30)
            self._notify_ai("正在鞠躬")
        else:
            r = {"action": action, "status": "unknown"}
        return r

    @llm_tool(
        name="vr_pickup",
        description="让 VRChat 角色用指定手拾取/抓取面前的物体。",
        parameters={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"], "default": "right"}}, "required": []},
        timeout=5.0,
    )
    async def llm_vr_pickup(self, side: str = "right", **_):
        r = await self.ui_api.vrc_pickup(side)
        self._notify_ai(f"VRChat {'右手' if side == 'right' else '左手'}拾取物体", priority=6)
        return r

    @llm_tool(
        name="vr_drop",
        description="让 VRChat 角色放下手中抓取的物体。",
        parameters={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"], "default": "right"}}, "required": []},
        timeout=5.0,
    )
    async def llm_vr_drop(self, side: str = "right", **_):
        r = await self.ui_api.vrc_drop(side)
        self._notify_ai(f"VRChat {'右手' if side == 'right' else '左手'}放下物体")
        return r

    @llm_tool(
        name="vr_jump",
        description="让 VRChat 角色跳跃一下。",
        parameters={"type": "object", "properties": {}},
        timeout=5.0,
    )
    async def llm_vr_jump(self, **_):
        r = await self.ui_api.vrc_jump()
        self._notify_ai("VRChat 跳跃")
        return r

    @llm_tool(
        name="vr_sit",
        description="让 VRChat 角色坐下。",
        parameters={"type": "object", "properties": {}},
        timeout=5.0,
    )
    async def llm_vr_sit(self, **_):
        r = await self.ui_api.vrc_sit()
        self._notify_ai("VRChat 坐下了")
        return r

    @llm_tool(
        name="vr_crouch",
        description="让 VRChat 角色蹲下。",
        parameters={"type": "object", "properties": {}},
        timeout=5.0,
    )
    async def llm_vr_crouch(self, **_):
        r = await self.ui_api.vrc_crouch()
        self._notify_ai("VRChat 蹲下了")
        return r

    @llm_tool(
        name="vr_handshake",
        description="让 VRChat 角色伸出手与面前的人握手。",
        parameters={"type": "object", "properties": {"side": {"type": "string", "enum": ["left", "right"], "default": "right"}}, "required": []},
        timeout=5.0,
    )
    async def llm_vr_handshake(self, side: str = "right", **_):
        r = await self.ui_api.vrc_handshake(side)
        self._notify_ai("VRChat 伸手握手", priority=7)
        return r

    @llm_tool(
        name="vr_dance",
        description="让 VRChat 角色播放 VMD 舞蹈。需要提供 VMD 文件路径。",
        parameters={"type": "object", "properties": {"vmd_path": {"type": "string", "description": "VMD 舞蹈文件路径"}}, "required": ["vmd_path"]},
        timeout=10.0,
    )
    async def llm_vr_dance(self, vmd_path: str = "", **_):
        r = await self.ui_api.play_dance(vmd_path=vmd_path)
        self._notify_ai(f"开始播放舞蹈: {vmd_path}", priority=7)
        return r

    @llm_tool(
        name="vr_stop_dance",
        description="停止 VRChat 角色当前正在播放的舞蹈。",
        parameters={"type": "object", "properties": {}},
        timeout=5.0,
    )
    async def llm_vr_stop_dance(self, **_):
        r = await self.ui_api.stop_dance()
        self._notify_ai("舞蹈已停止")
        return r

    @llm_tool(
        name="vr_get_state",
        description="获取 VR N.E.K.O.cat 插件的当前完整状态，包括连接、情感、追踪、手势等信息。",
        parameters={"type": "object", "properties": {}},
        timeout=5.0,
    )
    async def llm_vr_get_state(self, **_):
        return await self.dashboard_service.build_dashboard_state()

    @llm_tool(
        name="vr_start_idle",
        description="开启 VRChat 角色的待机动画（呼吸+微晃），让角色看起来更自然。",
        parameters={"type": "object", "properties": {}},
        timeout=5.0,
    )
    async def llm_vr_start_idle(self, **_):
        return await self.ui_api.start_idle()

    @llm_tool(
        name="vr_stop_idle",
        description="停止 VRChat 角色的待机动画。",
        parameters={"type": "object", "properties": {}},
        timeout=5.0,
    )
    async def llm_vr_stop_idle(self, **_):
        return await self.ui_api.stop_idle()

    @llm_tool(
        name="vr_driver_status",
        description="查询 AnyaDance 驱动的当前状态，包括是否运行、是否已注册、AnyaDance.exe 路径等。",
        parameters={"type": "object", "properties": {}},
        timeout=5.0,
    )
    async def llm_vr_driver_status(self, **_):
        return self.driver_service.get_driver_state()

    @llm_tool(
        name="vr_driver_oneclick",
        description="一键启动 VR 环境: 自动注册 AnyaDance 驱动、启动 AnyaDance.exe、开启 UDP 流送。适用于首次启动或恢复连接。",
        parameters={"type": "object", "properties": {}},
        timeout=30.0,
    )
    async def llm_vr_driver_oneclick(self, **_):
        reg = await self.driver_service.register_driver()
        if not reg.get("ok") and reg.get("status") != "already_registered":
            return {"ok": False, "step": "register", "error": reg.get("error")}
        start = await self.driver_service.start_anyadance()
        if not start.get("ok") and start.get("status") != "already_running":
            return {"ok": False, "step": "start", "error": start.get("error")}
        stream = await self.ui_api.start_stream()
        self._notify_ai("AnyaDance 一键启动完成: 驱动已注册 → 进程已启动 → UDP 流送中")
        return {"ok": True, "register": reg, "start": start, "stream": stream}

    @llm_tool(
        name="vr_capture_screen",
        description="截取当前游戏画面(屏幕截图)供 AI 自主视觉分析。返回 base64 编码的 JPEG 图像，AI 可以'看到'VRChat 游戏中的场景、人物、UI等。",
        parameters={"type": "object", "properties": {"monitor_index": {"type": "integer", "default": 0, "description": "显示器索引，0=主显示器"}, "quality": {"type": "integer", "default": 75, "description": "JPEG 质量 1-100"}, "scale": {"type": "number", "default": 1.0, "description": "缩放比例 0.1-2.0"}}},
        timeout=10.0,
    )
    async def llm_vr_capture_screen(self, monitor_index: int = -1, quality: int = -1, scale: float = -1.0, **_):
        r = self.screen_capture.capture(monitor_index=monitor_index, quality=quality, scale=scale)
        if r.get("ok"):
            self._notify_ai(f"已截取游戏画面: {r['width']}x{r['height']}, {r['size_kb']}KB")
        return r

    @llm_tool(
        name="vr_capture_game_window",
        description="截取当前前台游戏窗口区域（不含 NEKO 界面），返回 base64 JPEG 供 AI 分析游戏画面。",
        parameters={"type": "object", "properties": {"quality": {"type": "integer", "default": 75, "description": "JPEG 质量 1-100"}}},
        timeout=10.0,
    )
    async def llm_vr_capture_game_window(self, quality: int = -1, **_):
        r = self.screen_capture.capture_active_window(quality=quality)
        if r.get("ok"):
            title = r.get("window_title", "未知窗口")
            self._notify_ai(f"已截取游戏窗口 [{title}]: {r['width']}x{r['height']}, {r['size_kb']}KB")
        return r

    @llm_tool(
        name="vr_get_window_info",
        description="获取当前前台窗口的位置和标题信息。",
        parameters={"type": "object", "properties": {}},
        timeout=5.0,
    )
    async def llm_vr_get_window_info(self, **_):
        rect = self.screen_capture.get_active_window_rect()
        title = self.screen_capture.get_active_window_title_raw()
        return {"window_rect": rect, "window_title": title}
