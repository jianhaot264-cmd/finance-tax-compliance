# -*- coding: utf-8 -*-
"""import_corpus.py — L0 逐字原文层校验与导入（纯标准库）。

流程：knowledge-base/corpus/manifest.json + *.md
      -> 校验（UTF-8 / 文号唯一 / 时效四态 / 双源 / 条号格式 / SHA256 / 去重）
      -> app/corpus-articles.json（供 build_v5.py 写入 article_text）

设计：L0 不进 build_kb.py 的 FILES，不参与主检索索引；逐字内容不得改写。
用法：python import_corpus.py
"""
import hashlib
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.normpath(os.path.join(BASE, "..", "knowledge-base", "corpus"))
MANIFEST = os.path.join(CORPUS, "manifest.json")
OUT = os.path.join(BASE, "corpus-articles.json")

VALID_STATUS = {"现行有效", "已废止", "修订中", "草案阶段"}
HEAD_RE = re.compile(r"^##\s*《(.+?)》(第[一二三四五六七八九十百零\d]+条)\s*$")


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    if not os.path.exists(MANIFEST):
        print("[error] 缺少 manifest.json:", MANIFEST)
        return 2
    with open(MANIFEST, "r", encoding="utf-8") as f:
        man = json.load(f)

    errors, articles, seen, seen_docno = [], [], set(), set()
    for doc in man.get("documents", []):
        did = doc.get("doc_id", "")
        path = os.path.join(CORPUS, doc.get("file", ""))
        if not os.path.exists(path):
            errors.append(f"{did}: 文件不存在 {path}")
            continue
        try:
            text = open(path, "r", encoding="utf-8").read()
        except UnicodeDecodeError as ex:
            errors.append(f"{did}: 非 UTF-8 {ex}")
            continue
        digest = sha256_text(text)
        doc["sha256"] = digest

        status = doc.get("status", "")
        if status not in VALID_STATUS:
            errors.append(f"{did}: 时效状态非法 {status!r}")
        if int(doc.get("source_count") or 0) < 2 or len(doc.get("sources") or []) < 2:
            errors.append(f"{did}: 未达双源交叉")
        docno = (doc.get("doc_no") or "").strip()
        if docno:
            if docno in seen_docno:
                errors.append(f"{did}: 文号重复 {docno}")
            seen_docno.add(docno)

        # 解析逐字条文块
        cur, buf = None, []
        blocks = []

        def flush():
            if cur:
                body = "\n".join(buf).strip()
                body = "\n".join(ln for ln in body.splitlines()
                                 if not ln.strip().startswith(">"))
                blocks.append((cur[0], cur[1], body.strip()))

        for line in text.splitlines():
            m = HEAD_RE.match(line.strip())
            if m:
                flush()
                cur, buf = (m.group(1).strip(), m.group(2).strip()), []
            elif cur:
                buf.append(line)
        flush()

        if not blocks:
            errors.append(f"{did}: 未解析到任何逐字条文")
        expected = int(doc.get("article_count") or 0)
        if expected and len(blocks) != expected:
            errors.append(f"{did}: 条数不符 manifest={expected} 实际={len(blocks)}")

        for law, art, verbatim in blocks:
            if not verbatim or len(verbatim) < 10:
                errors.append(f"{did}: {law} {art} 原文为空或过短")
                continue
            key = (law, art)
            if key in seen:
                continue  # 与 23 文件解析来源重叠时按 (法规名, 条号) 去重
            seen.add(key)
            articles.append({
                "doc_id": did, "law_name": law, "article_no": art,
                "verbatim": verbatim, "effect_level": doc.get("level", ""),
                "validity": status, "source_db": "官方原文层 L0（双源核验）",
                "source_url": (doc.get("sources") or [""])[0],
                "source_file": doc.get("file", ""),
                "verified_at": doc.get("verified_at") or man.get("verified_at", ""),
                "sha256": digest,
            })
        print(f"[doc] {did}: {len(blocks)} 条, sha256={digest[:16]}…")

    if errors:
        print("\n[校验失败]")
        for e in errors:
            print("  -", e)
        return 2

    out = {
        "generated_at": man.get("generated_at", ""),
        "verified_at": man.get("verified_at", ""),
        "layer": "L0 逐字原文层（不进 FILES / 不参与主检索索引）",
        "documents": len(man.get("documents", [])),
        "articles": articles,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    print(f"\n[ok] 校验通过：{len(articles)} 条唯一逐字条文 -> {OUT}")
    print("[ok] manifest.json 已回写 SHA256")
    return 0


if __name__ == "__main__":
    sys.exit(main())
