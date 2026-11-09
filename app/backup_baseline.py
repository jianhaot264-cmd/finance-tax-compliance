# -*- coding: utf-8 -*-
"""backup_baseline.py — 生成项目基线归档（写 .tmp → 校验 → 原子改名 + 逐文件 SHA256）。

用法：
    python backup_baseline.py            # 默认 v10 / 日期取今天
    python backup_baseline.py v11 2026-11-15

产物：backups/baseline-<版本>-<日期>.zip 与 -manifest.json
"""
import hashlib
import json
import os
import sys
import zipfile
from datetime import date, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
OUT_DIR = os.path.join(ROOT, "backups")

INCLUDE_DIRS = [
    ("knowledge-base", (".md",)),
    ("app", (".py", ".json", ".md", ".db", ".bat")),
    ("app/static", (".html", ".css", ".js", ".svg")),
    ("reports", (".md", ".html", ".json", ".csv", ".png")),
    ("reports/policy-radar", (".md", ".json")),
]
ROOT_FILES = ["context-handoff-v9-2026-11-08.md", "context-handoff-v10-2026-11-09.md",
              "context-handoff-v11-2026-11-09.md"]


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main():
    ver = sys.argv[1] if len(sys.argv) > 1 else "v10"
    day = sys.argv[2] if len(sys.argv) > 2 else date.today().isoformat()
    stem = f"baseline-{ver}-{day}"
    zip_path = os.path.join(OUT_DIR, stem + ".zip")
    tmp = zip_path + ".tmp"
    man_path = os.path.join(OUT_DIR, stem + "-manifest.json")

    files = []
    for rel, exts in INCLUDE_DIRS:
        d = os.path.join(ROOT, rel)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            p = os.path.join(d, fn)
            if not os.path.isfile(p) or not fn.endswith(exts):
                continue
            if rel == "app" and fn.startswith("kb-pre-enrich"):
                continue
            files.append(os.path.relpath(p, ROOT).replace("\\", "/"))
    for fn in ROOT_FILES:
        p = os.path.join(ROOT, fn)
        if os.path.isfile(p):
            files.append(fn)

    files = sorted(set(files))
    os.makedirs(OUT_DIR, exist_ok=True)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            z.write(os.path.join(ROOT, rel), rel)
    with zipfile.ZipFile(tmp) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit(f"[abort] zip 校验失败: {bad}")
        n = len(z.namelist())
    if n != len(files):
        raise SystemExit(f"[abort] 文件数不一致: zip={n} list={len(files)}")

    manifest = {
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "version": ver,
        "count": len(files),
        "files": [{"path": rel, "size": os.path.getsize(os.path.join(ROOT, rel)),
                   "sha256_16": sha16(os.path.join(ROOT, rel))} for rel in files],
    }
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    os.replace(tmp, zip_path)
    print(f"[ok] {zip_path}  files={n}  size={os.path.getsize(zip_path)}")


if __name__ == "__main__":
    main()
