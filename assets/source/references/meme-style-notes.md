# 网络梗图素材搜集记录（「蓝色大肥鱼」风格参考）

> 本文件记录 2026-10-30 搜集过程中的公开页面与可获取的元信息，仅用于 **二创风格参考**。
> 成品精灵（`assets/mascot/master/*.png`）全部由 `tools/gen_assets.py` 程序化重绘，未使用任何梗图原图。

## 1. 搜集结果概览

| 目标 | 站点 / URL | 可达性 | 处理方式 |
| --- | --- | --- | --- |
| DeepSeek 官网 OG 社交图（官方鲸鱼 + wordmark） | https://www.deepseek.com/images/deepseek-social.jpg | ✅ 已下载（1200×630，69KB） | 存为 `deepseek-social-1200x630.jpg`；裁剪出 logo 区域存为 `deepseek-brand-social-crop.png`；用 Pillow 色差键控抠出透明鲸鱼并调色为品牌蓝，存为 `deepseek-whale-logo-social-transparent.png` |
| DeepSeek 官网 favicon | https://www.deepseek.com/favicon.ico | ✅ 已下载 | 与已有 `deepseek-favicon-225.ico` 一致（225×225） |
| Simple Icons 官方单色鲸鱼 SVG | https://unpkg.com/simple-icons@latest/icons/deepseek.svg | ✅ 已下载（CC0-1.0） | 用于核对轮廓比例与品牌蓝 |
| 「蓝色大肥鱼 / DeepSeek娘」梗图库 | https://aigengtu.com/DeepSeek%E5%A8%98 | ⚠️ 页面 HTML 可达（约 2.3k 张梗图索引），但图片 CDN `img.aigengtu.com` 被 DNS 劫持（解析到 `img.aigengtu.com.cc`）**无法下载图片文件** | 仅使用页面标题 / 图片 alt 文本（表情语义）作为表情设计参考，见下节 |
| vectorseek 官方 App 图标页 | https://vectorseek.com/vector_logo/deepseek-chat-app-icon-png-vector/ | ❌ 站点请求超时（301 后无响应） | 项目预置的 `deepseek-app-icon-vectorseek.png` 已可作为轮廓基础 |
| GitHub 梗图仓库（deepseek-chan-meme-pack） | https://github.com/the-beating-light-of-the-nail/deepseek-chan-meme-pack | ❌ github.com / raw.githubusercontent.com 均不可达 | 仅记录仓库名与描述（「蓝色大肥鱼表情包 1400+ 张」）作为风格参考 |

## 2. aigengtu 梗图页可获取的表情语义参考（alt 文本，节选）

> 来源：<https://aigengtu.com/DeepSeek%E5%A8%98>（页面标题：“DeepSeek娘表情包 · 2358张蓝色大肥鱼梗图 · 持续更新 | 梗鲸”）
> 图片文件因 CDN 不可达未下载，以下 alt 文本仅作“表情/情绪”设计参考。

- 「真当我是便宜货啊」气鼓鼓
- 「又错了，我再换另一种方法」委屈落泪
- 「这用户发的啥啊」疑惑不解
- 「你目录里的dsh是什么…大烧货吗」吃瓜窥屏
- 「把钱还我」崩溃

据此确定本项目 14 表情覆盖：待机/眨眼/开心/大笑/说话/思考/睡觉/惊讶/难过/生气/爱心/拖拽/挥手/吃东西，
并采用“圆肥蓝鲸 + 深色粗描边 + 大眼 + 腮红 + 品牌蓝 `#4D6BFE`”的统一风格，避免直接复制梗图角色。

## 3. Pillow 处理说明（均可复现）

- `tools/gen_assets.py --analyze`：读取参考图，统计主体 alpha 包围盒 / 宽高比 / 主体平均色，
  与成品角色几何参数对照（官方 logo 与成品同为横向圆肥轮廓，成品宽高比约 1.24）。
- 抠图/调色（官方社交图 → 透明鲸鱼）：对每个像素用色差 `b - r` 估计 alpha（背景近白差值小，logo 蓝差值大），
  RGB 统一重映射为品牌蓝 `#4D6BFE`，得到 `deepseek-whale-logo-social-transparent.png`。
- `deepseek-brand-social-crop.png`：按蓝色像素分布包围盒自动裁剪（Pillow `crop`），保留鲸鱼 + wordmark。

## 4. 版权

以上官方图片版权归杭州深度求索人工智能基础技术研究有限公司（DeepSeek）所有，仅作本项目个人二创的参考；
不随成品资产分发、不用于商业用途。网络梗图版权归原作者所有。详见 `assets/source/NOTICE.md`。
