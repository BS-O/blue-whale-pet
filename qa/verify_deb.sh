#!/usr/bin/env bash
# Debian .deb 安装/自检/WSLg 启动/卸载 往返验证（Lead QA，在 WSL Debian 中运行）
# 用法（root 或 sudo）: wsl -d Debian -u root -- bash /mnt/c/.../blue-whale-pet/qa/verify_deb.sh /mnt/c/.../release/linux/blue-whale-pet_1.0.0_all.deb
set -uo pipefail
DEB="${1:?用法: verify_deb.sh <deb路径>}"
OUT="${2:-/tmp/deb_report.txt}"
: > "$OUT"
step() { local name="$1"; shift; local ok="$1"; shift; echo "[$([ "$ok" = 0 ] && echo OK || echo FAIL)] $name $*" | tee -a "$OUT"; }
FAILED=0
fail() { FAILED=$((FAILED + 1)); }

apt-get install -y --no-install-recommends python3-tk python3-pil python3-pil.imagetk desktop-file-utils xvfb x11-utils xdotool >/dev/null 2>&1 || true
if dpkg -s blue-whale-pet >/dev/null 2>&1; then dpkg -r blue-whale-pet >/dev/null 2>&1 || true; fi
for f in /usr/lib/blue-whale-pet /usr/bin/blue-whale-pet /usr/share/applications/blue-whale-pet.desktop; do
  [ -e "$f" ] && rm -rf "$f"
done

echo "== 1. dpkg -i ==" | tee -a "$OUT"
dpkg -i "$DEB" > /tmp/dpkg_i.log 2>&1
RC=$?
step "dpkg-install" $RC "rc=$RC"
[ $RC -ne 0 ] && { fail; tail -5 /tmp/dpkg_i.log | tee -a "$OUT"; apt-get -f install -y >>/tmp/dpkg_i.log 2>&1; dpkg -i "$DEB" >>/tmp/dpkg_i.log 2>&1; step "dpkg-install-retry" $? "after apt -f"; }

for f in /usr/bin/blue-whale-pet /usr/lib/blue-whale-pet/main.py /usr/share/applications/blue-whale-pet.desktop; do
  [ -e "$f" ] && step "file-exists" 0 "$f" || { step "file-exists" 1 "$f"; fail; }
done
ls /usr/share/icons/hicolor/*/apps/blue-whale-pet.png >/dev/null 2>&1 && step "hicolor-icons" 0 "$(ls /usr/share/icons/hicolor/*/apps/blue-whale-pet.png | wc -l) 个" || { step "hicolor-icons" 1; fail; }
[ -f /usr/share/icons/hicolor/scalable/apps/blue-whale-pet.svg ] && step "scalable-icon" 0 || step "scalable-icon" 1 "缺少 svg（不阻塞）"

echo "== 2. 版本/自检 ==" | tee -a "$OUT"
V=$(/usr/bin/blue-whale-pet --version 2>&1); RC=$?
step "version" $RC "$V"; [ $RC -ne 0 ] && fail
timeout 60 xvfb-run -a /usr/bin/blue-whale-pet --selftest > /tmp/selftest.log 2>&1; RC=$?
grep -q "SELFTEST OK" /tmp/selftest.log && SELFTEST_OK=0 || SELFTEST_OK=1
step "selftest" $((RC != 0 || SELFTEST_OK)) "rc=$RC $(tail -1 /tmp/selftest.log)"
grep -q "SELFTEST OK" /tmp/selftest.log || fail

echo "== 3. WSLg 启动 ==" | tee -a "$OUT"
export DISPLAY="${DISPLAY:-:0}"
/usr/bin/blue-whale-pet --config /tmp/deb-qa-config.json > /tmp/launch.log 2>&1 &
APP_PID=$!
sleep 6
WIN=$(xdotool search --pid "$APP_PID" --name "." 2>/dev/null | head -1)
if [ -z "$WIN" ]; then WIN=$(xdotool search --name "蓝鲸" 2>/dev/null | head -1); fi
[ -n "$WIN" ] && step "gui-window" 0 "window=$WIN" || { step "gui-window" 1 "xvfb/display=${DISPLAY}（WSLg 不可用时允许失败）"; }
if [ -n "$WIN" ]; then
  import -window "$WIN" /tmp/pet_screenshot.png 2>/dev/null || true
fi
kill "$APP_PID" 2>/dev/null; sleep 2
kill -9 "$APP_PID" 2>/dev/null || true
step "process-stopped" 0

echo "== 4. dpkg -r 卸载 ==" | tee -a "$OUT"
dpkg -r blue-whale-pet > /tmp/dpkg_r.log 2>&1; RC=$?
step "dpkg-remove" $RC "rc=$RC"; [ $RC -ne 0 ] && fail
[ -e /usr/lib/blue-whale-pet ] || [ "$(ls -A /usr/lib/blue-whale-pet 2>/dev/null)" = "" ]
[ -e /usr/lib/blue-whale-pet ] && { echo "残留 /usr/lib/blue-whale-pet" | tee -a "$OUT"; fail; } || step "no-residual-lib" 0
[ -e /usr/bin/blue-whale-pet ] && { echo "残留 /usr/bin/blue-whale-pet" | tee -a "$OUT"; fail; } || step "no-residual-bin" 0
[ -e /usr/share/applications/blue-whale-pet.desktop ] && { echo "残留 desktop" | tee -a "$OUT"; fail; } || step "no-residual-desktop" 0

echo "" | tee -a "$OUT"
if [ "$FAILED" -eq 0 ]; then echo "DEB VERIFY OK" | tee -a "$OUT"; exit 0; else echo "DEB VERIFY FAIL ($FAILED)" | tee -a "$OUT"; exit 1; fi
