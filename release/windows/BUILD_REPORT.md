# Windows 构建报告（BUILD_REPORT）

- 构建时间：2026-10-30 21:08–21:13（应用），2026-10-31 17:20–18:03（安装器修复与重打）
- 构建机：Windows 11 26100 · Python 3.11.5 · PyInstaller 6.22.3 · 构建临时目录 `E:\pet-build-tmp\pack-win`
- 源码快照：src 冻结版（25 模块 / 7557 行，最终 mtime 2026-10-30 21:04–21:10）+ 资产定稿 v1（2.93 MB）

## 产物

| 文件 | 大小 (bytes) | SHA256 |
| --- | --- | --- |
| BlueWhalePet-Portable-1.0.0.exe | 22,092,102 | B095C6A12D74EFE3857BA1F22C7A1A9BD8F21EFC5F6334227F3063508341FC5C |
| BlueWhalePet-Setup-1.0.0.exe | 33,196,674 | 见 release/windows/SHA256SUMS.txt（以该文件为准） |

完整校验值：`release/windows/SHA256SUMS.txt`、`release/SHA256SUMS.txt`。

## 构建流水线

`packaging/windows/build_all.ps1`：clean → PyInstaller onedir（应用）→ payload.zip（1046 项，仅 mascot/icons，无 source/preview）→ PyInstaller onefile（便携版，含 `portable.flag`）→ PyInstaller onefile（自研 tkinter 安装器，内嵌 payload + banner/side/setup 插画）→ 复制产物 → `icacls /setintegritylevel Medium` → SHA256SUMS。

安装器独有修复（2026-10-31，Lead 在 pack-win 定稿基础上修复静默卸载崩溃）：
1. 静默卸载改为「先登记退出后删除，再做尽力清理」，不再在删除文件过程中崩溃（原先退出码 -1 / 2）；
2. 修复 `%i` 被 Python `%` 格式化吞掉的 bug；
3. 残留的 uninstall.exe 用 `MoveFileEx(DELAY_UNTIL_REBOOT)` 登记重启删除。

## 验证（Lead 独立执行）

| 检查 | 结果 |
| --- | --- |
| 便携版 `--selftest` | **PASS**：`SELFTEST OK`，15 项检查全过，14 states/38 frames，tray=true，DPI 1.25，数据目录 `BlueWhalePet-Data`（随 exe） |
| 便携版内存（12s 采样，父+子） | **PASS**：max 57.31 MB / avg 55.24 MB（≤60 MB 目标） |
| 便携版交互（SendInput 模拟） | **PASS**：窗口出现、戳一戳气泡、右键拖拽（dx128 dy48 落盘）、滚轮缩放 220→244、双击开聊天窗、mock API 流式回复（completions+1 stream+1 model=deepseek-flash）、单实例互斥、操作后存活 |
| 安装器静默安装 `/S /D=%TEMP%\bwpet-inst5` | **PASS**：exit=0，1048 个文件（含 _internal 完整资产），uninstall.exe 就位，HKCU 卸载项（DisplayName/DisplayVersion/UninstallString）正确 |
| 安装版应用 `--selftest` | **PASS**：exit=0，报告写 `%APPDATA%\BlueWhalePet\selftest_report.json`，45.96 MB |
| 安装器静默卸载 `uninstall.exe /uninstall /S` | **PASS**：exit=0，开始菜单/桌面 lnk、HKCU 注册项全部清除，用户配置保留 |
| 卸载残留 | 安装目录残留 1 个 `uninstall.exe`（运行中的自身，Windows 限制）：正常桌面由登记的独立 cmd 清理进程删除；本机构建沙箱会回收 detached 子进程导致该兜底不生效，已额外登记重启删除（MoveFileEx） |
| 完整性标签 | 产物与 release/windows 目录均已设 Medium（避免 OneDrive/Low-IL 下 onefile 无法解压 %TEMP%） |

已知限制：
- 未做代码签名（SmartScreen 会提示未知发布者）；
- 卸载器自删除依赖 detached 子进程（正常桌面可用）；沙箱环境下装目录会留一个 uninstall.exe 直到重启。
