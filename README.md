# VR N.E.K.O.cat

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://github.com/Project-N-E-K-O/N.E.K.O/blob/main/LICENSE)
[![N.E.K.O](https://img.shields.io/badge/N.E.K.O-Plugin%20SDK-orange.svg)](https://github.com/Project-N-E-K-O/N.E.K.O)

**VR N.E.K.O.cat** 是 [N.E.K.O. AI 伴侣平台](https://github.com/Project-N-E-K-O/N.E.K.O) 的全功能 VR 插件，通过 UDP 协议驱动 [AnyaDance](https://github.com/anyapipira/AnyaDance) SteamVR 虚拟设备，让 N.E.K.O. 的 AI 能够在 VRChat 中实现全身追踪 (FBT)、手势控制、情感表达、舞蹈表演、自主移动等丰富行为。

---

## 核心特性

| 功能 | 描述 |
|------|------|
| **全身追踪 (FBT)** | 6 设备位姿模拟 (HMD / 左右手柄 / 髋部 / 左右脚)，60Hz 实时 UDP 流送 |
| **手势控制** | 8 种 VRChat 标准手势 + 五指独立弯曲 + 摇杆/按键/扳机输入，含 5 秒卡键自动释放 |
| **情感映射** | 12 种情感 (开心/悲伤/愤怒/恐惧/惊讶/害羞等) → 全身姿态自动映射 |
| **舞蹈系统** | VMD 文件解析播放，骨骼重定向到 6 设备，支持循环/变速 |
| **视觉桥接** | AI 视觉 → VR 行为：人脸检测→注视、表情→情感、手势→手指、物体→关注 |
| **动画动作** | 点头/摇头/歪头/挥手/鞠躬 + 待机呼吸微动 + 音频律动响应 |
| **AI 注视追踪** | 平滑注视目标或方向，自动转头追踪 |
| **VRChat 操控** | 移动/转向/跳跃/坐下/蹲下/拾取/投掷/握手/FBT 校准 |
| **驱动管理** | AnyaDance 进程生命周期管理 + SteamVR 驱动注册/注销/重启 |
| **游戏画面感知** | 截图前台游戏窗口 (mss/PIL 双后端)，供 AI 分析游戏场景 |
| **玻璃控制面板** | 苹果液态玻璃风格 UI，内置氛围粒子引擎 (飘雪/樱花/细雨/星尘) |
| **AI 可直接调用** | 22 个 LLM Tool 让 AI 自主控制所有 VR 行为，50+ plugin_entry 入口 |
| **连接稳定** | UDP 连接健康监测 + 断连自动重建 Socket |

---

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│  N.E.K.O AI 核心 (plugin_entry / llm_tool 调用)          │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  VrNekoCatPlugin (Mixin 组合模式)                         │
│                                                         │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌─────────┐ │
│  │ entries  │  │ llm_tools│  │ ui_api    │  │ dashboard│ │
│  │ (50+ 入口)│  │ (22 工具) │  │ (参数校验) │  │ (聚合状态)│ │
│  └────┬────┘  └────┬─────┘  └─────┬─────┘  └────┬────┘ │
│       │             │              │              │      │
│       └──────┬──────┘              │              │      │
│              ▼                     ▼              │      │
│  ┌───────────────────────────────────────────┐    │      │
│  │  服务层 (7 services + 桥接/适配)             │    │      │
│  │  pose / input / emotion / tracking /      │    │      │
│  │  animation / dance / vrchat / vision      │    │      │
│  └─────────────────┬─────────────────────────┘    │      │
│                    │                              │      │
│                    ▼                              │      │
│  ┌────────────────────────────────────────┐       │      │
│  │  udp_service → build_packet() → JSON   │       │      │
│  │              → socket.sendto()         │       │      │
│  │            127.0.0.1:39570 (UDP)       │       │      │
│  └─────────────────┬──────────────────────┘       │      │
│                    │                              │      │
│  ┌─────────────────┴──────────────────────┐       │      │
│  │  driver_service / config_service       │       │      │
│  │  (进程管理 + 注册表 + 配置持久化)        │       │      │
│  └────────────────────────────────────────┘       │      │
└────────────────────────┬──────────────────────────┘      │
                         │                                 │
                         ▼                                 ▼
┌────────────────────────┐              ┌──────────────────┐
│ AnyaDance.exe          │              │ Web 控制面板      │
│ → SteamVR 驱动         │              │ (index.html)     │
│ → VRChat (FBT/手势/移动)│              │ 玻璃UI + 粒子特效 │
└────────────────────────┘              └──────────────────┘
```

---

## 快速开始

### 前置要求

- Windows 10/11, Python 3.11
- [N.E.K.O.](https://github.com/Project-N-E-K-O/N.E.K.O) 已安装并运行
- SteamVR + VRChat (可选)

### 安装

插件位于 `N.E.K.O/plugin/plugins/vr_neko_cat/`，N.E.K.O. 启动时自动发现。

### 使用

1. 启动 N.E.K.O.
2. 在插件管理面板启用 **VR N.E.K.O.cat**
3. 打开 Web 控制面板查看实时状态
4. 通过 AI 对话或控制面板控制 VRChat 行为

### 一键驱动启动

插件内置 AnyaDance 发布版，`driver_oneclick` 一键完成：启动 AnyaDance → 注册驱动 → 启动流送。

---

## UDP 协议

插件向 `127.0.0.1:39570` 发送 UDP JSON，格式遵循 AnyaDance 协议:

```json
{
  "version": 1,
  "devices": {
    "hmd":              {"valid": true, "connected": true, "pose": {"position": [x,y,z], "rotation_xyzw": [x,y,z,w]}},
    "left_controller":  {...},
    "right_controller": {...},
    "hip":              {...},
    "left_foot":        {...},
    "right_foot":       {...}
  },
  "inputs": {
    "left_controller":  {"trigger_click": false, "joystick_x": 0.0, ...},
    "right_controller": {...},
    "finger_bends":     {"left": {...}, "right": {...}}
  }
}
```

---

## AI 可调用工具 (LLM Tools)

| 工具名 | 功能 |
|--------|------|
| `vr_emotion` | 设置 12 种情感姿态 (0~1 强度) |
| `vr_gesture` / `vr_gesture_both` | 单手/双手 VRChat 手势 |
| `vr_walk` / `vr_stop_walk` / `vr_turn` | 移动控制 (方向 + 秒数) |
| `vr_look_at` / `vr_animation` | 注视目标 / 播放预设动画 |
| `vr_pickup` / `vr_drop` | 拾取/投掷物品 |
| `vr_jump` / `vr_sit` / `vr_crouch` | 跳跃/坐下/蹲下 |
| `vr_handshake` | 伸手握手交互 |
| `vr_dance` / `vr_stop_dance` | 播放/停止 VMD 舞蹈 |
| `vr_get_state` | 获取全状态摘要 |
| `vr_start_idle` / `vr_stop_idle` | 启动/停止待机呼吸动画 |
| `vr_driver_status` / `vr_driver_oneclick` | 驱动状态查询 / 一键启动 |
| `vr_capture_screen` / `vr_capture_game_window` | 全屏/游戏窗口截图 |
| `vr_get_window_info` | 获取前台窗口信息 |

---

## 文件结构

详见 [FILES.md](./FILES.md) — 逐文件说明每个模块的职责。

---

## 依赖

- [N.E.K.O. Plugin SDK](https://github.com/Project-N-E-K-O/N.E.K.O) (>=0.1.0)
- [mss](https://github.com/BoboTiG/python-mss) — 高速屏幕截图 (可选)
- [Pillow](https://python-pillow.org/) — 图像处理后备 (可选)
- [numpy](https://numpy.org/) — 数值计算 (可选)

---

## 许可证

Apache 2.0 — 详见 [LICENSE](https://github.com/Project-N-E-K-O/N.E.K.O/blob/main/LICENSE)

---

## 相关项目

- [N.E.K.O.](https://github.com/Project-N-E-K-O/N.E.K.O) — AI 伴侣平台
- [AnyaDance](https://github.com/anyapipira/AnyaDance) — SteamVR 虚拟全身追踪驱动
