# 蓝鲸桌宠（Blue Whale Pet / 蓝色大肥鱼）

> DeepSeek「蓝色大肥鱼」AI 桌面宠物 · Windows / Debian / Arch

![状态](https://img.shields.io/badge/version-1.0.0-4D6BFE) ![平台](https://img.shields.io/badge/platform-Windows%20%7C%20Debian%20%7C%20Arch-blue)

**当前状态：开发中。** 本 README 将在交付前由 Lead 完善（功能、截图、安装、API Key 配置、构建、FAQ）。

## 特性（目标）

- 🐳 蓝色大肥鱼桌宠常驻桌面，置顶、透明、无边框，低内存
- 💬 接入 DeepSeek API 对话，言简意赅；无 Key 也可用内置短句互动
- 😊 14 种表情动作：待机 / 眨眼 / 开心 / 大笑 / 说话 / 思考 / 睡觉 / 惊讶 / 难过 / 生气 / 爱心 / 拖拽 / 招手 / 吃鱼
- 🖱️ 左键戳一戳、双击聊天、右键拖拽移动、滚轮缩放
- ⚙️ 任务栏托盘右键打开设置：大小 / 置顶 / 开机自启 / 模型 / API Key / 人设
- 📦 Windows 便携单 exe、Windows 安装版、Debian `.deb`、Arch `PKGBUILD`

## 目录

```
SPEC.md            工程契约（接口/验收标准）
src/               应用源码
assets/            美术资产（由工具生成）
packaging/         三平台打包脚本
release/           构建产物
docs/              使用/构建文档与截图
qa/                自动化验证脚本与测试报告
```

## 快速开始（开发模式）

```bash
py -m pip install pillow
py src/main.py
```

## 许可证

代码 MIT；DeepSeek 蓝鲸 logo 版权归 DeepSeek，本项目为非官方个人二创桌宠，仅供个人使用。
