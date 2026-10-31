# 设计说明（DESIGN）

本文记录「蓝色大肥鱼」的架构、关键实现决策与取舍。工程接口契约见 `SPEC.md`，构建方法见 `BUILD.md`，使用说明见 `USAGE.md`。

## 1. 总体架构

```
┌──────────────────────────── 桌面宠物进程（常驻托盘） ────────────────────────────┐
│                                                                                  │
│  main.py ── CLI 解析 ──► app.PetApp（Tk 主线程）                                 │
│     │                      │                                                     │
│     │                      ├── resources.py  资产/数据目录路径（便携/安装/Linux） │
│     │                      ├── config.py     config.json 深合并/校验/原子写       │
│     │                      ├── anim/         读 manifest.json，表情帧与状态机     │
│     │                      ├── pet_window.py 无边框置顶透明宠物窗 + 交互绑定      │
│     │                      ├── bubble.py     气泡（打字机、自动消失、跟随宠物）   │
│     │                      ├── chat.py       聊天气泡/输入框，SSE 流式渲染        │
│     │                      ├── settings_window.py 设置窗口（大小/模型/Key/自启…） │
│     │                      ├── tray_win.py   Windows 原生托盘（ctypes）           │
│     │                      ├── tray.py       Linux 托盘（pystray 可选，可降级）   │
│     │                      ├── platform_win.py / platform_linux.py  DPI/透明/X11  │
│     │                      ├── single_instance.py  单实例（Mutex/锁文件）         │
│     │                      ├── autostart.py  开机自启（HKCU Run / .desktop）      │
│     │                      └── logging_setup.py  RotatingFileHandler              │
│     │                                                                            │
│     └── api.py ──urllib.request──► DeepSeek API（/chat/completions，SSE 流式）    │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**技术选型**：Python 3.11 + tkinter + Pillow。理由：
- 低内存：Tk+Pillow 空载 Working Set 实测约 45MB（Electron 方案通常在 150MB 以上）；
- 跨平台：同一套代码跑 Windows / Debian / Arch，Tk 8.6 系统自带，Linux 包依赖少；
- 打包成熟：PyInstaller 支持 Windows 单 exe 与 Linux；
- 无重型运行时：网络仅用标准库 `urllib.request`，不引入 requests/Qt/numpy。

## 2. 透明与窗口

| 平台 | 方案 | 备注 |
| --- | --- | --- |
| Windows | Tk `-transparentcolor #010203` + Pillow 把精灵合成到色键背景 | 资产轮廓为深色描边，色键边缘无浅色脏边；无需逐像素 alpha 合成 |
| Linux | X11 SHAPE 扩展（ctypes 调 libX11/libXext）按 alpha 掩码剪裁窗口 | 无合成器也能用；失败自动降级为窗口整体 `-alpha` 半透明 |
| DPI | 启动时 `SetProcessDpiAwareness(2)`（回退 1），`tk scaling = dpi/72` | 配置的 size/x/y 为逻辑像素，实际窗口 = 逻辑 × scale（本机 125% → ×1.25），避免 1080p@125% 下发虚/挤字 |
| 置顶/任务栏 | `overrideredirect(True)` + `-topmost`；托盘为唯一入口 | 无标题栏、不占任务栏；托盘菜单可显示/隐藏、退出 |

## 3. 表情动画

- `assets/mascot/manifest.json` 描述 14 个 state、每帧时长与是否循环；代码**不硬编码帧数/文件名**，换美术只改资产。
- 状态机负责：待机 idle 循环 → 随机眨眼 blink → 定时自动睡眠 sleep；说话时 talk；交互触发 happy/laugh/surprise/angry/love/drag 等，短时后回 idle。
- 帧在内存中以「当前 state × 当前尺寸」懒加载并缓存；切换尺寸时丢弃旧缓存，避免常驻多套大图（低内存关键）。
- 渲染：`PIL.Image.LANCZOS` 缩放到任意尺寸 → `ImageTk.PhotoImage`；Windows 侧先合成到色键背景。

## 4. DeepSeek API 对话

- OpenAI 兼容：`POST {base_url}/chat/completions`，`Authorization: Bearer <key>`，`stream:true`，`thinking:{"type":"disabled"}`（桌宠要秒回，不显示思考链）。
- 现行模型：`deepseek-flash`（默认，快） / `deepseek-v4-pro`（可选）；设置窗口允许自定义模型名与 base_url。
- SSE 解析：增量 UTF-8 解码 + 行缓冲，兼容跨 chunk 多字节字符、`data: [DONE]`、keep-alive 注释、流中 error。
- 人设提示词要求「言简意赅：1~2 句、≤60 字」，回复按 `max_chars` 截断；仅保留最近 8 轮上下文控制 token。
- 错误分类：无 Key / 401 / 402 余额 / 429 限流 / 超时 / 断网 / 服务端错误 → 各自映射为友好中文短句 + 内置兜底台词，**任何情况下不崩溃**。
- API Key 只存本机 `config.json`，不上传、不写日志；README 明确提示不要提交配置。

## 5. 托盘与交互

- **Windows 托盘**：纯 ctypes 调 `Shell_NotifyIconW`，自建隐藏窗口 + 独立消息循环线程；`TrackPopupMenu` 中文菜单；监听 `TaskbarCreated` 重注册（explorer 重启后图标不丢）；退出 `NIM_DELETE`。零第三方依赖（不用 pystray/pywin32）。
- **Linux 托盘**：可选 `pystray`（Debian/Arch 均作为可选依赖），缺失时自动降级为宠物右键菜单，功能不丢失。GNOME 无托盘扩展时同理。
- 交互：左键戳→表情+短句；双击→聊天；右键拖拽→移动（位置持久化）；右键单击→小菜单；滚轮→缩放（64~320 逻辑像素）；设置窗口通过托盘右键打开。

## 6. 配置与数据目录

| 形态 | 配置/日志/自检报告位置 |
| --- | --- |
| 开发态 | `%APPDATA%\BlueWhalePet-Dev`（Windows）/ `~/.config/blue-whale-pet-dev`（Linux） |
| Windows 便携版 | exe 同级 `BlueWhalePet-Data/`（不可写时回退 `%APPDATA%\BlueWhalePet`） |
| Windows 安装版 | `%APPDATA%\BlueWhalePet` |
| deb / Arch | `$XDG_CONFIG_HOME/blue-whale-pet`（默认 `~/.config/blue-whale-pet`） |

配置写入采用「临时文件 + os.replace」原子写；文件损坏时自动备份为 `config.json.bad-<时间戳>` 并回退默认值；未知字段丢弃、越界值夹取。

## 7. 打包矩阵

| 平台 | 产物 | 说明 |
| --- | --- | --- |
| Windows 便携 | `BlueWhalePet-Portable-1.0.0.exe` | PyInstaller onefile/windowed，单文件，内含 `portable.flag`；数据目录在 exe 旁 |
| Windows 安装 | `BlueWhalePet-Setup-1.0.0.exe` | 自研 tkinter 安装向导（PyInstaller onefile，内嵌 onedir 应用 zip）：装到 `%LOCALAPPDATA%\Programs\BlueWhalePet`，开始菜单/可选桌面快捷方式、卸载注册项、`uninstall.exe /uninstall /S` 静默卸载；支持 `/S`、`/D=路径` |
| Debian/Ubuntu | `blue-whale-pet_1.0.0_all.deb` | 源码装到 `/usr/lib/blue-whale-pet`，依赖系统 `python3-tk/python3-pil`，无需 PyInstaller 即可运行；`/usr/bin/blue-whale-pet` 启动器 + `.desktop` + hicolor 图标 |
| Arch | `PKGBUILD` + `blue-whale-pet-1.0.0-1-any.pkg.tar.zst` | 与 deb 相同的 /usr 布局，depends `python/tk/python-pillow` |

为什么 Windows 安装版用 onedir 而不是 onefile：onedir 单进程、启动快、内存更低（无 onefile 引导父进程），同时安装器负责「单文件交付」的体验。便携版为了「单个 exe 随身带」保留 onefile。

## 8. 质量保障

- `src` 内置 `--selftest`（无人工、10s 内、写 `selftest_report.json`），覆盖资产加载、38 帧图像创建、状态机、配置往返/恢复、SSE mock、托盘、设置窗口、戳一戳、内存采样。
- `tests/` 单元测试覆盖配置、manifest、SSE、状态机、CLI、资源路径。
- `qa/` 为 Lead 独立验收工具（不复用队友自测）：资产契约检查、真机截图/蓝色像素检测、内存采样、安装/卸载往返、deb 往返、交互自动化（SendInput + mock API 统计）、发布产物 SHA256。
- 所有验收结论写入 `qa/QA_REPORT.md` 与 `release/*/BUILD_REPORT.md`。
