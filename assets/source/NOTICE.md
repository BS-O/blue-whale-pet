# 参考素材来源与版权说明（NOTICE）

本项目为 **非官方** 的 DeepSeek 桌宠二创项目，仅供个人学习与娱乐使用。DeepSeek 名称、蓝鲸（蓝色大肥鱼）logo
及品牌视觉的版权归杭州深度求索人工智能基础技术研究有限公司（DeepSeek）所有。本项目未获得 DeepSeek 官方授权，
不使用其商标作为本项目官方身份标识。若版权方有异议，请联系删除。

> **`assets/source/` 为开发期参考资料，请在打包（exe/deb/pkg）时排除，不要随产品分发。**

## 网络搜集的参考素材（assets/source/references/）

| 文件 | 来源 URL | 说明/处理 |
| --- | --- | --- |
| `deepseek-app-icon-vectorseek.png` | https://vectorseek.com/wp-content/uploads/2025/01/Deepseek-Chat-App-Icon-PNG-Vector.png （页面：https://vectorseek.com/vector_logo/deepseek-chat-app-icon-png-vector/） | 1200×1200 官方蓝鲸图标。**实测为 RGB 图、背景是烘焙的棋盘格（非真透明）**；用 Pillow 色差键控抠出主体后再做取色/比例参考，成品为重绘 |
| `deepseek-logo-vectorseek-transparent.png` | 同上（抠图产物） | Pillow 色差键控（`b-r` 估计 alpha）得到透明背景官方蓝鲸；键控主体包围盒≈(120,246,1080,954)、宽高比≈1.36、主体平均色 **#4D6BFE**（与成品品牌蓝一致） |
| `deepseek-favicon-225.ico` / `deepseek-whale-logo-225.png` | https://www.deepseek.com/favicon.ico | 官网 favicon（225×225），官方蓝鲸形象交叉参照 |
| `deepseek-simpleicons.svg` | https://unpkg.com/simple-icons@latest/icons/deepseek.svg （Simple Icons, CC0-1.0） | 官方图标的单色矢量版本，用于提取标准蓝色与轮廓比例 |
| `deepseek-social-1200x630.jpg` | https://www.deepseek.com/images/deepseek-social.jpg | 官网 OG 社交图（1200×630，官方鲸鱼 + wordmark），2026-10-30 下载 |
| `deepseek-brand-social-crop.png` | 同上（裁剪产物） | Pillow 按蓝色像素包围盒自动裁剪出 logo 区域（鲸鱼 + wordmark），供取色/比例分析 |
| `deepseek-whale-logo-social-transparent.png` | 同上（抠图产物） | Pillow 色差键控（`b - r` 估 alpha）+ 统一调色为 `#4D6BFE`，得到透明背景官方鲸鱼，仅作轮廓参照 |
| `meme-style-notes.md` | https://aigengtu.com/DeepSeek%E5%A8%98 等公开梗图站 | 「蓝色大肥鱼」梗图搜集记录：图片 CDN `img.aigengtu.com` 被 DNS 劫持无法下载，仅记录页面标题/alt 文本表情语义作风格参考；未再分发任何梗图 |

### 网络搜集说明（可复现）

- 官方站 `www.deepseek.com`、`unpkg.com` 可达；`vectorseek.com` 请求超时（仅有项目预置的 App 图标）；
  `img.aigengtu.com` 解析被劫持、`github.com` / `raw.githubusercontent.com` 不可达 —— 梗图原图未能下载，
  改为使用官方社交图 + 页面元信息作参考，成品 100% 程序化重绘。
- Pillow 处理：`tools/gen_assets.py --analyze` 输出参考图主体包围盒 / 宽高比 / 平均色，与成品几何参数对照；
  抠图/调色/裁剪步骤见 `references/meme-style-notes.md` 第 3 节。当前分析结果：
  官方双叶尾鳍侧视轮廓宽高比 ≈ 1.36，成品正面 Q 版轮廓宽高比 ≈ 1.16（更圆更肥，符合二创方向）；
  官方主体平均色 **#4D6BFE** 与成品品牌蓝完全一致。

## 处理说明

- 所有成品精灵（`assets/mascot/master/*.png`）、图标（`assets/icons/`）、安装器插画（`assets/installer/`）
  均由 `tools/gen_assets.py` 基于官方 logo 的轮廓/配色/比例 **程序化重绘**（圆肥身体、双叶尾鳍、大眼、腮红、
  深藏青粗描边 `#0B1330`、品牌蓝 `#4D6BFE`），并非官方素材原样缩放或分发。
- 表情/动画（14 state × 38 帧）、图标（app/tray/setup/hicolor/svg）、安装器 banner/side 全部由代码绘制，
  无外部图片素材进入成品目录。
- Simple Icons 部分遵循 CC0-1.0；其余素材版权归原作者/DeepSeek 所有，仅作参考，不随本项目单独授权。

## 2026-10-31 图标更新（应用更名「蓝色大肥鱼」）

- 用户在桌面提供候选图 `1.png / 2.png / 3.png / 5.png`（4.png 未提供，共 4 张有效），
  作为新版应用图标（app.ico / tray.ico / setup.ico / app.png / hicolor / svg）的素材来源。
- 处理流程（`tools/gen_icons.py`，可复现）：
  1. 四角中值估计背景色 + 边界洪泛抠图（背景均匀度阈值 0.55，容差自适应）；
  2. 主体裁边、6% 透明衬边、0.8px 羽化；贴纸表格图（1.png，322 个连通域）自动切出最大单体；
  3. 主体主色判定（HSV）→ 偏蓝主体用浅底 `#F7F9FF` + 品牌蓝描边环，否则品牌蓝底；
  4. 多尺寸重采样（ICO 256~16 / hicolor 16~512 / 512 app.png / SVG 内嵌 base64）。
- 自动选型：候选 1（贴纸表格中的单只蓝鱼，score 5.0）> 候选 5（单只主体，score 5.0）> 2/3（背景复杂仅圆角裁切）。
  如需改用其他候选：`py tools/gen_icons.py --pick 5`。对比图：`docs/screenshots/icon_candidates.png`。
- 候选图版权归原作者所有，仅本机使用，不随仓库外的分发再授权。

## 2026-10-31 晚 · 桌宠本体更换为用户素材（v3）

- 用户要求桌宠**本体形态**使用桌面 1~5 号图片（实际为 1.png / 2.png / 3.png / 4.jpg / 5.png，
  无 3.jpg 与 4.png）处理后的形象，并反馈此前图标"太模糊"。
- **桌宠本体**（`assets/mascot/master/` 14 状态 × 38 帧）：
  - 身体素材：**5.png 主体**（854×1564 蓝头白肚大肥鱼，洪泛抠图 + 最大连通域 + UnsharpMask）；
  - 14 状态 = 整体形变（呼吸压扁/摇摆/旋转/位移，围绕底部锚点）+ 矢量符号叠加
    （爱心/Zz/?/!/泪滴/青筋/音符/速度线/食物碎屑/气泡点）+ **单眼 wink 眼睑**
    （脸部为 3/4 侧视，仅左眼可见 fx≈0.345 fy≈0.150，右眼被头鳍遮挡）；
  - 生成器 `tools/gen_mascot_images.py`（--source/--no-eyelid 可调），画布 512、
    key 色与 manifest 不变；联络表 `docs/screenshots/mascot_preview.png`。
- **图标 v3（修模糊）**：`tools/gen_icons.py` 候选扩为 1/2/3/4/5 号（4 号为 4.jpg），
  自动选 **5 号头部方形裁切**（854×813，与本体同源）；修复点：
  ① 移除 thumbnail(1400) 预降采样；② 主体占比 0.80→0.88；③ 羽化 0.8→0.5 + UnsharpMask；
  ④ ICO 改由 1024 母版逐档直出（避免 256 中转二次缩放）。
- 其余素材用途：1.png 双排小鱼贴纸表（备选/贴纸）、4.jpg 方形蓝角色（候选 2）、
  2.png / 3.png 为多角色复杂场景，背景无法干净分离，仅存档不参与抠图。
- 候选图版权归原作者所有，仅本机使用。

## 2026-10-31 深夜 · 多素材状态系统（v4，用户指定）

- 用户指定：各状态使用 1.png（贴纸表）+ 修改后的 1.png（抠出小鱼）+ 2~5 号图；
  **4.jpg 仅在愤怒状态以 50% 概率出现**（另 50% 为 1.png 愤怒小鱼版）。
- 分工：5.png 主体 → idle/blink/drag；1.png 七只小鱼（extract_sheet_fish.py 抠图+锐化）
  → happy(fish_1)/laugh(fish_4)/talk(fish_0)/think(fish_6)/sleep(fish_5)/
  surprise(fish_2)/sad(fish_0)/love(fish_1)/wave(fish_2)/eat(fish_3 张嘴)/angry(fish_3+青筋)；
  4.jpg → angry_alt（angryalt_0/1）；2.png/3.png → talk/think 帧内的圆角小照片点缀
  （多角色场景无法作主体）。
- 实现：manifest 新增 `angry_alt` 状态（第 15 个），app 戳一戳触发愤怒时 50% 抽签切换；
  生成器 `tools/gen_mascot_images.py`（40 帧输出）。
- 交互变更（用户要求）：**桌宠本体右键不再弹出菜单**（保留托盘菜单作为功能入口）。
