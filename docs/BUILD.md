# 构建说明（BUILD）

所有产物均已在本仓库 `release/` 中提供；本文档说明如何**从源码复现构建**。整套构建在 Windows 11 上完成，Windows 包用本机 Python + PyInstaller，Linux 包在 WSL2 Debian 13 中构建。

## 0. 环境要求

| 用途 | 依赖 |
| --- | --- |
| 运行/开发 | Python 3.9+（本项目用 3.11.5）、Pillow ≥ 9、tkinter（Windows 官方 Python 自带） |
| Windows 打包 | PyInstaller 6.x（`py -m pip install pyinstaller`），无需 Inno Setup/NSIS（安装器为自研 Python） |
| Linux 打包 | WSL2 + Debian 13（或原生 Debian/Ubuntu）：`python3-tk python3-pil python3-pil.imagetk dpkg-dev fakeroot zstd xvfb x11-utils xdotool`，可选 `libarchive-tools`（生成 Arch .MTREE） |

> 注意：若 WSL/VM 与 Docker Desktop 冲突导致 `Wsl/Service/CreateInstance/CreateVm/ERROR_TIMEOUT`，先 `Stop-Process` 掉 Docker Desktop 进程 → `wsl --shutdown` → 等 8 秒再 `wsl -d Debian`。

## 1. 开发模式

```bash
py -m pip install pillow
py src/main.py                  # 启动桌宠
py src/main.py --selftest       # 自检（写 <数据目录>/selftest_report.json）
py tests/run_tests.py           # 单元测试
py qa/check_assets.py           # 资产契约校验（独立 QA）
```

重新生成美术（可选，需要 Pillow）：

```bash
py tools/gen_assets.py          # 生成全部表情/图标/安装器插画/manifest
py tools/check_assets.py        # asset-fish 自带校验
```

## 2. Windows 便携版 + 安装版

一键构建（产物在 `release/windows/`）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\windows\build_all.ps1
```

流程：清理 → PyInstaller onedir（安装版应用）→ 打包 payload.zip → PyInstaller onefile（便携版）→ PyInstaller 安装器 → 复制产物 → 生成 SHA256SUMS → 清理 `E:\pet-build-tmp`。

常用参数：`-SkipPortable` / `-SkipInstaller` / `-KeepWork`（保留构建中间目录）/ `-QaConsoleBuild`（生成控制台版便于看 selftest stdout）。
中间目录默认 `E:\pet-build-tmp\pack-win`（可用 `-BuildRoot` 改）。

产物：
- `release/windows/BlueWhalePet-Portable-1.0.0.exe`：单文件便携版（onefile / windowed，含 `portable.flag`）
- `release/windows/BlueWhalePet-Setup-1.0.0.exe`：自研安装向导（内嵌 onedir 应用 zip，安装到 `%LOCALAPPDATA%\Programs\BlueWhalePet`）
- `release/windows/SHA256SUMS.txt`

安装器静默用法（自动化/批量部署）：

```bat
BlueWhalePet-Setup-1.0.0.exe /S /D=C:\Tools\BlueWhalePet
BlueWhalePet-Setup-1.0.0.exe /uninstall /S
```

手动构建（不跑一键脚本）示例：

```powershell
py -m PyInstaller --noconfirm --clean --distpath E:\pet-build-tmp\dist `
  --workpath E:\pet-build-tmp\work\portable packaging\windows\pet-portable.spec
py -m PyInstaller --noconfirm --clean --distpath E:\pet-build-tmp\dist `
  --workpath E:\pet-build-tmp\work\onedir packaging\windows\pet-onedir.spec
```

## 3. Debian 包 + Arch 包（WSL Debian 13）

```bash
bash packaging/linux/build_linux.sh              # deb + arch 包
bash packaging/linux/build_linux.sh --pyinstaller  # 额外产出 Linux 单文件版
```

产物（`release/linux/`）：
- `blue-whale-pet_1.0.0_all.deb` —— 源码安装到 `/usr/lib/blue-whale-pet`，依赖系统 python3-tk/python3-pil
- `blue-whale-pet-1.0.0-1-any.pkg.tar.zst` —— 可直接 `sudo pacman -U` 的 Arch 包
- `blue-whale-pet-1.0.0.tar.gz` —— PKGBUILD 使用的源码 tarball
- `PKGBUILD` + `blue-whale-pet.install`
- `BlueWhalePet-Linux-x86_64`（`--pyinstaller` 时；在 Debian 13 上构建，glibc ≥ 2.41 可运行）

安装验证：

```bash
sudo dpkg -i release/linux/blue-whale-pet_1.0.0_all.deb
blue-whale-pet --version
xvfb-run -a blue-whale-pet --selftest
sudo dpkg -r blue-whale-pet
```

Arch 环境（或手工解包校验）：

```bash
# 有 pacman 的机器：
sudo pacman -U blue-whale-pet-1.0.0-1-any.pkg.tar.zst
# 无 pacman 的机器上静态校验：
zstd -t blue-whale-pet-1.0.0-1-any.pkg.tar.zst
tar --zstd -tf blue-whale-pet-1.0.0-1-any.pkg.tar.zst | head
```

## 4. 打包矩阵约定

| 项目 | 便携版 | 安装版 | deb / Arch |
| --- | --- | --- | --- |
| 形态 | PyInstaller onefile | PyInstaller onedir + 自研安装器 | 源码 + 系统 Python |
| 数据目录 | exe 旁 `BlueWhalePet-Data` | `%APPDATA%\BlueWhalePet` | `~/.config/blue-whale-pet` |
| 运行时依赖 | 自带 Python/Tk/Pillow | 自带 | 系统 python3-tk / python3-pil |
| 自启方式 | 托盘菜单 / 设置 | 托盘菜单 / 设置 | 托盘菜单 / 设置（写 `~/.config/autostart`） |

三端共用同一份 `src/` 与 `assets/`，行为一致；差异只在 `src/resources.py` 的路径解析（便携标记 / 环境变量 `BLUE_WHALE_PET_ASSETS`）。

## 5. 打包排除项（重要）

- 应用载荷**不包含** `assets/source/`（网络参考图，含官方版权素材）与 `assets/preview/`（文档预览图）。
- 安装器载荷额外包含 `assets/installer/` 的 banner/side 插画；应用本身不需要。
- `.gitignore` 已排除构建中间产物、用户配置与 `BlueWhalePet-Data/`。

## 6. 校验

```bash
py qa/check_release.py     # 产物存在性/文件头/SHA256 校验
py qa/check_assets.py      # 资产契约
py qa/screenshot_win.py --exe release/windows/BlueWhalePet-Portable-1.0.0.exe --out docs/screenshots
py qa/interact_win.py --exe <exe>     # 需要先运行 py qa/mock_api.py --port 8765
```

Windows 安装/卸载往返：`powershell -File qa/verify_installer.ps1 -Setup release\windows\BlueWhalePet-Setup-1.0.0.exe`
Debian 安装/卸载往返：`wsl -d Debian -u root -- bash qa/verify_deb.sh <deb 路径>`
内存采样：`powershell -File qa/measure_memory.ps1 -Exe release\windows\BlueWhalePet-Portable-1.0.0.exe`
