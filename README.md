注意注意注意，本插件未开发完成，仅供参考。注意注意注意，本插件未开发完成，仅供参考。注意注意注意，本插件未开发完成，仅供参考。
注意注意注意，本插件未开发完成，仅供参考。注意注意注意，本插件未开发完成，仅供参考。注意注意注意，本插件未开发完成，仅供参考。







# VR N.E.K.O.cat

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://github.com/Project-N-E-K-O/N.E.K.O/blob/main/LICENSE)
[![N.E.K.O](https://img.shields.io/badge/N.E.K.O-Plugin%20SDK-orange.svg)](https://github.com/Project-N-E-K-O/N.E.K.O)

**VR N.E.K.O.cat** 是 [N.E.K.O. AI 伴侣平台](https://github.com/Project-N-E-K-O/N.E.K.O) 的全功能 VR 插件，通过 UDP 协议驱动 [AnyaDance](https://github.com/anyapipira/AnyaDance) SteamVR 虚拟设备，让 N.E.K.O. 的 AI 能够在 VRChat 中实现全身追踪 (FBT)、手势控制、情感表达、舞蹈表演、自主移动等丰富行为。

---

## 核心特性

| 功能 | 描述 |
|------|------|
| **全身追踪 (FBT)** | 6 设备位姿模拟 (HMD / 左右手柄 / 髋部 / 左右脚)，60Hz 实时流送 |
| **手势控制** | 8 种 VRChat 标准手势 + 五指独立弯曲 + 摇杆/按键/扳机输入 |
| **情感映射** | 12 种情感 (开心/悲伤/愤怒/恐惧/惊讶/厌恶等) → 全身姿态自动映射 |
| **舞蹈系统** | VMD 文件解析播放，骨骼重定向到 6 设备，支持循环/变速/换模型 |
| **视觉桥接** | AI 视觉 → VR 行为：人脸检测→注视、表情→情感、手势→手指、物体→关注 |
| **动画动作** | 点头/摇头/歪头/挥手/鞠躬/待机动画/音频律动响应 |
| **AI 注视追踪** | 平滑注视目标或方向，自动转头追踪 |
| **VRChat 操控** | 移动/转向/跳跃/坐下/蹲下/拾取/投掷/握手/FBT 校准 |
| **驱动管理** | AnyaDance 进程生命周期管理 + SteamVR 驱动注册/注销/重启 |
| **游戏画面感知** | 截图前台游戏窗口 (mss，无 NEKO 覆盖层)，供 AI 分析游戏场景 |
| **Web 控制面板** | 内置可视化仪表板，实时查看所有设备状态 |
| **AI 可直接调用** | 22 个 LLM Tool 让 AI 自主控制所有 VR 行为 |

---

## 架构概览

```
┌──────────────────────────────────────────────────────┐
│  N.E.K.O AI 核心                                       │
│  (plugin_entry / llm_tool 调用)                       │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│  VRControllerPlugin  (vr_neko_cat 插件)                │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐       │
│  │ pose     │  │ emotion  │  │ dance        │       │
│  │ service  │  │ service  │  │ service      │       │
│  ├──────────┤  ├──────────┤  ├──────────────┤       │
│  │ input    │  │ tracking │  │ animation    │       │
│  │ service  │  │ service  │  │ service      │       │
│  ├──────────┤  ├──────────┤  ├──────────────┤       │
│  │ vrchat   │  │ vision   │  │ dashboard    │       │
│  │ service  │  │ bridge   │  │ service      │       │
│  └──────────┘  └──────────┘  └──────────────┘       │
│                                                      │
│  VrUdpService → build_packet() → JSON (AnyaDance 协议)│
│                  │ socket.sendto()                   │
│                  ▼                                   │
│            127.0.0.1:39570 (UDP)                     │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│  AnyaDance.exe  →  driver_anyadance.dll               │
│  (C++ SteamVR 虚拟设备驱动)                            │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│  SteamVR  →  VRChat  (全身追踪 / 手势 / 移动)          │
└──────────────────────────────────────────────────────┘
```

---

## 快速开始

### 前置要求

- Windows 10/11
- Python 3.11
- [N.E.K.O.](https://github.com/Project-N-E-K-O/N.E.K.O) 已安装并运行
- SteamVR 已安装
- VRChat (可选，用于实际控制)

### 安装

插件位于 `N.E.K.O/plugin/plugins/vr_neko_cat/`，N.E.K.O. 启动时会自动发现。

### 使用

1. 启动 N.E.K.O.
2. 在插件管理面板启用 `VR N.E.K.O.cat`
3. 打开 Web 控制面板 (`static/index.html`)
4. 通过控制面板或 AI 对话控制 VRChat 行为

### 一键驱动启动

插件内置 AnyaDance v0.0.3 发布版，可通过 `driver_oneclick` 一键完成：启动 AnyaDance → 注册驱动 → 启动流送。

---

## UPD 协议

插件向 `127.0.0.1:39570` 发送 UDP JSON 数据包，格式遵循 AnyaDance 协议：

```json
{
  "version": 1,
  "devices": {
    "hmd":               {"pos": [x,y,z], "rot": [x,y,z,w]},
    "left_controller":   {"pos": [x,y,z], "rot": [x,y,z,w]},
    "right_controller":  {"pos": [x,y,z], "rot": [x,y,z,w]},
    "hip":               {"pos": [x,y,z], "rot": [x,y,z,w]},
    "left_foot":         {"pos": [x,y,z], "rot": [x,y,z,w]},
    "right_foot":        {"pos": [x,y,z], "rot": [x,y,z,w]}
  },
  "inputs": {
    "left_controller":  { "trigger_click": false, "joystick_x": 0.0, ... },
    "right_controller": { "trigger_click": false, "joystick_x": 0.0, ... },
    "finger_bends": {
      "left":  { "thumb": 0.0, "index": 0.0, ... },
      "right": { "thumb": 0.0, "index": 0.0, ... }
    }
  }
}
```

---

## AI 可调用工具 (LLM Tools)

| 工具名 | 功能 |
|--------|------|
| `vr_emotion` | 设置情感姿态 |
| `vr_gesture` / `vr_gesture_both` | VRChat 手势 |
| `vr_walk` / `vr_stop_walk` | 移动控制 |
| `vr_turn` | 转向 |
| `vr_look_at` | 注视目标 |
| `vr_animation` | 播放动画动作 |
| `vr_pickup` / `vr_drop` | 拾取/投掷 |
| `vr_jump` / `vr_sit` / `vr_crouch` | 跳跃/坐下/蹲下 |
| `vr_handshake` | 握手 |
| `vr_dance` / `vr_stop_dance` | 舞蹈控制 |
| `vr_get_state` | 获取当前状态 |
| `vr_start_idle` / `vr_stop_idle` | 待机动画 |
| `vr_driver_status` / `vr_driver_oneclick` | 驱动状态/一键启动 |
| `vr_capture_screen` / `vr_capture_game_window` | 截图 |
| `vr_get_window_info` | 获取窗口信息 |

---

## 依赖

- [N.E.K.O. Plugin SDK](https://github.com/Project-N-E-K-O/N.E.K.O) (>=0.1.0)
- [mss](https://github.com/BoboTiG/python-mss) — 高速屏幕截图
- [Pillow](https://python-pillow.org/) — 图像处理
- [numpy](https://numpy.org/) — 数值计算

---

## 许可证

Apache 2.0 — 详见 [LICENSE](https://github.com/Project-N-E-K-O/N.E.K.O/blob/main/LICENSE)

本插件作为 N.E.K.O. 生态的一部分，遵循上游项目许可证。

---

## 相关项目

- [N.E.K.O.](https://github.com/Project-N-E-K-O/N.E.K.O) — AI 伴侣平台主项目
- [AnyaDance](https://github.com/anyapipira/AnyaDance) — SteamVR 虚拟全身追踪驱动
