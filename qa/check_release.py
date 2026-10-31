"""release 产物完整性 + SHA256 校验（Lead QA）。

用法: py qa/check_release.py [--project PATH] [--write-manifest]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

EXPECTED = [
    ("windows", "BlueWhalePet-Portable-1.0.0.exe", "MZ"),
    ("windows", "BlueWhalePet-Setup-1.0.0.exe", "MZ"),
    ("linux", "blue-whale-pet_1.0.0_all.deb", "!<arch>"),
    ("linux", "blue-whale-pet-1.0.0-1-any.pkg.tar.zst", "zst"),
    ("linux", "PKGBUILD", "text"),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def magic_ok(p: Path, kind: str) -> bool:
    head = p.open("rb").read(8)
    if kind == "MZ":
        return head[:2] == b"MZ"
    if kind == "!<arch>":
        return head[:7] == b"!<arch>"
    if kind == "zst":
        return head[:4] == bytes([0x28, 0xB5, 0x2F, 0xFD])
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--write-manifest", action="store_true")
    args = ap.parse_args()
    root = Path(args.project) / "release"
    rows, errors = [], []
    for sub, name, kind in EXPECTED:
        p = root / sub / name
        if not p.exists():
            errors.append(f"缺少 {p}")
            continue
        if p.stat().st_size < 1024:
            errors.append(f"{p} 体积异常 {p.stat().st_size}B")
        if not magic_ok(p, kind):
            errors.append(f"{p} 文件头不是 {kind}")
        rows.append({"path": str(p.relative_to(root.parent)), "size": p.stat().st_size,
                     "sha256": sha256(p)})
    # 逐项对比已有 SHA256SUMS
    sums = root / "SHA256SUMS.txt"
    if sums.exists():
        declared = {}
        for line in sums.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2:
                declared[parts[1].lstrip("*")] = parts[0]
        for r in rows:
            rel = r["path"].replace("\\", "/").split("release/", 1)[-1]
            if rel not in declared:
                errors.append(f"SHA256SUMS 缺少 {rel}")
            elif declared[rel] != r["sha256"]:
                errors.append(f"SHA256 不匹配 {rel}")
    else:
        errors.append("缺少 release/SHA256SUMS.txt")
    print(f"{'file':58s} {'size':>12s}  sha256")
    for r in rows:
        print(f"{r['path']:58s} {r['size']:12d}  {r['sha256'][:16]}...")
    if args.write_manifest:
        (root / "release_manifest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        print(f"\nFAIL {len(errors)}:")
        for e in errors:
            print(" -", e)
        return 1
    print("RELEASE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
