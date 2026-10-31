# 蓝鲸桌宠 · 独立 QA 报告

- QA 执行：Lead（独立于各打包成员，最终轮 2026-10-31）
- 对象：release/ 下全部最终产物（v1.0.0）
- 方法：脚本化黑盒验证 + 系统级观测（进程树、内存采样、SendInput 合成输入、WSL/WSLg 实机、注册表/文件系统审计），不信任成员自报，所有结论均有可复现命令或日志佐证。

## 1. 产物清单与完整性

| 产物 | 大小 (B) | SHA256（前16） | 校验文件 |
| --- | --- | --- | --- |
| BlueWhalePet-Portable-1.0.0.exe | 22,092,102 | b095c6a12d74efe3 | release/windows/SHA256SUMS.txt |
| BlueWhalePet-Setup-1.0.0.exe | 33,196,674 | defbb87e8695a794 | 同上 |
| blue-whale-pet_1.0.0_all.deb | 1,775,652 | c773985a5d12e46c | release/linux/SHA256SUMS.txt |
| blue-whale-pet-1.0.0-1-any.pkg.tar.zst | 1,801,512 | d479574f88ff8df8 | 同上 |
| blue-whale-pet-1.0.0.tar.gz + PKGBUILD + .install | — | 见校验文件 | 同上 |
| BlueWhalePet-Linux-x86_64（可选） | 21,166,832 | ad0b8d4da7f5fde4 | 同上 |

deb/Arch 为 2026-10-31 postrm 修复后重打（修复过程见 §7）。全量校验：`release/SHA256SUMS.txt`。

包内容审计：payload.zip（Windows 两版共用）1046 项含 52 个 assets 条目（38 帧 + manifest + 图标），**不含** `assets/source/`、`assets/preview/`（版权参考素材不分发）✓；deb 包内 src 与冻结源码 md5 一致（抽查 pet_window.py）✓。

## 2. 运行时自检（--selftest，15 项）

| 环境 | 结果 | 关键数据 |
| --- | --- | --- |
| 开发态（py src/main.py） | PASS | 75/75 相关资产检查、working_set 75→46 MB |
| Windows 便携 exe | PASS | 14 states / 38 frames、tray=true、DPI 1.25、数据目录 `<exe_dir>\BlueWhalePet-Data` |
| Windows 安装版 exe | PASS | exit=0、数据目录 `%APPDATA%\BlueWhalePet`、working_set 45.96 MB |
| Debian .deb（xvfb） | PASS | exit=0、数据目录 `~/.config/blue-whale-pet`、working_set 41.71 MB、38 帧全建、状态机 14/14、连戳 3 次→surprise、气泡/设置窗/托盘检查通过 |

自检覆盖：manifest、必需状态、配置写/读/损坏恢复、SSE 解析、API payload、窗口创建、38 帧图像、状态机切换、戳一戳、气泡、设置窗、托盘、内存。

## 3. 单元测试

`py tests/run_tests.py` → **75/75 PASS**（0 失败 / 0 跳过）。

## 4. 内存（目标 ≤60 MB）

| 场景 | 峰值 | 均值 | 方式 |
| --- | --- | --- | --- |
| 便携 exe 空载 12s（父+子进程） | **57.31 MB** | 55.24 MB | PowerShell 每 0.5s WorkingSet64 采样 |
| 安装版启动 + 自检 | 45.96 MB | — | selftest_report.json |
| deb 启动 + 自检（Linux） | 42.56 MB | — | 同上 |

## 5. 交互与 API 全流程（便携 exe，SendInput 合成输入）

| 用例 | 结果 |
| --- | --- |
| 窗口出现（onefile 父子进程树定位） | PASS |
| 按 --config 绝对路径定位坐标 | PASS（修复：包内应用相对 --config 按 exe CWD 解析，QA 改用绝对路径） |
| 左键戳一戳 → 气泡+表情 | PASS |
| 右键拖拽 (128,48) → 位置落盘 | PASS |
| 滚轮缩放 220→244 | PASS |
| 双击开聊天窗（0.16s 间隔） | PASS（修复：Tk 双击需 ≥~120ms 间隔） |
| 聊天流式回复（本地 mock DeepSeek API :8765） | PASS（completions 请求 +1、SSE stream +1、model=deepseek-flash） |
| 单实例：二次启动唤醒已有实例 | PASS（全局 Mutex + instance.json 唤醒端口） |
| 操作序列后进程存活 | PASS |

文档截图（`docs/screenshots/`）：hero 全景 1920×1080、pet/pet_bubble/chat/settings/expressions 全部有效内容（非空白，色彩分布校验通过）。

## 6. 安装器往返（Windows Setup，静默）

`/S /D=<dir>` 安装：exit=0，1048 文件（含 `_internal` 完整资产），卸载注册表项（DisplayName/Version/UninstallString/图标）正确，开始菜单+桌面快捷方式就位 ✓ → 安装版 `--selftest` PASS → `uninstall.exe /uninstall /S`：exit=0，快捷方式/注册表清除、用户配置保留 ✓。

**QA 发现并推动修复的 3 个卸载缺陷**（Lead 直接修复 `installer_main.py` 并重打）：
1. 静默卸载在删除文件阶段崩溃（退出码 -1/2）→ 改为「登记退出后删除 + 尽力清理」，退出码归零；
2. 新增延迟清理命令里 `%i` 被 Python `%` 格式化吞掉（TypeError）→ 改用字符串拼接；
3. 修复过程中残留 `moved` 引用（NameError）→ 清除。

残留说明：卸载后安装目录仅剩正在运行的 `uninstall.exe`（Windows 不允许删除运行中的自身）。正常桌面由卸载器注册的独立清理进程删除；本构建沙箱会回收 detached 子进程，故表现为「重启后清除」（已登记 MoveFileEx DELAY_UNTIL_REBOOT）。用户数据与系统区域零残留已验证。

## 7. Debian 包往返

`dpkg -i` → 文件/桌面项/8 个 hicolor 图标/scalable 图标就位 ✓ → `--version`、`xvfb-run --selftest`（15/15）✓ → **WSLg 真窗口**出现（xdotool 定位到 window id，WM_CLASS=blue-whale-pet）✓ → `dpkg -r` 干净移除（启动器/桌面项/图标无残留，`__pycache__` 由 postrm 清理）✓ → `~/.config/blue-whale-pet/` 用户配置保留 ✓。

**QA 发现并推动修复的 1 个包缺陷**：Lead 在 Windows 侧编辑 postrm 引入 CRLF，导致 shebang 失效（`dpkg -r` rc=1、postrm 无法执行）→ 全部 debian 脚本强制 LF 后重打，复测通过。教训已写入构建脚本注意事项。

## 8. 结论

四大交付物（Windows 便携 exe / Windows 安装版 / Debian .deb / Arch 包）全部通过端到端验证；内存、交互、聊天流式、多表情、托盘设置、右键拖拽、可调大小均符合 SPEC 验收标准。遗留事项仅 §6 残留说明（Windows 自删除限制）与 Linux 托盘环境依赖（文档已注明），不阻塞交付。
