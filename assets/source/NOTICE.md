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
