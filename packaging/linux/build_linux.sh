#!/usr/bin/env bash
# =============================================================================
# 蓝鲸桌宠 Linux 打包脚本（Debian 13 trixie / Ubuntu 测试；WSL2 内直接运行）
# =============================================================================
# 产物（默认输出到 <项目>/release/linux/）：
#   blue-whale-pet_1.0.0_all.deb                  Debian/Ubuntu 安装包
#   blue-whale-pet-1.0.0-1-any.pkg.tar.zst        Arch 预构建包（手工 tar+zstd，无需 pacman）
#   blue-whale-pet-1.0.0.tar.gz                   Arch PKGBUILD 使用的源码 tarball
#   PKGBUILD                                     可直接 makepkg 的 PKGBUILD（sha256 已填入）
#   blue-whale-pet.install                        PKGBUILD 引用的 Arch 安装脚本
#   BlueWhalePet-Linux-x86_64                     （可选 --pyinstaller）单文件版
#
# 依赖（Debian/Ubuntu）：
#   sudo apt-get install -y python3 python3-tk python3-pil python3-pil.imagetk \
#        dpkg-dev zstd fakeroot xvfb x11-utils xdotool
#   Arch 打包的 .MTREE 需要 bsdtar：apt-get install -y libarchive-tools（可选）
#
# 用法：
#   bash packaging/linux/build_linux.sh                # deb + arch
#   bash packaging/linux/build_linux.sh --pyinstaller  # 额外构建单文件版
#   bash packaging/linux/build_linux.sh --no-deb --no-arch --pyinstaller
#   选项：--no-deb --no-arch --pyinstaller --keep-work --out DIR -h
# =============================================================================
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

usage() {
  cat <<'EOF'
蓝鲸桌宠 Linux 打包脚本

用法: bash packaging/linux/build_linux.sh [选项]

选项:
  --no-deb        跳过 .deb 构建
  --no-arch       跳过 Arch pkg.tar.zst 构建
  --pyinstaller   额外构建 PyInstaller onefile Linux 单文件版（需已安装 pyinstaller）
  --keep-work     保留 /tmp 下的构建临时目录（排查问题用）
  --out DIR       指定产物输出目录（默认 <项目根>/release/linux）
  -h, --help      显示本帮助

示例:
  bash packaging/linux/build_linux.sh
  bash packaging/linux/build_linux.sh --pyinstaller
  bash packaging/linux/build_linux.sh --no-deb --out /tmp/out
EOF
}

BUILD_DEB=1
BUILD_ARCH=1
BUILD_PYI=0
KEEP_WORK=0
OUT_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --no-deb)     BUILD_DEB=0 ;;
    --no-arch)    BUILD_ARCH=0 ;;
    --pyinstaller) BUILD_PYI=1 ;;
    --keep-work)  KEEP_WORK=1 ;;
    --out)
      [ $# -ge 2 ] || die "--out 需要一个目录参数"
      OUT_DIR="$2"; shift ;;
    --out=*)      OUT_DIR="${1#*=}" ;;
    -h|--help)    usage; exit 0 ;;
    *)            die "未知参数: $1（-h 查看帮助）" ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# 基础检查
# ---------------------------------------------------------------------------
ROOT="$(project_root_from "$SCRIPT_DIR/../..")"
[ -n "$OUT_DIR" ] || OUT_DIR="$ROOT/release/linux"
mkdir -p "$OUT_DIR"
OUT_DIR=$(cd -- "$OUT_DIR" && pwd)

log "项目根目录 : $ROOT"
log "输出目录   : $OUT_DIR"
log "包名/版本  : $PKG_NAME $APP_VERSION (Arch pkgrel=$PKG_REL)"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令 $1（$2）"
}
require_cmd python3 "apt-get install -y python3"
require_cmd tar "apt-get install -y tar"
require_cmd zstd "apt-get install -y zstd"
if [ "$BUILD_DEB" = 1 ]; then
  require_cmd dpkg-deb "apt-get install -y dpkg-dev"
fi

python3 - <<'PYCHK' || die "python3 缺少 tkinter/Pillow(ImageTk)，请安装 python3-tk python3-pil python3-pil.imagetk"
try:
    import tkinter
    import PIL
    import PIL.ImageTk  # noqa: F401
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"[check] python3 依赖不完整: {exc}")
print(f"[check] tkinter {tkinter.TkVersion} / Pillow {PIL.__version__} / ImageTk OK")
PYCHK

[ -f "$ROOT/src/main.py" ] || die "缺少 $ROOT/src/main.py"
[ -f "$ROOT/assets/mascot/manifest.json" ] || die "缺少 $ROOT/assets/mascot/manifest.json（资产未就绪？）"
[ -f "$ROOT/assets/icons/app.png" ] || warn "缺少 assets/icons/app.png（图标可能不完整）"

# ---------------------------------------------------------------------------
# 临时工作目录（默认 /tmp，避免占用 Windows C 盘可见路径的空间）
# ---------------------------------------------------------------------------
if [ -n "${BWP_WORK_DIR:-}" ]; then
  WORK="$BWP_WORK_DIR"
  mkdir -p "$WORK"
else
  WORK=$(mktemp -d "${TMPDIR:-/tmp}/${PKG_NAME}-build.XXXXXX")
fi
log "临时构建目录: $WORK"

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  if [ "$KEEP_WORK" = 1 ]; then
    log "已保留临时构建目录: $WORK"
  else
    rm -rf "$WORK"
  fi
  exit "$rc"
}
trap cleanup EXIT INT TERM

START_TIME=$(date +%s)

# ---------------------------------------------------------------------------
# 1) .deb 构建
# ---------------------------------------------------------------------------
build_deb() {
  log "================== 构建 .deb =================="
  local root="$WORK/deb-root"
  local deb="$OUT_DIR/${PKG_NAME}_${APP_VERSION}_all.deb"
  local recommends=""

  rm -rf "$root"
  stage_tree "$ROOT" "$SCRIPT_DIR/debian" "$root"
  install -d "$root/DEBIAN"

  # Recommends 仅当 Debian 仓库确实提供 python3-pystray 时写入（符合 SPEC §7.2）
  if [ "${BWP_PYSTRAY_RECOMMENDS:-auto}" = "auto" ] \
     && command -v apt-cache >/dev/null 2>&1 \
     && apt-cache show python3-pystray >/dev/null 2>&1; then
    recommends="Recommends: python3-pystray"
    log "Debian 仓库提供 python3-pystray → 写入 Recommends"
  else
    log "Debian 仓库无 python3-pystray（或非 apt 环境）→ 不写 Recommends"
  fi

  local installed_size
  installed_size=$(du -sk --exclude=DEBIAN "$root" | cut -f1)

  sed -e "s|@VERSION@|$APP_VERSION|g" \
      -e "s|@MAINTAINER@|$MAINTAINER|g" \
      -e "s|@INSTALLED_SIZE@|$installed_size|g" \
      "$SCRIPT_DIR/debian/control" | grep -v '^@RECOMMENDS@$' > "$root/DEBIAN/control"
  if [ -n "$recommends" ]; then
    awk -v rec="$recommends" '{print} /^Depends:/{print rec}' \
      "$root/DEBIAN/control" > "$root/DEBIAN/control.tmp"
    mv "$root/DEBIAN/control.tmp" "$root/DEBIAN/control"
  fi

  install -m 0755 "$SCRIPT_DIR/debian/postinst" "$root/DEBIAN/postinst"
  install -m 0755 "$SCRIPT_DIR/debian/postrm" "$root/DEBIAN/postrm"

  # md5sums（路径相对根、不带 ./ 前缀，符合 dpkg 规范）
  (
    cd "$root"
    find . -path ./DEBIAN -prune -o -type f -printf '%P\0' \
      | sort -z | xargs -0 md5sum > DEBIAN/md5sums
  )

  log "Installed-Size: ${installed_size} KiB / 文件数: $(count_payload_files "$root")"
  rm -f "$deb"
  dpkg-deb --root-owner-group -Zxz --build "$root" "$deb" >/dev/null
  chmod 0644 "$deb"
  ok "生成: $deb ($(du -h "$deb" | cut -f1))"
  validate_deb "$deb"
  sha256_of "$deb"
}

validate_deb() {
  local deb="$1" missing=0 f
  log "静态校验 .deb ..."

  local pkg ver arch
  pkg=$(dpkg-deb --field "$deb" Package)
  ver=$(dpkg-deb --field "$deb" Version)
  arch=$(dpkg-deb --field "$deb" Architecture)
  [ "$pkg" = "$PKG_NAME" ] || die "control Package 错误: $pkg"
  [ "$ver" = "$APP_VERSION" ] || die "control Version 错误: $ver"
  [ "$arch" = "all" ] || die "control Architecture 错误: $arch"

  local deps
  deps=$(dpkg-deb --field "$deb" Depends)
  for d in "python3 (>= 3.9)" "python3-tk" "python3-pil" "python3-pil.imagetk"; do
    case "$deps" in
      *"$d"*) ;;
      *) die "Depends 缺少: $d（实际: $deps）" ;;
    esac
  done

  local filelist
  filelist=$(dpkg-deb --fsys-tarfile "$deb" | tar -tf -)
  local expected=(
    "./usr/bin/$PKG_NAME"
    "./usr/lib/$PKG_NAME/main.py"
    "./usr/lib/$PKG_NAME/src/main.py"
    "./usr/lib/$PKG_NAME/assets/mascot/manifest.json"
    "./usr/share/applications/$PKG_NAME.desktop"
    "./usr/share/man/man1/$PKG_NAME.1"
    "./usr/share/pixmaps/$PKG_NAME.png"
    "./usr/share/icons/hicolor/scalable/apps/$PKG_NAME.svg"
    "./usr/share/doc/$PKG_NAME/copyright"
  )
  local n
  for n in 16 24 32 48 64 128 256 512; do
    expected+=("./usr/share/icons/hicolor/${n}x${n}/apps/$PKG_NAME.png")
  done
  for f in "${expected[@]}"; do
    if ! grep -Fxq -- "$f" <<<"$filelist"; then
      warn "deb 缺少文件: $f"; missing=1
    fi
  done
  [ "$missing" = 0 ] || die "deb 结构校验失败"

  # 启动器内容
  dpkg-deb --fsys-tarfile "$deb" | tar -xOf - "./usr/bin/$PKG_NAME" \
    | grep -q 'exec python3 /usr/lib/blue-whale-pet/main.py' \
    || die "启动器内容不正确（应 exec python3 /usr/lib/blue-whale-pet/main.py）"
  # desktop 文件关键字段
  dpkg-deb --fsys-tarfile "$deb" | tar -xOf - "./usr/share/applications/$PKG_NAME.desktop" \
    | grep -q '^Icon=blue-whale-pet$' || die "desktop 缺少 Icon=blue-whale-pet"
  # 启动器可执行位
  local mode
  mode=$(dpkg-deb --fsys-tarfile "$deb" | tar -tvf - | awk '$NF == "./usr/bin/'"$PKG_NAME"'" {print $1}')
  [ "$mode" = "-rwxr-xr-x" ] || warn "启动器权限位为 $mode（期望 -rwxr-xr-x）"

  # 数据文件权限应为 644（源码/资产/desktop/man）
  local f m
  for f in \
    "./usr/lib/$PKG_NAME/src/main.py" \
    "./usr/lib/$PKG_NAME/assets/mascot/manifest.json" \
    "./usr/share/applications/$PKG_NAME.desktop" \
    "./usr/share/man/man1/$PKG_NAME.1"; do
    m=$(dpkg-deb --fsys-tarfile "$deb" | tar -tvf - | awk -v p="$f" '$NF == p {print $1}')
    [ "$m" = "-rw-r--r--" ] || warn "文件权限非 644: $f = $m"
  done

  # lintian 风格的桌面文件校验（若装有 desktop-file-utils）
  if command -v desktop-file-validate >/dev/null 2>&1; then
    dpkg-deb --fsys-tarfile "$deb" | tar -xOf - "./usr/share/applications/$PKG_NAME.desktop" \
      > "$WORK/tmp.desktop"
    desktop-file-validate "$WORK/tmp.desktop" && ok "desktop-file-validate 通过"
  fi

  ok "deb 结构校验通过（$(wc -l <<<"$filelist") 项）"
}

# ---------------------------------------------------------------------------
# 2) Arch 包构建（调用 arch/build_arch_pkg.sh：手工 tar+zstd，无需 pacman）
# ---------------------------------------------------------------------------
build_arch() {
  log "================== 构建 Arch 包 =================="
  bash "$SCRIPT_DIR/arch/build_arch_pkg.sh" \
    --project-root "$ROOT" \
    --debian-dir "$SCRIPT_DIR/debian" \
    --out "$OUT_DIR" \
    --work "$WORK/arch" \
    --version "$APP_VERSION" \
    --pkgrel "$PKG_REL" \
    --maintainer "$MAINTAINER"
}

# ---------------------------------------------------------------------------
# 3) 可选：PyInstaller 单文件版
# ---------------------------------------------------------------------------
build_pyinstaller() {
  log "================== 可选：PyInstaller Linux 单文件版 =================="
  if ! python3 -c "import PyInstaller" >/dev/null 2>&1; then
    warn "未安装 PyInstaller，跳过单文件版（pip install pyinstaller 后可重试）"
    return 0
  fi
  local name="BlueWhalePet-Linux-x86_64"
  local stage="$WORK/pyi-assets"
  rm -rf "$stage"
  install -d "$stage/assets"
  # 与 deb 一致：排除 assets/source（参考原图）
  tar -C "$ROOT/assets" --exclude='source' --exclude='__pycache__' -cf - . \
    | tar -C "$stage/assets" -xf -

  python3 -m PyInstaller \
    --onefile --noconfirm --clean --log-level WARN \
    --name "$name" \
    --add-data "$stage/assets:assets" \
    --hidden-import PIL._tkinter_finder \
    --hidden-import PIL.ImageTk \
    --hidden-import PIL._imagingtk \
    --distpath "$WORK/pyi-dist" \
    --workpath "$WORK/pyi-work" \
    --specpath "$WORK" \
    "$ROOT/src/main.py" || die "PyInstaller 构建失败"

  install -m 0755 "$WORK/pyi-dist/$name" "$OUT_DIR/$name"
  ok "生成: $OUT_DIR/$name ($(du -h "$OUT_DIR/$name" | cut -f1))"
  # 冒烟：--version（不需要 DISPLAY）
  if "$OUT_DIR/$name" --version >/dev/null 2>&1; then
    ok "单文件版 --version 冒烟通过"
  else
    warn "单文件版 --version 冒烟失败（glibc/环境兼容问题，仅供参考）"
  fi
  # 冒烟：--selftest（xvfb 无头，验证 Tk/ImageTk 在冻结态可用）
  if command -v xvfb-run >/dev/null 2>&1; then
    local pyi_rc=0
    xvfb-run -a -s "-screen 0 1280x800x24" "$OUT_DIR/$name" --selftest \
      > "$WORK/pyi-selftest.log" 2>&1 || pyi_rc=$?
    if [ "$pyi_rc" = 0 ] && grep -q '^SELFTEST OK' "$WORK/pyi-selftest.log"; then
      ok "单文件版 --selftest（xvfb）通过"
    else
      warn "单文件版 --selftest 失败（rc=$pyi_rc），详见构建目录 pyi-selftest.log"
      tail -3 "$WORK/pyi-selftest.log" >&2 || true
    fi
  fi
  sha256_of "$OUT_DIR/$name"
}

# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
[ "$BUILD_DEB" = 1 ] && build_deb
[ "$BUILD_ARCH" = 1 ] && build_arch
[ "$BUILD_PYI" = 1 ] && build_pyinstaller

END_TIME=$(date +%s)
log "================== 构建完成（$((END_TIME - START_TIME))s） =================="
log "产物目录: $OUT_DIR"
ls -lh "$OUT_DIR" 2>/dev/null || true
log "校验值（可写入 release/SHA256SUMS.txt）："
( cd "$OUT_DIR" && sha256sum blue-whale-pet_*_all.deb blue-whale-pet-*.pkg.tar.zst 2>/dev/null ) || true
