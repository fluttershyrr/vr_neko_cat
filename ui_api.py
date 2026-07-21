from __future__ import annotations

from typing import Any

from plugin.sdk.plugin import Err, Ok, SdkError


class VrUiApi:
    """统一 API 门面：所有 plugin_entry 的调用入口，负责参数校验 + Ok/Err 结果包装 + 委托底层服务。"""

    def __init__(self, plugin: Any):
        self.plugin = plugin

    async def start_stream(self) -> dict[str, Any]:
        if self.plugin._streaming:
            return Ok({"status": "already_streaming"})
        self.plugin._streaming = True
        self.plugin._stream_task = self.plugin._loop.create_task(self.plugin._stream_loop())
        return Ok({"status": "started"})

    async def stop_stream(self) -> dict[str, Any]:
        self.plugin._streaming = False
        if self.plugin._stream_task:
            self.plugin._stream_task.cancel()
            self.plugin._stream_task = None
        return Ok({"status": "stopped"})

    async def apply_preset(self, preset: str = "standing") -> dict[str, Any]:
        self.plugin.pose_service.apply_preset(preset)
        return Ok({"preset": preset, "applied": True})

    async def set_device_pose(self, device: str = "", position_x: float = 0.0, position_y: float = 0.0, position_z: float = 0.0, rotation_x: float = 0.0, rotation_y: float = 0.0, rotation_z: float = 0.0, rotation_w: float = 1.0, **_) -> dict[str, Any]:
        if not device:
            return Err(SdkError("INVALID_INPUT: device 不能为空"))
        self.plugin.pose_service.set_device_position(device, position_x, position_y, position_z)
        self.plugin.pose_service.set_device_rotation(device, rotation_x, rotation_y, rotation_z, rotation_w)
        return Ok({"device": device, "updated": True})

    async def set_finger_bends(self, side: str = "left", thumb: float = 0.0, index: float = 0.0, middle: float = 0.0, ring: float = 0.0, pinky: float = 0.0, **_) -> dict[str, Any]:
        if side not in ("left", "right"):
            return Err(SdkError("INVALID_INPUT: side 必须为 left 或 right"))
        self.plugin.input_service.set_finger_bends(side, {"thumb": thumb, "index": index, "middle": middle, "ring": ring, "pinky": pinky})
        return Ok({"side": side, "updated": True})

    async def set_joystick(self, side: str = "left", x: float = 0.0, y: float = 0.0, **_) -> dict[str, Any]:
        if side not in ("left", "right"):
            return Err(SdkError("INVALID_INPUT: side 必须为 left 或 right"))
        self.plugin.input_service.set_joystick(side, x, y)
        return Ok({"side": side, "x": x, "y": y})

    async def press_button(self, side: str = "left", button: str = "", pressed: bool = True, **_) -> dict[str, Any]:
        if side not in ("left", "right"):
            return Err(SdkError("INVALID_INPUT: side 必须为 left 或 right"))
        valid_buttons = ["trigger_click", "menu_click", "system_click", "a_click", "b_click", "grip_click"]
        if button not in valid_buttons:
            return Err(SdkError(f"INVALID_INPUT: button 必须是以下之一: {valid_buttons}"))
        self.plugin.input_service.set_button(side, button, pressed)
        return Ok({"side": side, "button": button, "pressed": pressed})

    async def play_dance(self, vmd_path: str = "", **_) -> dict[str, Any]:
        ok = await self.plugin.dance_service.play(vmd_path)
        return Ok({"started": ok})

    async def stop_dance(self, **_) -> dict[str, Any]:
        await self.plugin.dance_service.stop()
        return Ok({"stopped": True})

    async def mirror_hands(self, enabled: bool = True, **_) -> dict[str, Any]:
        self.plugin._config["mirror_hands"] = bool(enabled)
        if enabled:
            self.plugin.pose_service.mirror_hands()
        return Ok({"mirror_hands": enabled})

    async def mirror_feet(self, enabled: bool = True, **_) -> dict[str, Any]:
        self.plugin._config["mirror_feet"] = bool(enabled)
        if enabled:
            self.plugin.pose_service.mirror_feet()
        return Ok({"mirror_feet": enabled})

    async def reset_inputs(self, side: str = "left", **_) -> dict[str, Any]:
        if side not in ("left", "right", "both"):
            return Err(SdkError("INVALID_INPUT: side 必须为 left / right / both"))
        if side == "both":
            self.plugin.input_service.reset_inputs("left")
            self.plugin.input_service.reset_inputs("right")
        else:
            self.plugin.input_service.reset_inputs(side)
        return Ok({"reset": side})

    async def send_single_packet(self, **_) -> dict[str, Any]:
        ok = await self.plugin.udp_service.send()
        return Ok({"sent": ok})

    async def hand_gesture(self, side: str = "left", gesture: str = "open", **_) -> dict[str, Any]:
        if side not in ("left", "right"):
            return Err(SdkError("INVALID_INPUT: side 必须为 left 或 right"))
        self.plugin.input_service._do_gesture(side, gesture)
        return Ok({"side": side, "gesture": gesture})

    async def set_emotion(self, emotion: str = "neutral", intensity: float = 1.0, **_) -> dict[str, Any]:
        r = self.plugin.emotion_service.apply_emotion(emotion, intensity)
        return Ok(r)

    async def blend_emotions(self, emotion_a: str = "neutral", emotion_b: str = "happy", ratio: float = 0.5, **_) -> dict[str, Any]:
        r = self.plugin.emotion_service.blend_emotions(emotion_a, emotion_b, ratio)
        return Ok(r)

    async def capture_baseline(self, **_) -> dict[str, Any]:
        self.plugin.emotion_service.capture_baseline()
        return Ok({"baseline_captured": True})

    async def look_at(self, x: float = 0.0, y: float = 1.5, z: float = -3.0, smooth: float = -1.0, **_) -> dict[str, Any]:
        r = self.plugin.tracking_service.look_at(x, y, z, smooth)
        return Ok(r)

    async def look_at_direction(self, yaw: float = 0.0, pitch: float = 0.0, smooth: float = -1.0, **_) -> dict[str, Any]:
        r = self.plugin.tracking_service.look_at_direction(yaw, pitch, smooth)
        return Ok(r)

    async def reset_head(self, **_) -> dict[str, Any]:
        r = self.plugin.tracking_service.reset_head()
        return Ok(r)

    async def start_tracking(self, x: float = 0.0, y: float = 1.5, z: float = -3.0, **_) -> dict[str, Any]:
        r = await self.plugin.tracking_service.start_tracking(x, y, z)
        return Ok(r)

    async def stop_tracking(self, **_) -> dict[str, Any]:
        r = await self.plugin.tracking_service.stop_tracking()
        return Ok(r)

    async def set_tracking_smooth(self, factor: float = 0.12, **_) -> dict[str, Any]:
        r = self.plugin.tracking_service.set_smooth_factor(factor)
        return Ok(r)

    async def do_nod_head(self, count: int = 1, speed: float = 1.0, **_) -> dict[str, Any]:
        r = await self.plugin.animation_service.nod_head(count, speed)
        return Ok(r)

    async def do_shake_head(self, count: int = 1, speed: float = 1.0, **_) -> dict[str, Any]:
        r = await self.plugin.animation_service.shake_head(count, speed)
        return Ok(r)

    async def do_tilt_head(self, direction: str = "left", amount: float = 15.0, **_) -> dict[str, Any]:
        r = await self.plugin.animation_service.tilt_head(direction, amount)
        return Ok(r)

    async def do_wave_hand(self, side: str = "right", style: str = "hello", **_) -> dict[str, Any]:
        r = await self.plugin.animation_service.wave_hand(side, style)
        return Ok(r)

    async def do_bow(self, depth: float = 30.0, **_) -> dict[str, Any]:
        r = await self.plugin.animation_service.bow(depth)
        return Ok(r)

    async def start_idle(self, **_) -> dict[str, Any]:
        r = await self.plugin.animation_service.start_idle()
        return Ok(r)

    async def stop_idle(self, **_) -> dict[str, Any]:
        r = await self.plugin.animation_service.stop_idle()
        return Ok(r)

    async def react_to_audio(self, level: float = 0.0, freq_band: str = "full", **_) -> dict[str, Any]:
        r = await self.plugin.animation_service.react_to_audio(level, freq_band)
        return Ok(r)

    async def vision_face(self, screen_x: float = 0.5, screen_y: float = 0.4,
                          screen_w: float = 0.15, screen_h: float = 0.2,
                          distance: float = 2.0, **_) -> dict[str, Any]:
        r = self.plugin.vision_bridge.on_face_detected(screen_x, screen_y, screen_w, screen_h, distance)
        return Ok(r)

    async def vision_face_lost(self, **_) -> dict[str, Any]:
        r = self.plugin.vision_bridge.on_face_lost()
        return Ok(r)

    async def vision_expression(self, expression: str = "neutral", confidence: float = 0.0, **_) -> dict[str, Any]:
        r = self.plugin.vision_bridge.on_expression_detected(expression, confidence)
        return Ok(r)

    async def vision_gesture(self, gesture: str = "open", side: str = "right", confidence: float = 0.0, **_) -> dict[str, Any]:
        r = self.plugin.vision_bridge.on_gesture_detected(gesture, side, confidence)
        return Ok(r)

    async def vision_object(self, obj_type: str = "person", x: float = 0.0, y: float = 1.0, z: float = -3.0, **_) -> dict[str, Any]:
        r = self.plugin.vision_bridge.on_object_detected(obj_type, x, y, z)
        return Ok(r)

    async def vision_config(self, camera_fov_h: float = -1, camera_fov_v: float = -1,
                            tracking_smooth: float = -1, look_distance: float = -1,
                            react_to_expression: bool = None, react_to_gesture: bool = None, **_) -> dict[str, Any]:
        kwargs = {}
        if camera_fov_h >= 0: kwargs["camera_fov_h"] = camera_fov_h
        if camera_fov_v >= 0: kwargs["camera_fov_v"] = camera_fov_v
        if tracking_smooth >= 0: kwargs["tracking_smooth"] = tracking_smooth
        if look_distance >= 0: kwargs["look_distance"] = look_distance
        if react_to_expression is not None: kwargs["react_to_expression"] = react_to_expression
        if react_to_gesture is not None: kwargs["react_to_gesture"] = react_to_gesture
        r = self.plugin.vision_bridge.set_vision_config(**kwargs)
        return Ok(r)

    async def vrc_gesture(self, side: str = "right", gesture: str = "neutral", **_) -> dict[str, Any]:
        r = self.plugin.vrchat_service.apply_vrc_gesture(side, gesture)
        return Ok(r)

    async def vrc_gesture_both(self, gesture: str = "neutral", **_) -> dict[str, Any]:
        r = self.plugin.vrchat_service.apply_vrc_gesture_both(gesture)
        return Ok(r)

    async def vrc_walk(self, direction: str = "forward", **_) -> dict[str, Any]:
        r = self.plugin.vrchat_service.walk(direction)
        return Ok(r)

    async def vrc_walk_for(self, direction: str = "forward", duration: float = 2.0, **_) -> dict[str, Any]:
        r = await self.plugin.vrchat_service.walk_for(direction, duration)
        return Ok(r)

    async def vrc_turn(self, direction: str = "right", speed: float = 0.5, **_) -> dict[str, Any]:
        r = self.plugin.vrchat_service.turn(direction, speed)
        return Ok(r)

    async def vrc_stop_loco(self, **_) -> dict[str, Any]:
        r = self.plugin.vrchat_service.stop_locomotion()
        return Ok(r)

    async def vrc_pickup(self, side: str = "right", **_) -> dict[str, Any]:
        r = self.plugin.vrchat_service.pickup(side)
        return Ok(r)

    async def vrc_drop(self, side: str = "right", **_) -> dict[str, Any]:
        r = self.plugin.vrchat_service.drop(side)
        return Ok(r)

    async def vrc_jump(self, **_) -> dict[str, Any]:
        r = self.plugin.vrchat_service.jump()
        return Ok(r)

    async def vrc_sit(self, **_) -> dict[str, Any]:
        r = await self.plugin.vrchat_service.sit()
        return Ok(r)

    async def vrc_crouch(self, **_) -> dict[str, Any]:
        r = await self.plugin.vrchat_service.crouch()
        return Ok(r)

    async def vrc_handshake(self, side: str = "right", **_) -> dict[str, Any]:
        r = await self.plugin.vrchat_service.handshake(side)
        return Ok(r)

    async def vrc_left_menu(self, pressed: bool = True, **_) -> dict[str, Any]:
        if pressed:
            r = self.plugin.vrchat_service.open_menu("left")
        else:
            self.plugin.input_service.set_button("left", "menu_click", False)
            r = {"action": "menu", "side": "left", "pressed": False}
        return Ok(r)

    async def vrc_right_menu(self, pressed: bool = True, **_) -> dict[str, Any]:
        if pressed:
            r = self.plugin.vrchat_service.open_menu("right")
        else:
            self.plugin.input_service.set_button("right", "menu_click", False)
            r = {"action": "menu", "side": "right", "pressed": False}
        return Ok(r)

    async def vrc_select(self, side: str = "right", pressed: bool = True, **_) -> dict[str, Any]:
        if pressed:
            r = self.plugin.vrchat_service.use_action(side)
        else:
            self.plugin.input_service.set_button(side, "a_click", False)
            r = {"action": "use", "side": side, "pressed": False}
        return Ok(r)

    async def vrc_drag_start(self, side: str = "right", **_) -> dict[str, Any]:
        self.plugin.input_service.set_button(side, "grip_click", True)
        self.plugin.input_service.set_button(side, "trigger_click", True)
        return Ok({"dragging": True, "side": side})

    async def vrc_drag_end(self, **_) -> dict[str, Any]:
        for s in ("left", "right"):
            self.plugin.input_service.set_button(s, "grip", False)
            self.plugin.input_service.set_button(s, "trigger", False)
        return Ok({"dragging": False})

    async def vrc_fbt_calibrate(self, height: str = "medium", **_) -> dict[str, Any]:
        r = self.plugin.vrchat_service.calibrate_fbt(height)
        return Ok(r)

    async def vrc_available_gestures(self, **_) -> dict[str, Any]:
        r = self.plugin.vrchat_service.get_available_gestures()
        return Ok(r)

    async def capture_screen(self, monitor_index: int = -1, quality: int = -1,
                            scale: float = -1.0, **_) -> dict[str, Any]:
        r = self.plugin.screen_capture.capture(
            monitor_index=monitor_index, quality=quality, scale=scale)
        return Ok(r)

    async def capture_monitors(self, **_) -> dict[str, Any]:
        return Ok({"monitors": self.plugin.screen_capture.get_monitors()})

    async def capture_active_window(self, quality: int = -1, **_) -> dict[str, Any]:
        r = self.plugin.screen_capture.capture_active_window(quality=quality)
        return Ok(r)

    async def capture_game_region(self, left: int = 0, top: int = 0,
                                  width: int = 1920, height: int = 1080,
                                  quality: int = -1, **_) -> dict[str, Any]:
        r = self.plugin.screen_capture.capture_game_region(
            left=left, top=top, width=width, height=height, quality=quality)
        return Ok(r)

    async def get_active_window_info(self, **_) -> dict[str, Any]:
        rect = self.plugin.screen_capture.get_active_window_rect()
        title = self.plugin.screen_capture.get_active_window_title_raw()
        return Ok({
            "window_rect": rect,
            "window_title": title,
        })
