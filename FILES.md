# vr_neko_cat 插件文件说明

> 本文档逐文件说明 vr_neko_cat 插件中每个源文件的作用和职责，方便开发者快速理解代码结构。

---

## 文件清单（按层次）

```
vr_neko_cat/
├── plugin.toml                  # 插件元数据 & 默认配置
├── __init__.py                  # 主入口: 插件注册 / 生命周期 / plugin_entry / LLM Tool
├── config_service.py            # 配置持久化 (JSON 读写)
├── udp_service.py               # UDP 通信层 → AnyaDance
├── pose_service.py              # 6 设备 3D 位姿管理
├── input_service.py             # 控制器输入 (按键/摇杆/扳机/手指)
├── dance_service.py             # VMD 舞蹈文件解析与播放
├── emotion_service.py           # 情感 → 全身姿态映射 (12 种)
├── tracking_service.py          # HMD 注视追踪 (Yaw/Pitch → 四元数)
├── animation_service.py         # 预设动画 (点头/挥手/鞠躬) + 待机 + 音频律动
├── vision_bridge.py             # AI 视觉 → VR 行为桥接
├── vrchat_service.py            # VRChat 专用适配 (手势/移动/FBT 校准)
├── driver_service.py            # AnyaDance 驱动进程管理
├── screen_capture_service.py    # 屏幕截图 (mss/PIL → base64)
├── ui_api.py                    # 统一 API 门面 (参数校验 + 委托)
├── dashboard_service.py         # 仪表板状态聚合
├── FILES.md                     # 本文件
└── README.md                    # 项目简介
```

---

## 逐文件详解

### 1. `plugin.toml` — 插件元数据 & 默认配置

**作用**: 定义插件身份信息、UI 面板入口、所有设备的默认位姿和网络参数。

**核心内容**:
- `[plugin]`: 插件 ID (`vr_neko_cat`)、名称、描述、版本、入口点
- `[plugin.ui.panel]`: 前端控制面板的入口 HTML 和 dashboard 上下文
- `[network]`: UDP 主机 `127.0.0.1:39570`、流送频率 60Hz、最大包大小
- `[hmd_pose] ~ [right_foot_pose]`: 6 个 VR 追踪设备的默认位姿 (位置 + 四元数)
- `[left_controller_input]` / `[right_controller_input]`: 两侧控制器的默认输入状态
- `[left_finger_bends]` / `[right_finger_bends]`: 两侧五指弯曲默认值
- `[dance]`: 舞蹈播放参数 (高度/速度/FPS/手部范围/循环)
- `[vrchat]`: VRChat 角色身高设置
- `[screen_capture]`: 截图默认参数

**关键配置项**:

| 配置项 | 默认值 | 含义 |
|--------|--------|------|
| `host` / `port` | 127.0.0.1 / 39570 | AnyaDance UDP 接收地址 |
| `stream_rate_hz` | 60 | 位姿数据发送频率 |
| `avatar_height` | 1.5 | VRChat 角色身高(m)，影响 FBT 校准偏移 |
| `dance_hand_reach` | 1.22 | 舞蹈时手臂伸展范围倍率 |

---

### 2. `__init__.py` — 主入口: 插件骨架

**类**: `VRControllerPlugin(NekoPluginBase)`

**作用**: 整个插件的核心骨架文件，负责:

1. **组装所有服务**: 在 `__init__` 中实例化 13 个子服务，每个服务通过 `self.plugin` 反向引用访问其他服务

2. **生命周期管理**:
   - `startup()`: 加载配置 → 注册静态 UI → 设置快捷入口 → 捕获基线位姿
   - `shutdown()`: 停止流送/舞蹈/追踪/动画/驱动 → 关闭 UDP socket

3. **60Hz UDP 流送主循环** (`_stream_loop`): 不断调用 `udp_service.send()` 将当前配置中的设备位姿和输入序列化为 JSON 发送给 AnyaDance

4. **AI 通知** (`_notify_ai`): 向 N.E.K.O 消息总线推送通知，让 AI 感知 VR 操作结果

5. **plugin_entry 注册**: 约 50 个 `@plugin_entry` 装饰器，每个对应一个可被 AI/用户调用的功能入口:
   - 流送控制 (2): `start_stream` / `stop_stream`
   - 预设位姿 (2): `apply_preset` / `set_device_pose`
   - 手指/摇杆/按键/手势 (5): `set_finger_bends` / `set_joystick` / `press_button` / `hand_gesture` / `reset_inputs`
   - 舞蹈 (2): `play_dance` / `stop_dance`
   - 镜像 (2): `mirror_hands` / `mirror_feet`
   - 情感 (3): `set_emotion` / `blend_emotions` / `capture_baseline`
   - 追踪 (6): `look_at` / `look_at_direction` / `reset_head` / `start_tracking` / `stop_tracking` / `set_tracking_smooth`
   - 动画 (7): `nod_head` / `shake_head` / `tilt_head` / `wave_hand` / `bow` / `start_idle` / `stop_idle` / `react_to_audio`
   - AI 视觉 (6): `vision_face` / `vision_face_lost` / `vision_expression` / `vision_gesture` / `vision_object` / `vision_config`
   - 截图 (3): `vision_capture` / `vision_capture_monitors` / `vision_capture_config`
   - VRChat 专用 (12): 手势/移动/转向/拾取/放下/跳跃/坐/蹲/握手/FBT校准
   - 驱动管理 (5): 注册/注销/启动/停止/重启 SteamVR/一键启动
   - 状态查询 (3): `get_dashboard_state` / `send_single_packet` / `save_settings`

6. **LLM Tools (22 个)**: `@llm_tool` 装饰器注册的方法，AI 大模型可直接调用:
   - `vr_emotion` / `vr_gesture` / `vr_gesture_both`
   - `vr_walk` / `vr_stop_walk` / `vr_turn`
   - `vr_look_at` / `vr_animation` / `vr_pickup` / `vr_drop`
   - `vr_jump` / `vr_sit` / `vr_crouch` / `vr_handshake`
   - `vr_dance` / `vr_stop_dance`
   - `vr_get_state` / `vr_start_idle` / `vr_stop_idle`
   - `vr_driver_status` / `vr_driver_oneclick`
   - `vr_capture_screen` / `vr_capture_game_window` / `vr_get_window_info`

**依赖关系**: 所有 13 个服务都通过它连接在一起，它是整个插件的"总线"。

---

### 3. `config_service.py` — 配置持久化

**类**: `VrConfigService`

**作用**: 管理插件所有配置的读写。配置文件存储在插件数据目录下的 `config.json`。

**核心方法**:
- `DEFAULTS`: 类变量，定义全部 46 个默认配置项（网络/位姿/输入/手指/舞蹈/视觉/截图/驱动）
- `load()`: 从 JSON 文件读取 → 与 DEFAULTS **深度合并**（`_deep_merge`）→ 保证新增配置项有默认值
- `save()`: 将当前配置写回 JSON 文件
- `update()`: 运行时增量更新配置（深度合并）

**深度合并** (`_deep_merge`): 递归合并两个字典，嵌套字典不会整体被覆盖，而是逐字段合并。这确保用户保存的自定义值不会丢失，同时新版本新增的默认值会被自动补充。

---

### 4. `udp_service.py` — UDP 通信层

**类**: `VrUdpService`

**作用**: 将插件配置中所有设备的位姿和控制器输入，序列化为符合 AnyaDance 协议格式的 JSON 数据包，通过 UDP 发送到 `127.0.0.1:39570`。

**数据包结构**:
```json
{
  "version": 1,
  "devices": {
    "hmd": {"valid": true, "connected": true, "pose": {"position": [...], "rotation_xyzw": [...]}},
    "left_controller": {...},
    "right_controller": {...},
    "hip": {...},
    "left_foot": {...},
    "right_foot": {...}
  },
  "inputs": {
    "left_controller": {"trigger_click": ..., "joystick_x": ..., "finger_bends": {...}},
    "right_controller": {...}
  }
}
```

**核心方法**:
- `build_packet()`: 从配置字典读取 6 设备位姿 + 2 控制器输入 → 组装 JSON 字典
- `_clamp_position()` / `_clamp_rotation()`: 位置限幅 (±10m / Y 上限 2m)、四元数归一化
- `send_sync()`: 同步发送（在 asyncio 线程池中调用以避免阻塞事件循环）
- `send()`: 异步封装，使用 `asyncio.to_thread` 在线程中执行 `send_sync()`

---

### 5. `pose_service.py` — 6 设备 3D 位姿管理

**类**: `VrPoseService`

**作用**: 管理 6 个 VR 追踪设备（HMD / 左右控制器 / 髋部 / 左右脚）的 3D 位置和四元数旋转。

**预设位姿** (`PRESETS`):
| 预设名 | 描述 |
|--------|------|
| `standing` | 标准站姿，双手自然下垂 |
| `t_pose` | T 字形，双手水平展开（常用于 FBT 校准） |
| `menu` | 菜单姿态，手腕抬高到菜单高度 |

**核心方法**:
- `apply_preset()`: 将预设的 7 个值 (px,py,pz,rx,ry,rz,rw) 写入 6 个设备配置
- `set_device_position()` / `set_device_rotation()`: 单独设置某设备的位姿
- `move_relative()`: 相对位移（增量修改位置）
- `rotate_yaw()`: 绕 Y 轴旋转指定度数（用于转向）
- `mirror_hands()` / `mirror_feet()`: 将左手/左脚位姿镜像到右侧

**坐标系**: X=左右(-右+), Y=上下(-下+), Z=前后(-前+)，原点在脚底地面。

---

### 6. `input_service.py` — 控制器输入管理

**类**: `VrInputService`

**作用**: 管理两侧 VR 控制器的按键、扳机、握把、摇杆和五指弯曲值。所有值最终写入配置字典，由 `udp_service.build_packet()` 读取并序列化。

**支持的输入项**:
| 类型 | 字段 | 范围 |
|------|------|------|
| 按键 | trigger_click / menu_click / system_click / a_click / b_click / grip_click | bool |
| 模拟量 | trigger_value / grip_value | 0.0 ~ 1.0 |
| 摇杆 | joystick_x / joystick_y / trackpad_x / trackpad_y | -1.0 ~ 1.0 |
| 手指 | thumb / index / middle / ring / pinky | 0.0(伸直) ~ 1.0(完全弯曲) |

**手势快捷方法** (`_do_gesture`):
| 手势名 | 描述 |
|--------|------|
| `open` | 五指张开 |
| `fist` | 握拳 |
| `point` | 食指指向 |
| `peace` | 剪刀手 |
| `thumbs_up` | 点赞 |
| `rock` | 摇滚手势 |
| `gun` | 手枪手势 |

---

### 7. `dance_service.py` — VMD 舞蹈文件解析与播放

**类**: `VrDanceService`

**作用**: 解析 MMD 标准 `.vmd` 格式的骨骼动画文件，将骨骼帧数据映射到 VR 设备位姿，按帧率驱动 6 设备运动实现跳舞效果。

**文件格式**: VMD 文件以 `"Vocaloid Motion Data 0002"` magic 开头，二进制结构为:
```
[30B magic] [20B model_name] [4B bone_count]
每个骨骼帧: [15B bone_name] [4B frame_no] [3×4B position] [4×4B rotation] [64B interpolation]
```

**骨骼→VR 映射** (`_map_bone_to_vr`):
| MMD 骨骼 | VR 设备 | 基准偏移 |
|----------|---------|---------|
| 頭 / head | hmd | (0, 1.5, 0) |
| 左腕 / left wrist | left_controller | (-0.26, 1.1, -0.54) |
| 右腕 / right wrist | right_controller | (0.27, 1.57, -0.54) |
| 腰 / hip | hip | (0, 1.07, -0.05) |
| 左足 / left ankle | left_foot | (-0.09, 0.26, 0.1) |
| 右足 / right ankle | right_foot | (0.09, 0.26, 0.1) |

**播放循环** (`_play_loop`): 逐帧 → `apply_frame()` 应用位姿 → UDP 发送 → 支持循环

**配置参数**: `dance_height`(角色身高偏移)、`dance_speed`(倍速)、`dance_hand_reach`(手部伸展范围)、`dance_loop`(循环播放)

---

### 8. `emotion_service.py` — 情感 → 全身姿态映射

**类**: `VrEmotionService`

**作用**: 将 12 种情感映射为 HMD 和双手控制器的位置/旋转偏移，驱动 VRChat 角色表现出对应的身体语言。

**12 种情感预设** (`EMOTION_PRESETS`):
| 情感 | HMD 变化 | 手臂变化 | 手势 |
|------|---------|---------|------|
| happy | 抬头 +0.05, 微偏头 | 手臂上扬 | open |
| sad | 低头 -0.1, 微偏头 | 手臂下垂、内收 | open |
| angry | 微抬头, 偏头 | 手臂外展 | fist |
| surprised | 抬头 +0.08 | 手臂大幅上扬展开 | open |
| scared | 低头 +0.1, 后缩 | 手臂内收 | open |
| excited | 抬头 +0.1, 大幅度偏头 | 手臂高举 | open |
| shy | 低头 -0.05, 歪头+偏转 | 手臂贴近身体 | fist |
| confident | 抬头 +0.06, 偏头 | 手臂微展 | thumbs_up |
| relaxed | 自然, 微偏头 | 手臂自然下垂 | open |
| curious | 微抬头, 探身+偏头 | 手臂微前 | point |
| tired | 低头 -0.08 | 手臂大幅下垂 | open |
| neutral | 无偏移 | 无偏移 | open |

**核心方法**:
- `capture_baseline()`: 捕获当前所有设备位姿作为"基线"——情感偏移在此之上叠加
- `apply_emotion()`: 将情感预设的偏移量乘以 `intensity`(0~1)，线性插值叠加到基线
- `blend_emotions()`: 按 `ratio` 混合两种情感，ratio=0 纯 A，ratio=1 纯 B

**注意**: 情感只影响 HMD 和双手，不影响髋部和脚部。

---

### 9. `tracking_service.py` — HMD 注视追踪

**类**: `VrTrackingService`

**作用**: 将世界 3D 坐标转换为 HMD 的 Yaw/Pitch 旋转角度 → 四元数 → 设置到 HMD 旋转，实现"注视目标"效果。支持平滑插值和 60Hz 持续追踪。

**核心逻辑**:
1. `_compute_look_at()`: 从 HMD 位置计算到目标点的 Yaw/Pitch，Pitch 限制在 ±60°
2. `look_at()`: 平滑插值当前角度 → 目标角度（`_lerp_factor` 控制平滑度）→ 转换为四元数写入 HMD
3. `look_at_direction()`: 直接指定 Yaw/Pitch 角度（而非世界坐标）
4. `_track_loop()`: 60Hz 持续追踪循环

**平滑系数** (`_lerp_factor`): 默认 0.12，值越小越平滑但越慢，值越大越灵敏但可能抖动。

---

### 10. `animation_service.py` — 预设动画动作

**类**: `VrAnimationService`

**作用**: 提供一系列预设的 VR 角色动画动作，通过周期性地修改设备位姿/旋转来实现。

**动画类型**:
| 动作 | 方法 | 实现原理 |
|------|------|---------|
| 点头 | `nod_head()` | HMD rotation_x 正弦振荡 ±15° |
| 摇头 | `shake_head()` | HMD rotation_y 正弦振荡 ±20° |
| 歪头 | `tilt_head()` | HMD rotation_z 偏转，1.5s 后自动恢复 |
| 挥手 | `wave_hand()` | 控制器 rotation_z 交替摆动 ±35°，3 种风格 |
| 鞠躬 | `bow()` | HMD 前倾 + 髋部后移 + 下降，0.8s 停留恢复 |

**待机循环** (`_idle_loop`, 30Hz):
- 正弦呼吸起伏: HMD position_y 以 0.008m 幅度持续微动
- 身体微晃: 髋部 position_x 正弦摆动 + rotation_z 微转

**音频律动** (`react_to_audio()`): 接收音频 level (0~1)，按比例驱动 HMD 和双手 Y 轴微动

---

### 11. `vision_bridge.py` — AI 视觉 → VR 行为桥接

**类**: `VrVisionBridge`

**作用**: 将摄像头/屏幕分析结果（人脸检测、表情识别、手势识别、物体检测）转换为 VR 角色的对应行为。

**桥接映射**:
| AI 检测输入 | → | VR 行为 |
|------------|---|---------|
| 人脸屏幕坐标 | → | `tracking.look_at()` 注视人脸世界位置 |
| 表情 (happy/sad/angry/...) | → | `emotion.apply_emotion()` 设置对应情感 |
| 人体关键点 (手腕) | → | `pose.set_device_position()` 映射到手部 |
| 手势 (open/fist/point/...) | → | `input._do_gesture()` 映射到手指弯曲 |
| 物体类型+位置 | → | `tracking.look_at()` 注视物体 |
| 人脸丢失 | → | 进入自动环视模式 |

**自动环视** (`_auto_look_loop`, 15Hz): 当无检测到人脸时，HMD 以正弦扫描 ±30°，模拟自然环顾四周的行为。

**视觉配置**: `camera_fov_h/v`(相机视场角)、`tracking_smooth`(平滑度)、`look_distance`(默认注视距离)、`react_to_expression/gesture`(是否响应表情/手势)

---

### 12. `vrchat_service.py` — VRChat 专用适配

**类**: `VrChatService`

**作用**: 提供 VRChat 特定的上层功能，包括标准手势、移动控制、FBT 校准和交互辅助。

**VRChat 8 种标准手势** (`VRC_GESTURES`): neutral / fist / hand_open / point / peace / rock / gun / thumbs_up —— 每个是五指弯曲值的组合

**移动控制**:
- `walk()`: 通过左摇杆控制前后左右移动
- `turn()`: 通过右摇杆控制视角转向
- `walk_for()`: 定时移动，duration 秒后自动停止
- `stop_locomotion()`: 停止所有移动

**FBT 校准** (`calibrate_fbt()`): 根据角色身高 (short 1.2m / medium 1.5m / tall 1.8m / tower 2.0m) 按比例缩放 6 个设备的基准偏移

**预设姿态**:
- `sit()`: 坐姿 → 降低 HMD/髋部/手臂高度 + 脚部前移
- `crouch()`: 蹲姿 → 大幅降低 HMD 和髋部
- `handshake()`: 握手 → 伸手到前方 → 张开 → 1 秒后握拳

**交互**: `pickup()`(握把+扳机=1)/`drop()`(握把+扳机=0)/`jump()`(A 键)/`use_action()`(A 键)/`open_menu()`(菜单键)

---

### 13. `driver_service.py` — AnyaDance 驱动进程管理

**类**: `VrDriverService`

**作用**: 管理 AnyaDance.exe 的完整生命周期（查找→注册→启动→停止→注销），以及 SteamVR 相关操作。

**目录查找** (`_anyadance_dir`): 5 级优先级搜索
1. 用户配置的 `anyadance_path`
2. 插件内置 `anyadance/` 目录
3. 工作区上级 `anyadance/`
4. 环境变量 `ANYADANCE_ROOT`
5. 当前目录下的 `anyadance/`

**SteamVR 驱动注册**: 通过 `vrpathreg.exe adddriver` 向 SteamVR 注册 AnyaDance 为虚拟追踪设备驱动；通过 `removedriver` 注销

**进程管理**:
- `start_anyadance()`: 先确保驱动已注册 → `subprocess.Popen` 启动 AnyaDance.exe
- `stop_anyadance()`: 先 `terminate()` → 超时则 `kill()` → 最后用 `taskkill /F` 强杀残留
- `restart_steamvr()`: taskkill 强制结束 vrserver/vrmonitor/vrcompositor → 通过 `steam://run/250820` 重新启动

**状态查询**: `get_driver_state()` 返回驱动路径/运行状态/注册状态/UDP 监听状态

**UDP 端口检测** (`_check_udp_port`): 发送空包到 39570 端口，收到 `ConnectionRefused` 表示端口已被 AnyaDance 占用

---

### 14. `screen_capture_service.py` — 屏幕截图

**类**: `VrScreenCapture`

**作用**: 截取屏幕画面并编码为 base64，供 AI 视觉模块"看到" VRChat 游戏画面进行自主分析。

**双后端支持**:
- **mss** (优先): 更快，支持多显示器、区域截图
- **PIL/ImageGrab**: 备选方案

**截图模式**:
| 方法 | 描述 |
|------|------|
| `capture()` | 全屏/指定显示器截图 |
| `capture_active_window()` | 截取前台窗口区域（不含 NEKO 覆盖层） |
| `capture_game_region()` | 截取指定屏幕坐标区域 |

**输出**: 返回包含 `image_base64`(JPEG/PNG base64)、`width`/`height`、`size_kb`、`elapsed_ms` 的字典

**前台窗口检测**: 通过 Windows API (`GetForegroundWindow` / `GetWindowRect` / `GetWindowTextW`) 获取当前活动窗口的位置和标题

---

### 15. `ui_api.py` — 统一 API 门面

**类**: `VrUiApi`

**作用**: 所有 `plugin_entry` 的调用入口层，负责:
1. 参数校验（side 必须为 left/right，button 必须在合法列表中）
2. 结果包装（成功用 `Ok()`，失败用 `Err(SdkError(...))`）
3. 委托底层服务执行实际逻辑

**设计模式**: 门面模式 (Facade) —— `__init__.py` 中 50 个 plugin_entry 方法 → 统一调用 `ui_api.xxx()` → 转发到底层服务。这样就把"参数校验 + 错误包装"和"业务逻辑"分开了。

**典型流程**:
```
用户/AI 调用 plugin_entry → __init__.py 方法 → ui_api.press_button(side, button, pressed)
  → 校验 side/button 合法性 → Err(SdkError) 或 → input_service.set_button() → Ok({...})
```

---

### 16. `dashboard_service.py` — 仪表板状态聚合

**类**: `VrDashboardService`

**作用**: 聚合所有 12 个子服务的状态，构建统一的仪表板数据，供前端 UI 面板展示。

**聚合内容**:
| 分类 | 来源服务 | 内容 |
|------|---------|------|
| driver | driver_service | AnyaDance 运行/注册状态 |
| connection | config | 主机/端口/流送频率/流送状态 |
| devices | pose_service | 6 设备的 position + rotation |
| inputs | input_service | 按键/摇杆/手指弯曲 |
| dance | dance_service | 播放状态/当前帧/总帧数 |
| emotion | emotion_service | 当前情感/强度/可用列表 |
| tracking | tracking_service | 追踪状态/目标/Yaw/Pitch |
| animation | animation_service | 待机状态/呼吸相位 |
| vision | vision_bridge | 人脸/表情/手势/自动环视 |
| screen_capture | screen_capture | 截图配置/显示器列表 |
| vrchat | vrchat_service | 角色身高/移动状态/手势列表 |
| settings | config | 镜像/UI/校准等设置项 |

**`save_settings()`**: 将前端传入的 KV 分类写入配置（简单值/位姿/输入/手指弯曲）→ 持久化到 JSON

---

## 整体数据流

```
用户 / AI (LLM Tool)
  │
  ▼
__init__.py  (plugin_entry / llm_tool 装饰器)
  │
  ├─► ui_api.py       (参数校验 + Ok/Err 包装)
  │     ├─► pose_service.py        (位姿 → config 字典)
  │     ├─► input_service.py       (输入 → config 字典)
  │     ├─► dance_service.py       (VMD → 逐帧位姿)
  │     ├─► emotion_service.py     (情感 → 位姿偏移)
  │     ├─► tracking_service.py    (坐标 → HMD 旋转)
  │     ├─► animation_service.py   (动画 → 周期位姿)
  │     ├─► vision_bridge.py       (视觉 → VR 行为)
  │     ├─► vrchat_service.py      (VRC 专属功能)
  │     ├─► driver_service.py      (进程/注册表)
  │     └─► screen_capture.py      (截图 → base64)
  │
  ├─► udp_service.py   (config 字典 → AnyaDance 协议 JSON)
  │     ▼
  │    UDP 127.0.0.1:39570
  │     ▼
  │   AnyaDance.exe  →  SteamVR 驱动  →  VRChat
  │
  ├─► dashboard_service.py  (聚合所有状态 → 前端 UI)
  └─► config_service.py     (配置读写 → config.json)
```
