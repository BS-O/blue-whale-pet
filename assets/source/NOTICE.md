# 参考素材来源与版权说明（NOTICE）

本项目为 **非官方** 的 DeepSeek 桌宠二创项目，仅供个人学习与娱乐使用。DeepSeek 名称、蓝鲸（蓝色大肥鱼）logo
及品牌视觉的版权归杭州深度求索人工智能基础技术研究有限公司（DeepSeek）所有。本项目未获得 DeepSeek 官方授权，
不使用其商标作为本项目官方身份标识。若版权方有异议，请联系删除。

## 网络搜集的参考素材（assets/source/references/）

| 文件 | 来源 URL | 说明/处理 |
| --- | --- | --- |
| `deepseek-app-icon-vectorseek.png` | https://vectorseek.com/wp-content/uploads/2025/01/Deepseek-Chat-App-Icon-PNG-Vector.png （页面：https://vectorseek.com/vector_logo/deepseek-chat-app-icon-png-vector/） | 1200×1200 官方蓝鲸图标（透明背景），作为桌宠轮廓基础；提取轮廓→二创为更圆润的大肥鱼表情精灵 |
| `deepseek-favicon-225.ico` / `deepseek-whale-logo-225.png` | https://www.deepseek.com/favicon.ico | 官网 favicon（225×225），作为官方蓝鲸形象交叉参照 |
| `deepseek-simpleicons.svg` | https://unpkg.com/simple-icons@latest/icons/deepseek.svg （Simple Icons, CC0-1.0） | 官方图标的单色矢量版本，用于提取标准蓝色与轮廓比例 |
| `meme-*.jpg/png`（如有） | https://aigengtu.com/ 等公开梗图站 | 「蓝色大肥鱼」网络梗图，仅作二创风格参考，不直接再分发为成品资产 |

## 处理说明

- 所有成品精灵（`assets/mascot/master/*.png`）、图标（`assets/icons/`）、安装器插画（`assets/installer/`）
  均由 `tools/gen_assets.py` 基于上述参考素材 **程序化二创** 生成（重绘表情、配色、描边、动画），
  并非官方素材原样分发。
- Simple Icons 部分遵循 CC0-1.0；其余素材版权归原作者/DeepSeek 所有，仅作参考，不随本项目单独授权。
