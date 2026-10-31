# 蓝鲸桌宠 Linux 打包（pack-linux）

本目录是 Linux 平台打包脚本与包描述文件，产出 **Debian/Ubuntu `.deb`** 与 **Arch 预构建包 `pkg.tar.zst` + PKGBUILD**。
在 WSL2 Debian 13 (trixie) 中实测通过；也适用于其他 Debian/Ubuntu 系发行版。

## 目录结构

```
packaging/linux/
├── build_linux.sh              # 一键构建入口（deb + arch + 可选 PyInstaller 单文件版）
├── common.sh                   # 公共函数：项目根定位 / 安装树铺设 / 图标补齐
├── debian/                     # .deb 控制文件与安装时资源
│   ├── control                 #   control 模板（@VERSION@ 等占位由脚本替换）
│   ├── postinst                #   安装后：update-desktop-database / gtk-update-icon-cache
│   ├── postrm                  #   卸载后：清理用户自启项、保留 ~/.config/blue-whale-pet
│   ├── blue-whale-pet.desktop  #   桌面菜单项（Icon=blue-whale-pet, StartupWMClass=blue-whale-pet）
│   ├── blue-whale-pet.launcher #   /usr/bin/blue-whale-pet 启动器模板
│   ├── main.py.bootstrap       #   /usr/lib/blue-whale-pet/main.py 引导壳
│   ├── blue-whale-pet.1        #   man 页
│   ├── copyright               #   Debian 版权文件
│   └── blue-whale-pet.svg      #   可选：资产缺矢量图标时的备用 SVG（一般不用）
└── arch/
    ├── PKGBUILD                # makepkg 用 PKGBUILD 模板（@SHA256SUM@ 由脚本填入）
    ├── build_arch_pkg.sh       # 手工构建 pkg.tar.zst（无需 pacman/makepkg）
    └── blue-whale-pet.install  # Arch 安装脚本（post_install/pre_remove/post_remove）
```

## 安装构建依赖（Debian/Ubuntu）

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-tk python3-pil python3-pil.imagetk \
    dpkg-dev fakeroot zstd xvfb x11-utils xdotool
# 可选：生成 Arch 包内 .MTREE 用（没有也能构建，仅缺可选元数据）
sudo apt-get install -y libarchive-tools
```

`python3-pystray` 仅在 Debian 仓库确实提供时才写入 `Recommends`（脚本自动检测，本环境 trixie 提供）。

## 构建

```bash
# 在项目根目录（blue-whale-pet/）执行
bash packaging/linux/build_linux.sh                 # 产出 .deb + Arch 包
bash packaging/linux/build_linux.sh --pyinstaller   # 额外产出 Linux 单文件版（需 pip install pyinstaller）
bash packaging/linux/build_linux.sh --no-deb        # 只打 Arch
bash packaging/linux/build_linux.sh --no-arch       # 只打 deb
bash packaging/linux/build_linux.sh --out /tmp/out  # 自定义输出目录
bash packaging/linux/build_linux.sh --keep-work     # 保留 /tmp 临时目录排查
```

临时文件默认放 `/tmp`（`mktemp -d`），构建结束自动清理，不污染 Windows C 盘可见目录。

### 产物（默认 `release/linux/`）

| 文件 | 说明 |
| --- | --- |
| `blue-whale-pet_1.0.0_all.deb` | Debian/Ubuntu 安装包（Architecture: all） |
| `blue-whale-pet-1.0.0-1-any.pkg.tar.zst` | Arch 预构建包（手工 tar+zstd，含 .PKGINFO/.INSTALL/.MTREE） |
| `blue-whale-pet-1.0.0.tar.gz` | Arch PKGBUILD 引用的源码 tarball |
| `PKGBUILD` | 已填入 tarball sha256，可直接 `makepkg -si` |
| `blue-whale-pet.install` | PKGBUILD `install=` 引用的安装脚本 |
| `BlueWhalePet-Linux-x86_64` | （可选 `--pyinstaller`）PyInstaller 单文件版 |

## 安装布局（deb / Arch 完全一致）

```
/usr/bin/blue-whale-pet                       # 启动器：BLUE_WHALE_PET_ASSETS=... exec python3 /usr/lib/blue-whale-pet/main.py "$@"
/usr/lib/blue-whale-pet/main.py               # 引导壳：src/ 加入 sys.path 后以 __main__ 运行 src/main.py
/usr/lib/blue-whale-pet/src/                  # 应用源码（含 anim/ 子包）
/usr/lib/blue-whale-pet/assets/               # 美术资产（mascot/manifest.json + 全部帧 + icons）
/usr/share/applications/blue-whale-pet.desktop
/usr/share/icons/hicolor/{16,24,32,48,64,128,256,512}x*/apps/blue-whale-pet.png
/usr/share/icons/hicolor/scalable/apps/blue-whale-pet.svg
/usr/share/pixmaps/blue-whale-pet.png
/usr/share/man/man1/blue-whale-pet.1
/usr/share/doc/blue-whale-pet/{copyright,LICENSE}
```

`Depends: python3 (>= 3.9), python3-tk, python3-pil, python3-pil.imagetk`；
`Recommends: python3-pystray`（仓库提供时）。

## 安装 / 卸载

```bash
# Debian/Ubuntu
sudo dpkg -i release/linux/blue-whale-pet_1.0.0_all.deb
# 若依赖未装：sudo apt-get -f install
blue-whale-pet --version
blue-whale-pet --selftest           # 无 GUI 环境：xvfb-run -a blue-whale-pet --selftest
sudo dpkg -r blue-whale-pet          # 卸载干净（用户配置保留）

# Arch
sudo pacman -U release/linux/blue-whale-pet-1.0.0-1-any.pkg.tar.zst
# 或从源码构建：
cd release/linux && makepkg -si
```

用户数据：`$XDG_CONFIG_HOME/blue-whale-pet/`（未设则 `~/.config/blue-whale-pet/`），
卸载时保留，并在 postrm/pre_remove 中提示；自启项 `~/.config/autostart/blue-whale-pet.desktop` 会被清理。

## 本机构建/验证记录

详细实测命令与输出见 `release/linux/BUILD_REPORT.md`。

## 说明与限制

- **Arch 包为手工构建**：本环境无 pacman/makepkg 与 Arch 根文件系统，`pkg.tar.zst` 由 `tar + zstd -19`
  按 Arch 包规范生成（`.PKGINFO` 首条目、可选 `.MTREE`、`.INSTALL`），并用 `zstd -t`、`tar -tf`、
  `.PKGINFO` 字段与文件权限做静态校验；未在真实 Arch 上 `pacman -U` 实测（已在报告中说明）。
- **PyInstaller 单文件版**在 Debian 13（glibc 2.41）上构建，只能在不高于该 glibc 的发行版运行，
  向下兼容性不如 `.deb`，属于可选附加产物。
- 构建脚本会排除 `assets/source/`（官方版权参考图，不随包分发）与 `assets/preview/`（开发用拼图）；
  `assets/mascot/`、`assets/icons/` 及运行时所需内容完整安装。包内文件权限统一为：目录 755、数据文件 644、
  `/usr/bin/blue-whale-pet` 启动器 755。
- Arch 包内 `.MTREE` 由 bsdtar 生成（uid/gid 归零）；无 bsdtar 时会跳过该可选文件并给出警告。
