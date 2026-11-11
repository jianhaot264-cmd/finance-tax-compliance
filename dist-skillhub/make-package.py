#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从仓库源码一键重建 SkillHub 上传包。

zip 二进制不入库（.gitignore 含 *.zip），因此换机器后用它重建：
    python dist-skillhub/make-package.py

产物：dist-skillhub/finance-tax-compliance.zip（约 0.82 MB，63 文件）
"""
import os
import sys
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "finance-tax-compliance")
OUT = os.path.join(BASE, "finance-tax-compliance.zip")

EXCL_DIR = {"__pycache__", ".git"}
EXCL_EXT = {".pyc", ".pyo", ".db", ".DS_Store", ".zip"}

REQUIRED = [
    "SKILL.md",
    "run.py",
    "README.md",
    "bin/server.py",
    "bin/build_v5.py",
    "bin/kb.json",
    "bin/corpus-articles.json",
]


def main():
    if not os.path.isdir(SRC):
        print("[error] 找不到源码目录：%s" % SRC)
        return 1

    missing = [r for r in REQUIRED if not os.path.exists(os.path.join(SRC, r))]
    if missing:
        print("[error] 缺少必要文件：")
        for m in missing:
            print("   ", m)
        return 1

    if os.path.exists(OUT):
        os.remove(OUT)

    n = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, dirs, files in os.walk(SRC):
            dirs[:] = [d for d in dirs if d not in EXCL_DIR]
            for fn in files:
                if os.path.splitext(fn)[1] in EXCL_EXT or fn == ".DS_Store":
                    continue
                p = os.path.join(root, fn)
                arc = "finance-tax-compliance/" + os.path.relpath(p, SRC).replace("\\", "/")
                z.write(p, arc)
                n += 1

    size = os.path.getsize(OUT)
    print("files : %d (limit 200) %s" % (n, "OK" if n <= 200 else "OVER"))
    print("size  : %.2f MB (limit 10 MB) %s"
          % (size / 1048576, "OK" if size <= 10 * 1048576 else "OVER"))
    print("output: %s" % OUT)
    if n > 200 or size > 10 * 1048576:
        print("\n[error] 超出 SkillHub 限制，请检查是否误入大文件。")
        return 1
    print("\n[ok] 可直接上传到 SkillHub")
    return 0


if __name__ == "__main__":
    sys.exit(main())
