# vr_neko_cat 插件文件说明

本文档逐文件说明插件的模块职责与结构，方便快速理解代码。

## 文件总览

```
vr_neko_cat/
├── plugin.toml                   # 插件元数据 & 默认配置
├── __init__.py                   # 主入口: 组装服务、生命周期、60Hz 流送循环, LlmToolResult 定义

├── entries.py                    # Mixin: 所有 @plugin_entry 方法
├── llm_tools.py                  # Mixin: 所有 @llm_tool 方法
├── config_service.py             # 配置持久化 (JSON → deep merge → config.json)
├── udp_service.py                # UDP 通信层 (build_packet → socket → AnyaDance)
├── pose_service.py               # 6 设备 3D 位姿管理
├── input_service.py              # 控制器输入管理 (按键/摇杆/扳机/五指; 含 5s 卡键自动释放)
├── animation_service.py          # 预设动画 (点头/挥手/鞠躬/待机/音频律动)
├── dance_service.py              # VMD 舞蹈文件解析与播放
├── emotion_service.py            # 12 种情感 → 全身姿态映射
├── tracking_service.py           # HMD 注视追踪 (坐标 → Yaw/Pitch → 四元数)
├── vision_bridge.py              # AI 视觉 → VR 行为桥接 (人脸→注视, 表情→情感, 手势→手指)
├── vrchat_service.py             # VRChat 专用适配 (手势/移动/坐/蹲/拾取/FBT 校准)
├── driver_service.py             # AnyaDance 驱动进程管理 (注册→启动→停止→注销)
├── screen_capture_service.py     # 屏幕截图 (mss/PIL 双后端 fallback → base64)
├── ui_api.py                     # 统一 API 门面 (参数校验 + Ok/Err 包装)
├── dashboard_service.py          # 仪表板状态聚合 (12 服务 → 统一结构)
├── static/
│   └── index.html                # Web 控制面板 (苹果液态玻璃 UI + 氛围粒子引擎)
├── i18n/                         # 国际化翻译文件
├── docs/                         # 文档
├── FILES.md                      # 本文件
└── README.md                     # 项目简介
```

## 逐文件详解

### `plugin.toml` — 插件元数据 & 默认配置

定义插件身份、UI 面板入口、所有设备的默认位姿和网络参数。包含:
- `[plugin]`: ID/名称/版本/入口点
- `[network]`: UDP 主机 `127.0.0.1:39570`、流送频率 60Hz
- `[hmd_pose] ~ [right_foot_pose]`: 6 个 VR 追踪设备的默认位姿
- `[left/right_controller_input]`: 控制器默认输入状态
- `[left/right_finger_bends]`: 五指弯曲默认值
- `[dance]`: 舞蹈播放参数
- `[vrchat]`: 角色身高设置
- `[screen_capture]`: 截图默认参数

---

### `__init__.py` — 主入口: 插件骨架

**类**: `VrNekoCatPlugin(PluginBase, VrPluginEntries, VrLlmTools)`

采用 **Mixin 组合模式** 拆分职责:
- `VrPluginEntries` (`entries.py`): 所有 `@plugin_entry` 方法
- `VrLlmTools` (`llm_tools.py`): 所有 `@llm_tool` 方法

核心职责:
1. **组装所有服务**: `__init__` 中实例化 13+ 个子服务
2. **生命周期**: `startup()` / `shutdown()` / `on_load` / `on_unload`
3. **60Hz 流送循环** (`_stream_loop`): UDP 发送 + 连接健康监测 + 卡键自动释放
4. **互斥锁** (`_anim_lock` / `_stop_conflicting_modes`): 防止 dance / idle / tracking 冲突
5. **内置类型**: `LlmToolResult` (AI 工具返回值包装)

---



### `entries.py` — 插件入口方法 (Mixin)

**类**: `VrPluginEntries`

约 50 个 `@plugin_entry` 方法，按功能分组:
- 流送控制: `start_stream` / `stop_stream`
- 位姿: `apply_preset` / `set_device_pose`
- 输入: `set_finger_bends` / `set_joystick` / `press_button` / `hand_gesture` / `reset_inputs`
- 舞蹈: `play_dance` / `stop_dance`
- 镜像: `mirror_hands` / `mirror_feet`
- 情感: `set_emotion` / `blend_emotions` / `capture_baseline`
- 追踪: `look_at` / `look_at_direction` / `reset_head` / `start_tracking` / `stop_tracking` / `set_tracking_smooth`
- 动画: `nod_head` / `shake_head` / `tilt_head` / `wave_hand` / `bow` / `start_idle` / `stop_idle` / `react_to_audio`
- 截图: `vision_capture` / `vision_capture_monitors` / `vision_capture_config`
- 驱动管理: 注册/注销/启动/停止/重启 SteamVR / 一键启动
- 状态查询: `get_dashboard_state` / `send_single_packet` / `save_settings`

---

### `llm_tools.py` — AI 可调用工具 (Mixin)

**类**: `VrLlmTools`

22 个 `@llm_tool` 方法，AI 大模型可直接调用:
- 情感: `vr_emotion` / `vr_gesture` / `vr_gesture_both`
- 移动: `vr_walk` / `vr_stop_walk` / `vr_turn`
- 注视: `vr_look_at` / `vr_animation`
- 交互: `vr_pickup` / `vr_drop` / `vr_jump` / `vr_sit` / `vr_crouch` / `vr_handshake`
- 舞蹈: `vr_dance` / `vr_stop_dance`
- 状态: `vr_get_state` / `vr_start_idle` / `vr_stop_idle`
- 驱动: `vr_driver_status` / `vr_driver_oneclick`
- 截图: `vr_capture_screen` / `vr_capture_game_window` / `vr_get_window_info`

---

### `config_service.py` — 配置持久化

**类**: `VrConfigService`

- `DEFAULTS`: 全部 46+ 配置默认值
- `load()`: JSON 读取 → 与 DEFAULTS 深度合并 (`_deep_merge`)
- `save()`: 写回 JSON
- `update()`: 运行时增量更新

---

### `udp_service.py` — UDP 通信层

**类**: `VrUdpService`

- `build_packet()`: config 字典 → AnyaDance 协议 JSON
- 连接健康监测: 10 次连续失败判定断连 → 自动重建 socket
- `send_sync()` / `send()`: 同步 / 异步发送

---

### `pose_service.py` — 位姿管理

**类**: `VrPoseService`

- 6 设备 (HMD/左右控制器/髋部/左右脚) 的 position + rotation 管理
- 预设: `standing` / `t_pose` / `menu`
- `move_relative()` / `rotate_yaw()` / `mirror_hands/feet`

---

### `input_service.py` — 控制器输入管理

**类**: `VrInputService`

- 按键 / 扳机 / 握把 / 摇杆 / 五指弯曲
- 7 种快捷手势: open / fist / point / peace / thumbs_up / rock / gun
- **5 秒卡键自动释放**: `check_stuck_buttons()` 在流送循环中持续监测

---

### `animation_service.py` — 预设动画

**类**: `VrAnimationService`

- 动作: `nod_head` / `shake_head` / `tilt_head` / `wave_hand` / `bow`
- 待机 (`_idle_loop`, 30Hz): 呼吸起伏 + 身体微晃 (从基线偏移)
- 音频律动: `react_to_audio()` 按音高驱动位姿
- 所有动画互斥: 通过 `_anim_lock` 保护

---

### `dance_service.py` — 舞蹈播放

**类**: `DanceService`

- VMD 文件解析: 骨骼帧 → 6 设备映射
- 播放循环: 逐帧 → 应用位姿 → UDP 发送，支持循环
- 重入保护: `_playing` 标志防止多次播放

---

### `emotion_service.py` — 情感映射

**类**: `VrEmotionService`

- 12 种情感 (happy/sad/angry/surprised/scared/excited/shy/confident/relaxed/curious/tired/neutral)
- 情感基线: `capture_baseline()` 捕获当前位姿作为偏移基准
- `blend_emotions()`: 按 ratio 混合两种情感

---

### `tracking_service.py` — 注视追踪

**类**: `TrackingService`

- 3D 坐标 → HMD Yaw/Pitch 四元数
- 平滑插值 (默认 0.12)
- 60Hz 持续追踪循环

---

### `vision_bridge.py` — AI 视觉桥接

**类**: `VrVisionBridge`

| 视觉检测 | → VR 行为 |
|---------|----------|
| 人脸坐标 | → `tracking.look_at()` |
| 表情识别 | → `emotion.apply_emotion()` |
| 手势识别 | → `input._do_gesture()` |
| 物体检测 | → `tracking.look_at()` |
| 人脸丢失 | → 自动环视 ±30° |

---

### `vrchat_service.py` — VRChat 适配

**类**: `VrChatService`

- 8 种 VRChat 标准手势
- 移动: `walk()` / `turn()` / `walk_for()` / `stop_locomotion()`
- 姿态: `sit()` / `crouch()` / `handshake()`
- 交互: `pickup()` / `drop()` / `jump()`
- FBT 校准: `calibrate_fbt()`

---

### `driver_service.py` — 驱动进程管理

**类**: `DriverService`

- 5 级优先级搜索 AnyaDance 目录
- SteamVR 驱动注册/注销 (`vrpathreg.exe`)
- 进程管理: start/stop/restart, kill fallback

---

### `screen_capture_service.py` — 屏幕截图

**类**: `VrScreenCapture`

- 双后端: mss (优先) / PIL (fallback)
- 截图模式: 全屏 / 活动窗口 / 区域截图
- 输出: base64 + 尺寸信息
- PIL 不可用时自动降级为 `_DummyScreenCapture` (无操作空壳)

---

### `ui_api.py` — API 门面

**类**: `VrUiApi`

- 参数校验 (side/button/手指合法性)
- 统一 `Ok()` / `Err(SdkError(...))` 包装
- 转发到底层服务

---

### `dashboard_service.py` — 仪表板聚合

**类**: `DashboardService`

- 聚合 12 个子服务状态 → 统一结构
- `save_settings()`: 前端 KV → config → 持久化

---

### `static/index.html` — Web 控制面板

前端单页应用:
- 苹果液态玻璃风格 (`backdrop-filter: blur(20px) saturate(180%)` + 半透明背景)
- 头部和所有卡片使用玻璃效果
- **氛围粒子引擎**: Canvas 全屏渲染，支持 飘雪 / 樱花 / 细雨 / 星尘
- 右下角 ✨ 按钮切换效果 + 调节密度/速度
- HTTP API 驱动数据刷新 (2 秒轮询)

## 整体数据流

```
用户 / AI (LLM Tool / plugin_entry)
  │
  ▼
VrNekoCatPlugin  (Mixin: entries.py + llm_tools.py)
  │
  ├─► ui_api.py          (参数校验 + Ok/Err → 转发服务)
  │     ├─► pose_service.py         (config 字典)
  │     ├─► input_service.py        (config 字典)
  │     ├─► animation_service.py    (周期位姿写入)
  │     ├─► dance_service.py        (VMD → 逐帧)
  │     ├─► emotion_service.py      (偏移叠加)
  │     ├─► tracking_service.py     (四元数写入 HMD)
  │     ├─► vision_bridge.py        (视觉 → 多服务)
  │     ├─► vrchat_service.py       (多服务组合)
  │     ├─► driver_service.py       (进程/注册表)
  │     └─► screen_capture_service.py (base64)
  │
  ├─► udp_service.py      (config → JSON → UDP)
  │     ▼
  │   AnyaDance.exe → SteamVR → VRChat
  │
  ├─► dashboard_service.py (聚合 → 前端)
  └─► config_service.py   (JSON 持久化)
```
