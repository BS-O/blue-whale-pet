# Linux 构建报告（BUILD REPORT）

- 构建时间：2026-10-31 18:28（最终版；首版 2026-10-30 21:08）
- 构建环境：Windows 11 + WSL2 Debian 13 (trixie)，系统 Python 3.13 + python3-tk + python3-pil + python3-pil.imagetk
- 构建脚本：`packaging/linux/build_linux.sh`（自动构建 deb + Arch 包 + 源码 tarball + PKGBUILD，可选 `--pyinstaller` 产出单文件版）
- 源码快照：src 冻结版（2026-10-30 21:10 定稿）+ 资产定稿 v1（2.93 MB）

## 产物（release/linux/）

| 文件 | 大小 | SHA256 |
| --- | --- | --- |
| blue-whale-pet_1.0.0_all.deb | 1,775,652 B | `c773985a5d12e46cdf37cf83d7905c1ab062bbc8ceb929f9dd76e608cac153a4` |
| blue-whale-pet-1.0.0-1-any.pkg.tar.zst | 1,801,512 B | `d479574f88ff8df8fa62e99b9cf1735b452f8c32a404691fbb5d631f7f693882` |
| blue-whale-pet-1.0.0.tar.gz | 2,217,301 B | `f19f6660706d05b8a42de8872fa2132b1a8eb4945f1244b1f7ca4895ea30c45f` |
| PKGBUILD | 1,691 B | `25b6eb8e5cf27d8edd3f63604bc9d3d987434c34e4b811fceaea1531e58469eb` |
| blue-whale-pet.install | 1,597 B | `6f49c72efd1606b6c9e341a513dfcba6c9deccbed105268633d70deae4d3df70` |
| BlueWhalePet-Linux-x86_64（可选单文件版） | 21,166,832 B | `ad0b8d4da7f5fde47f2c0fe67f0dfa391dbb555d363ce24b248bc7500b762a3b` |

完整校验值：`release/linux/SHA256SUMS.txt`、`release/SHA256SUMS.txt`。

## 包设计

- **.deb**：Architecture: all；Depends `python3 (>=3.9), python3-tk, python3-pil, python3-pil.imagetk`；Recommends `python3-pystray`（trixie 有 0.19.5-1，已核实）；源码安装到 `/usr/lib/blue-whale-pet`，启动器 `/usr/bin/blue-whale-pet`，桌面项 `/usr/share/applications/blue-whale-pet.desktop`，hicolor 图标 8 个尺寸 + scalable SVG；postinst 刷新桌面数据库/图标缓存；postrm 清理运行时 `__pycache__` 与自启项，保留用户配置 `~/.config/blue-whale-pet/`；**不包含 assets/source 与 assets/preview**（版权参考素材不随包分发）。
- **Arch 包**：tar + zstd 手工构建（构建机无 pacman）；含 `.PKGINFO`（pkgname/pkgver 1.0.0-1/arch=any/depends python,tk,python-pillow/optdepend python-pystray）、`.INSTALL`、`.CHANGELOG`；无 .MTREE（无 libarchive-tools 生成，pacman 可正常安装，已在构建日志注明）。同目录提供 `PKGBUILD`（sha256 已填）与 `blue-whale-pet.install`，可用 `makepkg -si` 从源码复现。

## 验证（Lead 独立执行，全部 PASS）

| 检查 | 结果 |
| --- | --- |
| `dpkg -i` 安装 | rc=0；`/usr/bin/blue-whale-pet`、`/usr/lib/blue-whale-pet/main.py`、桌面项、8 个 hicolor 图标、scalable 图标就位 |
| 包内源码与冻结 src 一致性 | md5 一致（抽查 pet_window.py） |
| `blue-whale-pet --version` | `蓝鲸桌宠 1.0.0` |
| `xvfb-run -a blue-whale-pet --selftest` | rc=0，15 项检查全过，14 states/38 frames，数据目录 `~/.config/blue-whale-pet/`，working_set 41.71 MB |
| WSLg 真窗口启动 | `--showcase` 启动后 xdotool 定位到窗口（window=6291471），WM_CLASS=blue-whale-pet |
| `dpkg -r blue-whale-pet` | rc=0；/usr/bin 启动器、桌面项、注册图标全部移除；**安装目录无残留**（postrm 清理了运行时 `__pycache__`，2026-10-31 修复后验证） |
| 用户配置保留 | `~/.config/blue-whale-pet/` 卸载后保留 |
| Arch 包 `zstd -t` + tar 列表 | 结构校验通过；`.PKGINFO` 字段齐全；无 source/preview |
| 单文件版（Debian 13 构建） | ELF x86-64 动态链接，glibc ≥ 2.41 可运行（构建机 libc 版本声明见 PyInstaller 日志） |

## 已知限制

1. Arch 包未含 `.MTREE`（构建机无 libarchive-tools；`pacman -U` 不受影响）。
2. 单文件版由 Debian 13 的 glibc 构建，CentOS 7 等老系统不兼容；推荐发行版用户使用 deb / PKGBUILD 方式。
3. Linux 托盘依赖 XEmbed/AppIndicator 环境：GNOME 需 AppIndicator 扩展，无托盘时应用自动退化为宠物右键菜单（功能等价）。
4. WSL 沙箱中 `sudo` 有密码提示，验证一律以 `-u root` 运行；真实发行版上按 README 用 `sudo apt/pacman` 即可。

---

## r2 重打（2026-10-31，应用更名 + GLM 适配）

- 显示名更改为「蓝色大肥鱼」（.desktop / control 描述 / man 页 / postinst&postrm 提示 / PKGBUILD pkgdesc；包名仍为 blue-whale-pet）。
- 新增 GLM 平台适配随源码打包（设置窗口平台切换，见 Windows r2 说明）。
- 产物：deb `7db898626373462a`（1,775,x B）、arch `18aae495fe47dcb4`；完整值 SHA256SUMS.txt。
- 验证：`dpkg -i` → `--version` 输出「蓝色大肥鱼 1.0.0」→ `xvfb-run --selftest` 15/15（app=蓝色大肥鱼，42.07MB）→ WSLg 真窗口 → `dpkg -r` 无残留。`DEB VERIFY OK`。

---

## r3 重打（2026-10-31，桌宠本体更换 + 图标 v3）

- 桌宠 38 帧更换为 5.png 主体合成；图标 v3 同步。deb `5b42532821643225`、arch `e6830f2a46e82f9f`。
- 验证：DEB VERIFY OK（14 状态/38 帧、`--version` 蓝色大肥鱼 1.0.0、WSLg 真窗口、卸载无残留）。

---

## r4 重打（2026-10-31，多素材状态系统）

- 40 帧/15 状态（含 angry_alt）；deb `3004b895a4f800bc`、arch `6e6b4be1ef475a82`；DEB VERIFY OK。
