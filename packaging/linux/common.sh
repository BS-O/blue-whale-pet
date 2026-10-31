#!/usr/bin/env bash
# 蓝鲸桌宠 Linux 打包公共函数库。
# 被 build_linux.sh 与 arch/build_arch_pkg.sh source，不单独执行。
# shellcheck shell=bash

set -euo pipefail

PKG_NAME="blue-whale-pet"
APP_NAME_ZH="蓝鲸桌宠"
APP_VERSION="${BWP_VERSION:-1.0.0}"
PKG_REL="${BWP_PKGREL:-1}"
MAINTAINER="${BWP_MAINTAINER:-Blue Whale Pet Team <blue-whale-pet@example.com>}"

if [ -t 1 ]; then
  C_BLUE=$'\033[1;34m'; C_YELLOW=$'\033[1;33m'; C_RED=$'\033[1;31m'; C_GREEN=$'\033[1;32m'; C_RESET=$'\033[0m'
else
  C_BLUE=""; C_YELLOW=""; C_RED=""; C_GREEN=""; C_RESET=""
fi

log()  { printf '%s[build]%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok()   { printf '%s[ ok  ]%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%s[warn]%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
die()  { printf '%s[error]%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; exit 1; }

# 从给定目录向上查找项目根（含 SPEC.md 与 src/main.py）
project_root_from() {
  local d
  d=$(cd -- "${1:?project_root_from 需要起始目录}" && pwd) || die "目录不存在: $1"
  while [ "$d" != "/" ]; do
    if [ -f "$d/SPEC.md" ] && [ -f "$d/src/main.py" ]; then
      printf '%s\n' "$d"
      return 0
    fi
    d=$(dirname -- "$d")
  done
  die "无法定位项目根目录（应位于 blue-whale-pet/packaging/linux 下运行）"
}

# 由 app.png 补齐 hicolor 各尺寸图标（已存在的不覆盖）
# 用法: ensure_hicolor <app.png> <hicolor 目录> <尺寸...>
ensure_hicolor() {
  local png="$1" hicolor="$2"
  shift 2
  if [ ! -f "$png" ]; then
    warn "缺少 $png，无法补齐 hicolor 图标"
    return 0
  fi
  if ! python3 -c 'import PIL' >/dev/null 2>&1; then
    warn "python3 缺少 Pillow，跳过高清图标补齐（资产应已自带 hicolor 图标）"
    return 0
  fi
  python3 - "$png" "$hicolor" "$@" <<'PY'
import sys
from pathlib import Path
from PIL import Image

src = Path(sys.argv[1])
root = Path(sys.argv[2])
sizes = [int(x) for x in sys.argv[3:]]
img = Image.open(src).convert("RGBA")
for n in sizes:
    dst = root / f"{n}x{n}" / "apps" / "blue-whale-pet.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file():
        continue
    img.resize((n, n), Image.LANCZOS).save(dst, "PNG")
    print(f"[icons] 由 app.png 生成 {n}x{n} 图标: {dst}")
PY
}

# 兜底：若资产中未提供矢量 SVG，则用内嵌 PNG 的 SVG 包装（保证 hicolor/scalable 存在）
# 用法: make_fallback_svg <app.png> <输出 svg>
make_fallback_svg() {
  local png="$1" out="$2"
  [ -f "$png" ] || { warn "缺少 $png，无法生成 SVG 兜底图标"; return 0; }
  python3 - "$png" "$out" <<'PY'
import base64
import sys
from pathlib import Path

png = Path(sys.argv[1])
out = Path(sys.argv[2])
b64 = base64.b64encode(png.read_bytes()).decode("ascii")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"\n'
    '     width="512" height="512" viewBox="0 0 512 512">\n'
    '  <title>蓝鲸桌宠</title>\n'
    f'  <image width="512" height="512" xlink:href="data:image/png;base64,{b64}"/>\n'
    '</svg>\n',
    encoding="utf-8",
)
print(f"[icons] 生成 SVG 兜底图标（内嵌 PNG）: {out}")
PY
}

# 把项目文件铺成安装树（deb 与 arch 共用布局）
# 用法: stage_tree <项目根> <debian 辅助目录> <目标根>
# 目标根布局:
#   usr/bin/blue-whale-pet
#   usr/lib/blue-whale-pet/{main.py,src/,assets/}
#   usr/share/applications/blue-whale-pet.desktop
#   usr/share/icons/hicolor/{NxN,scalable}/apps/blue-whale-pet.{png,svg}
#   usr/share/pixmaps/blue-whale-pet.png
#   usr/share/doc/blue-whale-pet/{copyright,README.md?}
#   usr/share/man/man1/blue-whale-pet.1
stage_tree() {
  local root="$1" debdir="$2" dest="$3"
  local lib="$dest/usr/lib/$PKG_NAME"

  [ -f "$root/src/main.py" ] || die "缺少 $root/src/main.py（核心应用尚未就绪？）"
  [ -f "$root/assets/mascot/manifest.json" ] || die "缺少 $root/assets/mascot/manifest.json（资产尚未就绪？）"

  log "铺设安装树: $dest"
  install -d "$lib" \
    "$dest/usr/bin" \
    "$dest/usr/share/applications" \
    "$dest/usr/share/icons/hicolor" \
    "$dest/usr/share/pixmaps" \
    "$dest/usr/share/doc/$PKG_NAME" \
    "$dest/usr/share/man/man1"

  # 1) 源码：保留 src/ 目录结构（引导壳以 __main__ 运行 src/main.py）
  rm -rf "$lib/src"
  tar -C "$root" --exclude='__pycache__' --exclude='*.py[co]' -cf - src \
    | tar -C "$lib" -xf -

  # 2) 资产：排除 source/（官方版权参考图，不随包分发）、preview/（开发用拼图）与缓存
  rm -rf "$lib/assets"
  install -d "$lib/assets"
  tar -C "$root/assets" \
      --exclude='source' --exclude='preview' \
      --exclude='__pycache__' --exclude='*.py[co]' \
      -cf - . | tar -C "$lib/assets" -xf -

  # 3) main.py 引导壳（必须在 /usr/lib/blue-whale-pet/main.py）
  install -m 0644 "$debdir/main.py.bootstrap" "$lib/main.py"

  # 4) 启动器 /usr/bin/blue-whale-pet
  install -m 0755 "$debdir/blue-whale-pet.launcher" "$dest/usr/bin/$PKG_NAME"

  # 5) 桌面文件
  install -m 0644 "$debdir/blue-whale-pet.desktop" \
    "$dest/usr/share/applications/$PKG_NAME.desktop"

  # 6) hicolor 图标
  if [ -d "$root/assets/icons/hicolor" ]; then
    tar -C "$root/assets/icons/hicolor" -cf - . \
      | tar -C "$dest/usr/share/icons/hicolor" -xf -
  else
    warn "assets/icons/hicolor 不存在，将仅用 app.png 生成各尺寸"
  fi
  ensure_hicolor "$root/assets/icons/app.png" "$dest/usr/share/icons/hicolor" \
    16 24 32 48 64 128 256 512

  local svg=""
  local cand
  for cand in \
    "$root/assets/icons/$PKG_NAME.svg" \
    "$root/assets/icons/blue-whale-pet.svg" \
    "$debdir/$PKG_NAME.svg"; do
    if [ -f "$cand" ]; then svg="$cand"; break; fi
  done
  install -d "$dest/usr/share/icons/hicolor/scalable/apps"
  if [ -n "$svg" ]; then
    install -m 0644 "$svg" "$dest/usr/share/icons/hicolor/scalable/apps/$PKG_NAME.svg"
  else
    warn "资产中缺少 blue-whale-pet.svg，生成 SVG 兜底图标（建议 asset-fish 补正式矢量图标）"
    make_fallback_svg "$root/assets/icons/app.png" \
      "$dest/usr/share/icons/hicolor/scalable/apps/$PKG_NAME.svg"
  fi

  # 7) pixmaps 兜底图标
  if [ -f "$root/assets/icons/app.png" ]; then
    install -m 0644 "$root/assets/icons/app.png" "$dest/usr/share/pixmaps/$PKG_NAME.png"
  fi

  # 8) 版权 / 文档 / man
  if [ -f "$debdir/copyright" ]; then
    install -m 0644 "$debdir/copyright" "$dest/usr/share/doc/$PKG_NAME/copyright"
  fi
  if [ -f "$root/LICENSE" ]; then
    install -m 0644 "$root/LICENSE" "$dest/usr/share/doc/$PKG_NAME/LICENSE"
  fi
  if [ -f "$debdir/$PKG_NAME.1" ]; then
    install -m 0644 "$debdir/$PKG_NAME.1" "$dest/usr/share/man/man1/$PKG_NAME.1"
  fi

  # 9) 统一权限（/mnt/c drvfs 源文件可能为 777）：
  #    目录 755；数据文件 644；仅 /usr/bin 启动器 755
  find "$dest" -type d -exec chmod 0755 {} + 2>/dev/null || true
  find "$dest" -type f ! -path "$dest/usr/bin/$PKG_NAME" -exec chmod 0644 {} + 2>/dev/null || true
  chmod 0755 "$dest/usr/bin/$PKG_NAME" 2>/dev/null || true

  # 10) 清理编译缓存
  find "$dest" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$dest" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

  ok "安装树就绪: $(du -sh "$dest" 2>/dev/null | cut -f1)"
}

# 统计包内容文件数（不含元数据目录）
count_payload_files() {
  local root="$1"
  ( cd "$root" && find . -path ./DEBIAN -prune -o -type f -print | wc -l )
}

# 打印文件 sha256（用于构建报告）
sha256_of() {
  local f="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -- "$f"
  else
    python3 - "$f" <<'PY'
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 20), b""):
        h.update(chunk)
print(h.hexdigest() + "  " + sys.argv[1])
PY
  fi
}
