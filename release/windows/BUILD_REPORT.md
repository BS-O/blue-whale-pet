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

---

## r2 重打（2026-10-31 20:0x，应用更名 + GLM 适配）

- 应用显示名「蓝鲸桌宠」→「**蓝色大肥鱼**」（窗口/托盘/设置/安装器/快捷方式/注册表 DisplayName/.desktop/man 页等 41 处；内部标识符 BlueWhalePet / blue-whale-pet / 注册表键名保持不变，兼容旧配置与升级）。
- 应用图标更换为用户桌面候选图（1/2/3/5.png，4.png 未提供） processed：`tools/gen_icons.py` 抠图（洪泛+连通域切分贴纸表格）→ 品牌风合成 → 全套 ICO/PNG/hicolor/SVG；候选对比图 `docs/screenshots/icon_candidates.png`，切换候选 `py tools/gen_icons.py --pick N`。来源与流程记录于 `assets/source/NOTICE.md`。
- 新增智谱 GLM 平台：设置窗口「平台」下拉（DeepSeek/智谱 GLM），Key 分平台保存（`api.keys`，旧 `api.key` 自动迁移为 DeepSeek Key），切换平台自动带出 Base URL 与模型列表（GLM 预设 `https://open.bigmodel.cn/api/paas/v4`，glm-4.6 / glm-4.5-air / glm-4-flash）。
- 安装器修复：注册表 DisplayName 由拼接式改为纯 APP_NAME（修复重复「蓝色大肥鱼（蓝色大肥鱼）」）。
- 产物（SHA256 前 16）：便携 `c74887eab5599183`（23,040,532 B）、安装版 `173849dca0d12682`（34,144,814 B）；完整值 SHA256SUMS.txt。
- 验证：79/79 单测（新增 4 项 provider 测试）；开发态/便携/安装版 `--selftest` OK（app=蓝色大肥鱼，45.6~47.9MB）；安装器静默安装 1048 文件、DisplayName=蓝色大肥鱼、卸载 exit 0。
- 已知测试怪癖：`Start-Process -Wait` 启动 GUI exe 跑 `--selftest` 会得到退出码 1（托盘线程退出时序），bash 直跑同一 exe 稳定 rc=0——以直跑结果为准。

---

## r3 重打（2026-10-31 20:5x，桌宠本体更换 + 图标 v3）

- **桌宠本体**：assets/mascot/master 全部 38 帧替换为用户 5.png 主体（854×1564 洪泛抠图）
  的形变+符号合成（tools/gen_mascot_images.py），14 状态不变，画布/key/manifest 不变。
- **图标 v3（修模糊）**：候选扩至 1/2/3/4/5 号（4 号为 4.jpg），自动选 5 号头部方形裁切
  （854×813 与本体同源）；占比 0.88 + UnsharpMask + ICO 自 1024 母版直出。
- 产物：便携 `14eb7f2f26f6a820`（26.7MB）、安装版 `f44d43177cb64c57`（37.3MB）。
- 验证：79/79 单测；开发/便携 selftest OK（38 帧全载，44~46MB）；安装器静默装 1048 文件
  （内嵌 38 帧+131KB ICO）、卸载 exit 0。

---

## r4 重打（2026-10-31 21:2x，多素材状态系统 + 右键菜单移除）

- 40 帧（新增 angryalt_0/1）：1.png 七只小鱼分配到 10 个表情状态，5.png 主体保留
  idle/blink/drag，4.jpg 作为 angry_alt（愤怒 50% 抽签），2.png/3.png 作 talk/think 小照片点缀。
- app.py：戳一戳愤怒分支 50% 切 angry_alt；桌宠本体右键不再弹菜单（托盘菜单保留）。
- 产物：便携（29.2MB）/ 安装版（39.8MB）；静默安装 1050 文件（40 帧内嵌）、卸载 exit 0。
