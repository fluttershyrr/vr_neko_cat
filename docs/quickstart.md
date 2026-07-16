# VR N.E.K.O.cat 快速开始

## 1. 启动插件

在 N.E.K.O 插件管理页面找到 **VR N.E.K.O.cat**，点击「重载」或启动按钮。插件启动后会监听本地 UDP 端口（默认 `39570`）。

## 2. 连接 AnyaDance

打开 AnyaDance 程序，确保其 UDP 输出目标设置为：

```
Host: 127.0.0.1
Port: 39570
```

AnyaDance 会发送身体姿态、手势和表情数据到 N.E.K.O，再转发到 SteamVR。

## 3. 启动 SteamVR

确保 SteamVR 已运行，然后插件会注册虚拟追踪器（HMD、左右手柄、髋部、双脚），供 VRChat 进行 FBT 全身追踪。

## 4. 进入 VRChat

- 启动 VRChat 并佩戴 VR 头显或进入桌面模式。
- 选择支持 FBT 的 avatar。
- 打开 VRChat 的镜子或第三方校准工具，确认身体、手部和脚部位置正确。

## 5. 常用设置

- `network.port`：修改 UDP 接收端口，需与 AnyaDance 保持一致。
- `mirror_settings.mirror_hands` / `mirror_settings.mirror_feet`：镜像左右手脚。
- `dance.vmd_path` / `dance.model_path`：加载 MMD 舞蹈文件进行动作同步。

## 6. 注意事项

- 请确保 AnyaDance、N.E.K.O 和 SteamVR 都在同一台电脑上运行，或使用可连通的网络。
- 如果 VRChat 没有识别追踪器，请在 SteamVR 设置中检查追踪器是否被正确枚举。
- 遇到问题时，可查看插件「日志」页面排查错误。
