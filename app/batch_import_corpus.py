# -*- coding: utf-8 -*-
"""batch_import_corpus.py — L0 逐字原文层批量导入驱动器（纯标准库）。

用途：把 IMPORT-BACKLOG.md 里剩余 16 个税种的「双官方源 URL 清单」补齐后，
      一条命令逐部走 fetch_corpus.py 的双源比对，全部通过才落盘，最后统一
      import_corpus.py 校验，并输出逐部结果报告。

用法：
  python batch_import_corpus.py                       # 读 knowledge-base/corpus/batch-sources.json
  python batch_import_corpus.py --dry-run            # 只做双源比对，不落盘
  python batch_import_corpus.py --sources <path>     # 指定清单
  python batch_import_corpus.py --only 印花税法        # 只跑名称含该串的条目

清单格式（knowledge-base/corpus/batch-sources.json）：
{
  "documents": [
    {
      "law": "中华人民共和国印花税法",
      "level": "法律",
      "status": "现行有效",
      "effective_date": "2022-07-01",
      "expiry_date": "",
      "doc_no": "",
      "expect": 20,
      "out": "stamp-duty-law-2021.md",
      "url_a": "https://www.gov.cn/...",
      "url_b": "https://fgk.chinatax.gov.cn/...",
      "note": "2021-06-10 通过，2022-07-01 施行"
    }
  ]
}

铁律：
  - 不猜测、不生成 URL；缺失 url_a/url_b 的条目直接标记 skipped；
  - 每部先 dry-run（双源逐条比对），不通过绝不写入；
  - 任一失败不阻断其余条目，最后汇总，便于分批补齐；
  - 逐字条文只能来自官方原文，模型不得复述。
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
CORPUS = os.path.join(ROOT, "knowledge-base", "corpus")
DEFAULT_SOURCES = os.path.join(CORPUS, "batch-sources.json")
REPORT = os.path.join(ROOT, "reports", "corpus-batch-report.json")
PY = sys.executable
FETCH = os.path.join(BASE, "fetch_corpus.py")
IMPORT = os.path.join(BASE, "import_corpus.py")


def run(args):
    return subprocess.run([PY] + args, cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def fetch_args(doc, dry):
    a = [FETCH, "--law", doc["law"], "--level", doc.get("level", "法律"),
         "--status", doc.get("status", "现行有效"),
         "--effective-date", doc.get("effective_date", ""),
         "--url-a", doc["url_a"], "--url-b", doc["url_b"],
         "--out", doc["out"], "--expect", str(doc.get("expect", 0)),
         "--note", doc.get("note", "")]
    if doc.get("doc_no"):
        a += ["--doc-no", doc["doc_no"]]
    if doc.get("expiry_date"):
        a += ["--expiry-date", doc["expiry_date"]]
    if dry:
        a.append("--dry-run")
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=DEFAULT_SOURCES)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-import", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.sources):
        print("[error] 缺少源清单：%s" % a.sources, flush=True)
        print("        请先按 IMPORT-BACKLOG.md 的检索词表逐部补齐 url_a / url_b。", flush=True)
        return 2
    src = json.load(open(a.sources, encoding="utf-8"))
    docs = [d for d in src.get("documents", []) if (not a.only or a.only in d.get("law", ""))]
    print("=== 批量导入 %d 部 | dry_run=%s ===" % (len(docs), a.dry_run), flush=True)

    results = []
    for i, doc in enumerate(docs, 1):
        name = doc.get("law", "")
        rec = {"law": name, "out": doc.get("out", ""), "status": "pending", "detail": ""}
        # expect 允许缺省/0：首次导入时未知官方条数，先 dry-run 由两源一致性兜底，
        # 拿到实际条数后再回填 expect 做「官方章条数」交叉校验。
        missing = [k for k in ("law", "out", "url_a", "url_b") if not doc.get(k)]
        if missing:
            rec["status"] = "skipped"
            rec["detail"] = "字段缺失：" + ", ".join(missing)
            print("[%d/%d] SKIP %s | %s" % (i, len(docs), name, rec["detail"]), flush=True)
            results.append(rec)
            continue
        r = run(fetch_args(doc, True))
        if r.returncode != 0:
            tail = (r.stdout or "").strip().splitlines()[-4:]
            rec["status"] = "verify_failed"
            rec["detail"] = " | ".join(tail)[:400]
            print("[%d/%d] FAIL(双源) %s | %s" % (i, len(docs), name, rec["detail"][:110]), flush=True)
            results.append(rec)
            continue
        if a.dry_run:
            rec["status"] = "dry_ok"
            print("[%d/%d] DRY_OK %s" % (i, len(docs), name), flush=True)
            results.append(rec)
            continue
        r2 = run(fetch_args(doc, False))
        if r2.returncode != 0:
            rec["status"] = "write_failed"
            rec["detail"] = ((r2.stdout or "") + (r2.stderr or ""))[-400:]
            print("[%d/%d] FAIL(写入) %s" % (i, len(docs), name), flush=True)
        else:
            rec["status"] = "ok"
            rec["detail"] = "双源一致，已写入 corpus 并登记 manifest"
            print("[%d/%d] OK %s" % (i, len(docs), name), flush=True)
        results.append(rec)

    if not a.dry_run and not a.skip_import and any(x["status"] == "ok" for x in results):
        r = run([IMPORT])
        print("\n=== import_corpus.py rc=%s ===" % r.returncode, flush=True)
        for line in (r.stdout or "").strip().splitlines()[-6:]:
            print("   ", line, flush=True)

    ok = sum(1 for x in results if x["status"] in ("ok", "dry_ok"))
    bad = [x for x in results if x["status"] in ("verify_failed", "write_failed", "skipped")]
    report = {"date": date.today().isoformat(), "dry_run": a.dry_run,
              "total": len(results), "passed": ok, "failed": len(bad), "results": results}
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    json.dump(report, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n=== 汇总：%d/%d 通过，%d 待处理 -> %s ===" %
          (ok, len(results), len(bad), REPORT), flush=True)
    for x in bad:
        print("  - %s [%s] %s" % (x["law"], x["status"], x["detail"][:100]), flush=True)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
