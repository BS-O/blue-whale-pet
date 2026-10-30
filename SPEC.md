# 蓝鲸桌宠（Blue Whale Pet / 蓝色大肥鱼）工程契约 v1

> 本文件是 Lead / pet-core / asset-fish / pack-win / pack-linux 共同遵守的接口契约。
> 修改契约前必须先通知 Lead；本文件由 Lead 维护。

## 1. 产品定位

基于 DeepSeek「蓝色大肥鱼（蓝鲸）」形象的 Windows / Linux 桌面宠物：
- 常驻桌面（置顶，无边框，透明），后台托盘常驻，低内存。
- 会说话：DeepSeek API（`https://api.deepseek.com`，OpenAI 兼容 `/chat/completions`，支持流式）；
  言简意赅，默认回复 1~2 句、不超过 60 字，可有语气词/颜文字。
- 多表情：idle/blink/happy/laugh/talk/think/sleep/surprise/sad/angry/love/drag/wave/eat。
- 互动：左键戳 → 表情+短句；双击 → 聊天气泡；右键拖拽 → 移动；滚轮 → 快速缩放；
  托盘右键 → 设置菜单（设置窗口、显示/隐藏、大小、开机自启、关于、退出）。
- 打包：Windows 便携单 exe；Windows 安装版（Exe 安装器 + 卸载）；Debian `.deb`；Arch `PKGBUILD` + 预构建 `pkg.tar.zst`。

产品名：**蓝鲸桌宠**（副标题：蓝色大肥鱼 / DeepSeek 桌宠）
英文可执行名：`BlueWhalePet`；包名：`blue-whale-pet`；版本：`1.0.0`。

## 2. 目录结构与写入范围（严格，禁止越界写）

```
blue-whale-pet/
├── SPEC.md  README.md  LICENSE  .gitignore        # Lead
├── src/  tests/                                   # pet-core
├── assets/  tools/                                # asset-fish
├── packaging/windows/  release/windows/           # pack-win
├── packaging/linux/    release/linux/             # pack-linux
├── docs/  qa/  release/*.md                       # Lead
└── release/                                       # 子目录按成员划分
```

共享只读：任何人可读全部文件，但只写自己范围内文件。跨范围需求用消息通知对方或 Lead。

## 3. 运行时技术约束

- Python **3.11**（Windows 构建），兼容 Python ≥ 3.9 语法。
- UI：`tkinter`（Tk 8.6），无边框窗口 `overrideredirect(True)`，置顶。
- 图像：**Pillow (PIL) ≥ 9** 运行时使用（缩放、透明、X11 形状、托盘图标）；`ImageTk` 用于 Tk 显示。
  运行时禁止依赖 numpy / PyQt / requests / pystray（Linux 的 pystray 为可选）。
- 网络：仅标准库 `urllib.request`（HTTPS + SSE 流式解析），禁止 requests。
- 线程：所有网络请求在 daemon 线程，UI 更新经 `after()` 回主线程。
- 资源：`src/resources.py` 统一解析资源路径：
  - 开发模式：项目根 `assets/`；冻结模式：`sys._MEIPASS/assets`。
  - `is_portable()`：冻结且 `sys._MEIPASS/portable.flag` 存在 → 便携模式（数据在 exe 同级 `BlueWhalePet-Data/`，不可写时回退 `%APPDATA%`）。
- 单实例：Windows 用命名 Mutex（ctypes），Linux 用 `$XDG_RUNTIME_DIR` 锁文件；二启时唤醒已有实例。
- 日志：数据目录 `logs/app.log`，`logging.handlers.RotatingFileHandler`，1MB×2。
- 内存目标：Windows 便携版常驻 Working Set ≤ 60MB（验收记录实测值）。
- 禁止在源码/资产中出现明文 API Key；Key 仅用户本机配置。

## 4. 资产契约（asset-fish 产出，pet-core 消费）

### 4.1 主精灵（必需）
- 画布：**512×512 RGBA PNG**，角色**居中**，锚点 `(256,496)`（脚底中心），任意表情/帧的角色主体包围盒误差 ≤ 6px，禁止抖动。
- 目录：`assets/mascot/master/<state>_<frame>.png`（全小写，`frame` 从 0 起）。
- 清单：`assets/mascot/manifest.json`，格式：
```json
{
  "version": 1,
  "canvas": {"w": 512, "h": 512, "anchor_x": 256, "anchor_y": 496},
  "key_color": "#010203",
  "default_state": "idle",
  "states": {
    "idle":    {"frames": ["idle_0","idle_1","idle_2","idle_3"], "durations": [420,420,420,420], "loop": true},
    "blink":   {"frames": ["blink_0","blink_1","blink_2"], "durations": [60,90,60], "loop": false},
    "...":     {}
  }
}
```
- 必需 state（14 个，每个 2~5 帧）：`idle, blink, happy, laugh, talk, think, sleep, surprise, sad, angry, love, drag, wave, eat`。
- 美术要求：以 DeepSeek 官方蓝鲸 logo 为轮廓基础做二创（更圆更肥、加粗描边、大眼睛、腮红），品牌蓝 `#4D6BFE`，描边深藏青 `#0B1330`，边缘全为深色描边（便于 Windows 色键透明）。透明背景，禁止半透明大面积阴影贴边。

### 4.2 图标与插画（必需）
- `assets/icons/app.ico`：多尺寸 256/128/64/48/32/16。
- `assets/icons/app.png`：512×512 RGBA（Linux/关于页）。
- `assets/icons/tray.ico`：16/32/48 多尺寸（Windows 托盘）。
- `assets/icons/blue-whale-pet.svg`：矢量图标（Linux hicolor/scalable）。
- `assets/icons/hicolor/<N>x<N>/apps/blue-whale-pet.png`，N ∈ {16,24,32,48,64,128,256,512}。
- `assets/installer/banner.png`（600×160）、`assets/installer/side.png`（164×314）、`assets/installer/setup.ico`。
- `assets/preview/contact_sheet.png`：全部表情的预览拼图（含中文标签），供文档/验收。

### 4.3 来源与合规
- `assets/source/references/` 保存网络搜集的原始参考图（官方 logo、蓝色大肥鱼梗图等）与来源 URL。
- `assets/source/NOTICE.md`：每张图来源链接、处理方式、版权说明（官方 logo 版权归 DeepSeek，本项目为非官方个人桌面宠物二创，仅供个人使用）。

## 5. 配置契约（pet-core 实现）

文件：`config.json`（UTF-8）+ 原子写（临时文件 + `os.replace`），损坏时回退默认值并备份。
```json
{
  "version": 1,
  "api": {"key": "", "base_url": "https://api.deepseek.com", "model": "deepseek-chat",
          "max_tokens": 120, "temperature": 1.3, "timeout": 30},
  "pet": {"size": 168, "x": null, "y": null, "always_on_top": true,
          "opacity": 1.0, "click_through": false},
  "speech": {"persona": "（内置人设，见 src/prompts.py）", "max_chars": 60,
             "typewriter": true, "bubble_seconds": 7},
  "behavior": {"idle_animation": true, "auto_sleep_seconds": 180, "greet_on_start": true,
               "wheel_resize": true, "click_actions": true},
  "system": {"autostart": false, "tray": true, "language": "zh", "first_run": true}
}
```
- `pet.size` 允许 64~320；`x/y` 为屏幕坐标，越界时夹回可见区域。
- 便携模式路径：exe 同级 `BlueWhalePet-Data/config.json`；安装版：`%APPDATA%\BlueWhalePet\config.json`；Linux：`$XDG_CONFIG_HOME/blue-whale-pet/config.json`。
- 开机自启：Windows `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 值名 `BlueWhalePet`；Linux `~/.config/autostart/blue-whale-pet.desktop`。

## 6. 入口 / CLI 契约（pack-win、pack-linux、QA 依赖）

`src/main.py`：
- 无参数：正常运行。
- `--version`：打印 `蓝鲸桌宠 1.0.0` 后退出。
- `--config PATH`：使用指定配置文件。
- `--selftest`：自动自检（加载 manifest/全部表情、创建宠物窗口、模拟 3 次戳、切换全部表情、创建托盘、设置窗口开合、配置读写往返、可选 API mock），
  约 10s 内退出；成功 stdout 打印 `SELFTEST OK <json摘要>`，失败打印 `SELFTEST FAIL <原因>` 并 exit 1。**必须可在无人工操作下跑完。**
- `--showcase [SECONDS]`：以固定位置循环展示全部表情并显示名字（供截图/验收），到时退出。
- `--debug`：日志输出到 stderr，日志级别 DEBUG。

## 7. 打包契约

### 7.1 Windows（pack-win）
- 便携版：PyInstaller **onefile** → `release/windows/BlueWhalePet-Portable-1.0.0.exe`（含 `portable.flag`、icon=`assets/icons/app.ico`，windowed）。
- 安装版：PyInstaller **onedir** 应用 + 自研安装器（Python/tkinter，PyInstaller onefile，中文向导，嵌入应用 zip 载荷）
  → `release/windows/BlueWhalePet-Setup-1.0.0.exe`。
  - 默认安装目录 `%LOCALAPPDATA%\Programs\BlueWhalePet`（无需管理员）；可选“为所有用户安装”不做。
  - 组件：应用本体、开始菜单快捷方式、可选桌面快捷方式、卸载器（安装器 exe 复制为 `uninstall.exe`，参数 `/uninstall`）、
    `HKCU\...\Uninstall\BlueWhalePet` 卸载注册项、图标 `%LOCALAPPDATA%\Programs\BlueWhalePet\BlueWhalePet.ico`。
  - 静默参数：`/S`（静默安装）、`/D=路径`（自定义目录）、`/uninstall /S`（静默卸载）。
  - 安装器文件名/窗口标题/图标均使用蓝鲸资产。
- 必须实测：便携 exe 双击运行（托盘+宠物出现）、`--selftest` 通过、内存实测、安装/卸载往返、快捷方式、自启开关。
- 构建脚本：`packaging/windows/build_all.ps1`（一键产出上述两 exe；可被 Lead 复跑）。

### 7.2 Linux（pack-linux）
- `.deb`（`release/linux/blue-whale-pet_1.0.0_all.deb`）：源码安装到 `/usr/lib/blue-whale-pet/`，
  启动器 `/usr/bin/blue-whale-pet`（`exec python3 /usr/lib/blue-whale-pet/main.py "$@"`），
  `Depends: python3 (>=3.9), python3-tk, python3-pil, python3-pil.imagetk`，
  `Recommends: python3-pystray`（若 Debian 仓库有；没有则不写）。
  安装 `/usr/share/applications/blue-whale-pet.desktop`（含 StartupWMClass/Autostart 说明）、hicolor 图标、
  man 页可选。卸载干净（postrm 清理缓存/自启项，保留用户配置并提示）。
- Arch：`packaging/linux/arch/PKGBUILD`（source 安装到 /usr/lib/blue-whale-pet，同 deb 布局）+ 用脚本手工构建
  `release/linux/blue-whale-pet-1.0.0-1-any.pkg.tar.zst`（.PKGINFO + .MTREE 可选，zstd 压缩），并给出 `sudo pacman -U` 用法。
- 构建脚本：`packaging/linux/build_linux.sh`（在 WSL Debian 13 中运行，产出 deb + arch 包 + 可选 Linux onefile 单文件版）。
- 必须实测：WSL Debian 13 中 `dpkg -i` 安装、WSLg 下启动、`--selftest` 通过、卸载。

### 7.3 产物命名与 release 目录
```
release/
├── windows/BlueWhalePet-Portable-1.0.0.exe
├── windows/BlueWhalePet-Setup-1.0.0.exe
├── linux/blue-whale-pet_1.0.0_all.deb
├── linux/blue-whale-pet-1.0.0-1-any.pkg.tar.zst
├── linux/PKGBUILD
├── SHA256SUMS.txt
└── README.md（Lead 汇总：文件说明、安装方法、校验值）
```
所有产物最终由 Lead 复核，`release/SHA256SUMS.txt` 由 Lead 统一生成。

## 8. 验收标准（QA / Lead）

1. `src/main.py --selftest`：Windows 开发态、Windows 便携 exe、WSL Debian 安装态 均 OK。
2. 便携 exe：双击后 3s 内宠物出现；托盘图标可右键出菜单；设置窗口可打开/保存并立即生效（大小/置顶/自启/模型/Key）。
3. 表情 ≥ 10 个可被触发；戳一戳有气泡短句；双击聊天可流式输出（无 Key 时给出友好提示与内置短句，不崩溃）。
4. 右键拖拽移动后位置持久化，重启后恢复；滚轮缩放即时生效并持久化。
5. 内存：便携版空载 Working Set ≤ 60MB（记录实测），安装版 ≤ 65MB。
6. 安装版安装→桌面/开始菜单快捷方式→卸载 全流程无残留（安装目录、注册项、自启项）。
7. `.deb` 在 WSL Debian 13 `dpkg -i` 安装成功、`blue-whale-pet --selftest` OK、`dpkg -r` 卸载干净；Arch 包结构与 PKGBUILD 通过静态校验（无法在 Windows 上跑 pacman 需说明）。
8. 文档：README（中文，功能/截图/使用/API Key 配置/构建/FAQ/免责声明）、docs/USAGE.md、docs/BUILD.md、release/README.md 完整。
9. 无明文密钥、无构建残留临时文件；release/SHA256SUMS.txt 覆盖全部产物。

## 9. 沟通约定

- 任务在共享任务板跟踪；完成关键里程碑用消息向 Lead 汇报（简短：做了什么、产物路径、验证结果、阻塞）。
- 构建/测试命令必须可复现，写进对应 README 或脚本，不依赖一次性终端操作。
- 遇到跨范围修改需求：先发消息，不要直接改别人文件。
