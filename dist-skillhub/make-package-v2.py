# -*- coding: utf-8 -*-
"""打包 SkillHub v2.0.0（skill-v2 目录）为 zip。

与 v1.x 不同：v2 是纯方法论 Skill，只有 4 个 md 文件。
"""
import os
import zipfile

BASE = r"E:\workbuddy-data\finance-tax-compliance\dist-skillhub"
SRC = os.path.join(BASE, "skill-v2")
OUT = os.path.join(BASE, "finance-tax-compliance.zip")  # 覆盖交付路径
EXCL = {"__pycache__", ".git", "logs"}
EXCL_EXT = {".pyc", ".pyo", ".db", ".log", ".zip", ".tmp", ".bak", ".DS_Store"}

if os.path.exists(OUT):
    os.remove(OUT)

n = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in EXCL]
        for fn in files:
            if os.path.splitext(fn)[1] in EXCL_EXT:
                continue
            p = os.path.join(root, fn)
            # 顶层目录名保持 skill slug
            arc = "finance-tax-compliance/" + os.path.relpath(p, SRC).replace("\\", "/")
            z.write(p, arc)
            n += 1

size = os.path.getsize(OUT)
print("files : %d (limit 200) %s" % (n, "OK" if n <= 200 else "OVER"))
print("size  : %.3f MB (limit 10 MB) %s"
      % (size / 1048576, "OK" if size <= 10 * 1048576 else "OVER"))
print("output:", OUT)

with zipfile.ZipFile(OUT) as z:
    names = z.namelist()
    for need in ["SKILL.md", "README.md", "COMPLIANCE.md",
                 "references/tax-quick-reference.md"]:
        key = "finance-tax-compliance/" + need
        print("  %-44s %s" % (need, "OK" if key in names else "MISSING"))
