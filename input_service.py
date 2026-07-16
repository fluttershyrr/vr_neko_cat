from __future__ import annotations

from typing import Any


class VrInputService:
    """控制器输入管理：按键/扳机/握把/摇杆/五指弯曲，以及手势快捷方法。"""

    def __init__(self, plugin: Any):
        self.plugin = plugin

    @property
    def _config(self) -> dict[str, Any]:
        return self.plugin._config

    def set_button(self, side: str, button: str, pressed: bool) -> None:
        key = f"{side}_controller_input"
        cfg = self._config.setdefault(key, {})
        cfg[button] = bool(pressed)

    def set_trigger(self, side: str, value: float) -> None:
        key = f"{side}_controller_input"
        cfg = self._config.setdefault(key, {})
        cfg["trigger_value"] = max(0.0, min(1.0, float(value)))
        cfg["trigger_click"] = cfg["trigger_value"] > 0.5

    def set_grip(self, side: str, value: float) -> None:
        key = f"{side}_controller_input"
        cfg = self._config.setdefault(key, {})
        cfg["grip_value"] = max(0.0, min(1.0, float(value)))
        cfg["grip_click"] = cfg["grip_value"] > 0.5

    def set_joystick(self, side: str, x: float, y: float) -> None:
        key = f"{side}_controller_input"
        cfg = self._config.setdefault(key, {})
        cfg["joystick_x"] = max(-1.0, min(1.0, float(x)))
        cfg["joystick_y"] = max(-1.0, min(1.0, float(y)))

    def set_finger_bends(self, side: str, bends: dict[str, float]) -> None:
        key = f"{side}_finger_bends"
        cfg = self._config.setdefault(key, {})
        for finger in ("thumb", "index", "middle", "ring", "pinky"):
            if finger in bends:
                cfg[finger] = max(0.0, min(1.0, float(bends[finger])))

    def set_finger(self, side: str, finger: str, value: float) -> None:
        key = f"{side}_finger_bends"
        cfg = self._config.setdefault(key, {})
        cfg[finger] = max(0.0, min(1.0, float(value)))

    def open_hand(self, side: str) -> None:
        self.set_finger_bends(side, {"thumb": 0.0, "index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0})

    def make_fist(self, side: str, closed: bool = True) -> None:
        v = 1.0 if closed else 0.0
        self.set_finger_bends(side, {"thumb": v, "index": v, "middle": v, "ring": v, "pinky": v})

    def make_point(self, side: str) -> None:
        self.set_finger_bends(side, {"thumb": 1.0, "index": 0.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0})

    def make_peace(self, side: str) -> None:
        self.set_finger_bends(side, {"thumb": 1.0, "index": 0.0, "middle": 0.0, "ring": 1.0, "pinky": 1.0})

    def make_thumbs_up(self, side: str) -> None:
        self.set_finger_bends(side, {"thumb": 0.0, "index": 1.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0})

    def make_rock(self, side: str) -> None:
        self.set_finger_bends(side, {"thumb": 1.0, "index": 0.0, "middle": 1.0, "ring": 1.0, "pinky": 0.0})

    def make_gun(self, side: str) -> None:
        self.set_finger_bends(side, {"thumb": 0.0, "index": 0.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0})

    def _do_gesture(self, side: str, gesture: str) -> None:
        """将手势名（open/fist/point/peace/thumbs_up/rock/gun）映射为五指弯曲值。"""
        gestures = {
            "open": self.open_hand,
            "fist": lambda s: self.make_fist(s, True),
            "point": self.make_point,
            "peace": self.make_peace,
            "thumbs_up": self.make_thumbs_up,
            "rock": self.make_rock,
            "gun": self.make_gun,
        }
        fn = gestures.get(gesture)
        if fn:
            fn(side)

    def reset_inputs(self, side: str) -> None:
        key = f"{side}_controller_input"
        self._config[key] = {
            "trigger_click": False, "trigger_value": 0.0,
            "menu_click": False, "system_click": False,
            "a_click": False, "b_click": False,
            "grip_click": False, "grip_value": 0.0,
            "joystick_x": 0.0, "joystick_y": 0.0,
            "trackpad_x": 0.0, "trackpad_y": 0.0,
        }
        bends_key = f"{side}_finger_bends"
        self._config[bends_key] = {"thumb": 0.0, "index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0}

    def get_controller_state(self, side: str) -> dict[str, Any]:
        inp = self._config.get(f"{side}_controller_input", {})
        bends = self._config.get(f"{side}_finger_bends", {})
        return {
            "buttons": {
                "trigger_click": inp.get("trigger_click", False),
                "trigger_value": inp.get("trigger_value", 0.0),
                "menu_click": inp.get("menu_click", False),
                "system_click": inp.get("system_click", False),
                "a_click": inp.get("a_click", False),
                "b_click": inp.get("b_click", False),
                "grip_click": inp.get("grip_click", False),
                "grip_value": inp.get("grip_value", 0.0),
            },
            "joystick": [inp.get("joystick_x", 0.0), inp.get("joystick_y", 0.0)],
            "trackpad": [inp.get("trackpad_x", 0.0), inp.get("trackpad_y", 0.0)],
            "finger_bends": {
                "thumb": bends.get("thumb", 0.0),
                "index": bends.get("index", 0.0),
                "middle": bends.get("middle", 0.0),
                "ring": bends.get("ring", 0.0),
                "pinky": bends.get("pinky", 0.0),
            },
        }
