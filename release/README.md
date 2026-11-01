# 蓝色大肥鱼 v1.0.0 · 发布产物（r3：更名 + GLM + 本体素材化）

> 全部产物由同一份源码与资产构建；校验值见各目录 `SHA256SUMS.txt` 或上级 `SHA256SUMS.txt`。

## 下载选择

| 你的系统 | 推荐下载 | 说明 |
| --- | --- | --- |
| Windows（不想安装） | [windows/BlueWhalePet-Portable-1.0.0.exe](windows/BlueWhalePet-Portable-1.0.0.exe) | 单文件便携版，双击即用，配置随 exe 存放 |
| Windows（常规安装） | [windows/BlueWhalePet-Setup-1.0.0.exe](windows/BlueWhalePet-Setup-1.0.0.exe) | 向导/静默安装，含卸载器与开始菜单/桌面快捷方式 |
| Debian 12+/Ubuntu 22.04+ | [linux/blue-whale-pet_1.0.0_all.deb](linux/blue-whale-pet_1.0.0_all.deb) | `sudo apt install ./blue-whale-pet_1.0.0_all.deb` |
| Arch/Manjaro | [linux/blue-whale-pet-1.0.0-1-any.pkg.tar.zst](linux/blue-whale-pet-1.0.0-1-any.pkg.tar.zst) | `sudo pacman -U blue-whale-pet-1.0.0-1-any.pkg.tar.zst` |
| Arch（源码构建） | [linux/PKGBUILD](linux/PKGBUILD) + [linux/blue-whale-pet-1.0.0.tar.gz](linux/blue-whale-pet-1.0.0.tar.gz) | 同目录放置后 `makepkg -si` |
| 其他 Linux x86_64 | [linux/BlueWhalePet-Linux-x86_64](linux/BlueWhalePet-Linux-x86_64) | 单文件版，需较新 glibc（Debian 13 构建），依赖系统 python3-tk 不需要——已内嵌 |

## 各目录内容

- `windows/`：两个 exe、SHA256SUMS、BUILD_REPORT（构建流水线与验证记录）
- `linux/`：deb / Arch 预构建包 / 源码 tarball / PKGBUILD / .install / 单文件版、SHA256SUMS、BUILD_REPORT
- `../qa/QA_REPORT.md`：独立端到端 QA 证据（自检、内存、交互、安装/卸载往返）
- `../docs/USAGE.md`：完整使用手册；`../docs/BUILD.md`：从源码构建

## 校验值速览

```text
4dcf436a695d60087dfb9e5e7c44f43c412ed04e236afb4fcd31f2b5c0b08e5e  windows/BlueWhalePet-Portable-1.0.0.exe
b4103c3669b62a0c0324800bd608f77cbc867f744371430d8d9d1ed7fe48fb5d  windows/BlueWhalePet-Setup-1.0.0.exe
cf57b82503a9975845685ddaf977e685477bbadb6e9ceff0e641583c65cc43cc  linux/blue-whale-pet_1.0.0_all.deb
97349d97276117d645b856a66fc3f57089d033366b5e4a2f574ed4f706c9ad94  linux/blue-whale-pet-1.0.0-1-any.pkg.tar.zst
```
