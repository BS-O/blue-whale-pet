# 使用说明（USAGE）

## 1. 安装 / 启动

| 平台 | 文件 | 使用方法 |
| --- | --- | --- |
| Windows 便携版 | `BlueWhalePet-Portable-1.0.0.exe` | 放到任意目录双击即可，**免安装**；配置/日志在同级 `BlueWhalePet-Data/`（目录不可写时自动回退 `%APPDATA%\BlueWhalePet`） |
| Windows 安装版 | `BlueWhalePet-Setup-1.0.0.exe` | 双击运行安装向导，默认装到 `%LOCALAPPDATA%\Programs\BlueWhalePet`，创建开始菜单快捷方式（可选桌面快捷方式），无需管理员权限 |
| Debian / Ubuntu | `blue-whale-pet_1.0.0_all.deb` | `sudo apt install ./blue-whale-pet_1.0.0_all.deb`（或 `sudo dpkg -i` 后 `sudo apt -f install` 补依赖）；应用菜单里会出现「蓝色大肥鱼」，或终端运行 `blue-whale-pet` |
| Arch / Manjaro | `blue-whale-pet-1.0.0-1-any.pkg.tar.zst` | `sudo pacman -U blue-whale-pet-1.0.0-1-any.pkg.tar.zst`；或用 `PKGBUILD`：`makepkg -si` |

> Windows SmartScreen 可能提示「未知发布者」（未做代码签名）：点击「更多信息 → 仍要运行」。
> 首次启动后桌宠出现在桌面上，**任务栏托盘**出现蓝鲸图标（Windows 11 默认收起，点任务栏 `^` 展开可见）。

## 2. 和桌宠互动

| 操作 | 效果 |
| --- | --- |
| 左键单击宠物 | 戳一戳：随机表情 + 一句短话（本地台词，秒回不耗 API） |
| 左键双击宠物 | 打开「和蓝鲸聊天」窗口，可输入问题，走 DeepSeek API 流式回复 |
| 右键按住拖动宠物 | 移动位置，松手自动保存，下次启动回到原位 |
| 右键单击宠物 | 弹出小菜单（聊天/设置/隐藏/大小/退出） |
| 鼠标滚轮在宠物上 | 快速放大 / 缩小（64~320） |
| 托盘图标右键 | **设置**、聊天、显示/隐藏、大小、置顶、鼠标穿透、开机自启、关于、退出 |
| 聊天窗口 | `Enter` 发送、`Shift+Enter` 换行、`Esc` 关闭；气泡回复自动消失 |

宠物会自己眨眼、呼吸、发呆；长时间不理它（默认 180 秒）会睡着，戳一下就会醒。

## 3. 配置 API Key（可选，支持 DeepSeek / 智谱 GLM）

不填 Key 也能玩（内置互动台词 + 友好提示），但**聊天功能需要 API Key**：

1. 右键任务栏托盘蓝鲸图标 → **设置**；
2. 在「API」标签页**先选平台**：
   | 平台 | 申请 Key | Base URL（预设） | 推荐模型 |
   | --- | --- | --- | --- |
   | DeepSeek | <https://platform.deepseek.com/api_keys> | `https://api.deepseek.com` | `deepseek-flash`（默认）/ `deepseek-v4-pro` / `deepseek-chat` |
   | 智谱 GLM | <https://open.bigmodel.cn/usercenter/apikeys> | `https://open.bigmodel.cn/api/paas/v4` | `glm-4.6`（默认）/ `glm-4.5-air` / `glm-4-flash`（有免费额度） |
3. 填入对应平台的 API Key；**两个平台的 Key 各存一份，切换平台自动带出各自的 Key、模型与 Base URL**；
4. 模型允许手填任意该平台支持的名称；Base URL 如使用代理/中转可改（需保留 OpenAI 兼容路径）；
5. 点「测试连接」确认可用，再「保存」。

Key 只保存在本机配置文件里，不会上传到除 DeepSeek API 之外的任何地方；日志不会记录 Key。

## 4. 设置项说明

| 标签页 | 设置 | 说明 |
| --- | --- | --- |
| API | 平台 / API Key（分平台保存）/ 模型 / Base URL / 超时 / max_tokens / temperature | 聊天能力配置；「测试连接」会发一次最小请求验证 |
| 外观 | 大小滑杆 / 不透明度 / 置顶 | 大小 64~320 逻辑像素，立即生效并保存 |
| 互动 | 空闲动画 / 自动睡眠秒数 / 气泡显示时长 / 滚轮缩放 / 点击互动 / 开机自启 | 自启为当前用户级（Windows 注册表 Run / Linux autostart） |
| 人设 | 自定义人设提示词 / 回复字数上限 | 默认人设：软萌蓝鲸、言简意赅 ≤60 字 |
| 更多 | 测试连接 / 打开数据目录 / 关于 / 恢复默认 / 保存 / 取消 | 「打开数据目录」可查看 config.json 与 logs/app.log |

## 5. 数据目录

| 形态 | 路径 |
| --- | --- |
| Windows 便携版 | exe 同级 `BlueWhalePet-Data\`（`config.json`、`logs\app.log`） |
| Windows 安装版 | `%APPDATA%\BlueWhalePet\` |
| Debian / Arch | `~/.config/blue-whale-pet/` |

卸载不会删除用户配置（便于重装保留设置）；如要彻底清理，手动删除上述目录即可。

## 6. 命令行（排障用）

```text
blue-whale-pet --version          # 版本
blue-whale-pet --debug            # 前台运行并输出 DEBUG 日志（Linux 终端排障）
blue-whale-pet --selftest         # 自检：写入 <数据目录>/selftest_report.json，退出码 0 表示通过
blue-whale-pet --dump-config      # 打印解析后的配置 JSON（不含 Key 掩码处理，注意不要外发）
blue-whale-pet --showcase 10      # 循环展示全部表情 10 秒（演示/录屏用）
blue-whale-pet --config PATH      # 使用指定配置文件
Windows 便携版：BlueWhalePet-Portable-1.0.0.exe --selftest
```

## 7. 常见问题

**Q：托盘图标找不到？**
Windows 11 默认把新图标收进任务栏 `^` 溢出区，可在「任务栏设置 → 其他系统托盘图标」里固定。Linux GNOME 需要 AppIndicator 扩展；无托盘环境下用**宠物右键菜单**打开设置，功能等价。

**Q：聊天提示 401 / Key 无效？**
重新复制 API Key（注意不要带空格/换行），保存后点「测试连接」；确认平台账户有余额。

**Q：提示 402 余额不足 / 429 限流？**
402 需到对应平台充值（GLM 可在 bigmodel.cn 领免费资源包）；429 请稍后再试（桌宠会自动用本地台词兜底）。

**Q：公司电脑/杀毒软件报毒？**
PyInstaller 打包的未签名 exe 偶发误报，可添加信任；也可使用安装版（onedir 结构更少触发启发式）。

**Q：Linux 上宠物没有透明背景/不能置顶？**
需要 X11 或 XWayland。纯 Wayland 会话下部分窗口管理器限制置顶/形状，建议登录 "Xorg" 会话；无托盘时右键宠物可打开菜单。

**Q：想换掉内置美术？**
`assets/mascot/manifest.json` + 帧 PNG 即全部表情资产，按 `SPEC.md` §4 的尺寸/锚点约定替换后重启即可，无需改代码。

## 8. 隐私与免责

- 与 DeepSeek API 的通信内容（人设、对话）按 DeepSeek 官方 API 条款处理；本项目不收集任何遥测。
- 本项目为非官方二创，DeepSeek 名称与蓝鲸形象版权归 DeepSeek 所有，详见 `assets/source/NOTICE.md` 与 `LICENSE`。
