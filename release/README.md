# 蓝色大肥鱼 v1.0.0 · 发布产物（r2：更名 + GLM）

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
c74887eab5599183d99a81bfbb5f4000d406f8acb4b5004b7b2e0f79ba0745f0  windows/BlueWhalePet-Portable-1.0.0.exe
173849dca0d12682047c72a1eef69c47c0367e13df73afc7b3e7e8c096e4bed3  windows/BlueWhalePet-Setup-1.0.0.exe
7db898626373462ae6fe36fe9e1ca8172f6f3ac0737d2d89cbe97bb059769f9f  linux/blue-whale-pet_1.0.0_all.deb
18aae495fe47dcb492a2d0aa7e66be37c5750be14a5071eb8dc1567b9bfae16e  linux/blue-whale-pet-1.0.0-1-any.pkg.tar.zst
```
