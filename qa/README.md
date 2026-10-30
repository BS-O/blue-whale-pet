# Lead QA / 验证脚本

独立于各成员自测的验收工具，全部可复现。产物写在 `qa/out/`（gitignore）。

| 脚本 | 用途 | 用法 |
| --- | --- | --- |
| `check_assets.py` | 资产契约校验（manifest/帧/锚点/抖动/图标/插画） | `py qa/check_assets.py` |
| `screenshot_win.py` | 真机启动桌宠→定位窗口→截图→蓝色像素检测；showcase 连拍 | `py qa/screenshot_win.py --exe release/windows/BlueWhalePet-Portable-1.0.0.exe --out docs/screenshots` |
| `measure_memory.ps1` | 便携/安装版空载内存采样 | `powershell -NoProfile -File qa/measure_memory.ps1 -Exe <path>` |
| `verify_installer.ps1` | 安装→校验→卸载→残留检查 | `powershell -NoProfile -File qa/verify_installer.ps1 -Setup release/windows/BlueWhalePet-Setup-1.0.0.exe` |
| `verify_deb.sh` | WSL Debian 中 deb 安装/自测/GUI/卸载 | `wsl -d Debian -- bash /mnt/c/.../qa/verify_deb.sh` |
| `check_release.py` | release 产物完整性与 SHA256 | `py qa/check_release.py` |

验收结论写入 `qa/QA_REPORT.md`。
