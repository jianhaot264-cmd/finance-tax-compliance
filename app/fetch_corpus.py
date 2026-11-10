# -*- coding: utf-8 -*-
"""fetch_corpus.py — L0 逐字原文层抓取与双源比对（纯标准库）。

作用：从两个官方源抓取同一部法规的正文，按「第X条」拆条，逐条比对；
      只有两源条数一致且条文实质一致时才写出 corpus md 并登记 manifest。
      不通过则退出码 2、不写任何文件（避免把未核验内容混入 L0）。

用法：
  python fetch_corpus.py --law "中华人民共和国增值税法" --level 法律 \
     --status 现行有效 --effective-date 2026-01-01 \
     --url-a https://www.gov.cn/... --url-b https://fgk.chinatax.gov.cn/... \
     --out vat-law-2024.md --expect 38 [--doc-no ""] [--note "..."] [--dry-run]

设计约束：
  - 只做「原文搬运」，不改写、不概括、不补全；
  - 拆条只认段首「第X条」，正文中「增值税法第三条所称…」不会被误切；
  - 条号必须从第一条起连续，断号即判失败。
"""
import argparse
import difflib
import html as htmllib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.normpath(os.path.join(BASE, "..", "knowledge-base", "corpus"))
MANIFEST = os.path.join(CORPUS, "manifest.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

ART_HEAD = re.compile(r"^第([一二三四五六七八九十百零]+)条[\s\u3000]*")
CHAPTER_HEAD = re.compile(r"^第[一二三四五六七八九十百零]+章[\s\u3000]*")
PAGE_NOISE = ("主办单位：", "版权所有", "京ICP备", "京公网安备", "网站标识码",
              "忘记密码", "扫一扫", "打印本页", "关闭窗口", "责任编辑", "分享到",
              "网站地图", "联系我们", "中国政府网微博", "中文域名", "【字体：")
CN_NUM = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9}


def cn2int(s):
    """中文条号 -> 整数（支持到 999）。"""
    if not s:
        return 0
    total, section, num = 0, 0, 0
    for ch in s:
        if ch in CN_NUM:
            num = CN_NUM[ch]
        elif ch == "十":
            section += (num or 1) * 10
            num = 0
        elif ch == "百":
            section += (num or 1) * 100
            num = 0
        else:
            return 0
    return total + section + num


def fetch(url, retries=2, timeout=30):
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            for enc in ("utf-8", "gb18030"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", errors="replace")
        except Exception as ex:  # noqa: BLE001
            last = ex
            if i < retries:
                time.sleep(1.5)
    raise RuntimeError("抓取失败 %s: %s" % (url, last))


def parse_articles(html_text):
    """按 <p> 段拆条；仅段首「第X条」视为新条开始。"""
    ps = re.findall(r"<p[^>]*>(.*?)</p>", html_text, re.S)
    arts, cur, buf = [], None, []
    for p in ps:
        t = re.sub(r"<[^>]+>", "", p)
        t = htmllib.unescape(t).replace("\u3000", " ").replace("\xa0", " ").strip()
        if not t:
            continue
        if CHAPTER_HEAD.match(t) or any(n in t for n in PAGE_NOISE):
            continue
        m = ART_HEAD.match(t)
        if m:
            if cur:
                arts.append((cur, "\n".join(buf).strip()))
            cur, buf = "第%s条" % m.group(1), [ART_HEAD.sub("", t, count=1).strip()]
        elif cur:
            buf.append(t)
    if cur:
        arts.append((cur, "\n".join(buf).strip()))
    if arts:
        arts[-1] = (arts[-1][0], trim_effect(arts[-1][1]))
    return arts


def trim_effect(body):
    """末条若含施行表述，截断到该句末，剔除页面尾部噪声。"""
    for kw in ("施行。", "施行；"):
        i = body.rfind(kw)
        if i >= 0:
            return body[:i + len(kw)]
    return body


def norm(s):
    """比对用归一化：NFKC 统一全角/半角（＋→+、（）→()、全角数字等）并去空白。
    只消除排版差异，不改动文字本身；不用于写库正文。"""
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", "", s)


def check_continuity(arts):
    nums = [cn2int(re.match(r"^第(.+?)条$", n).group(1)) for n, _ in arts]
    bad = [i + 1 for i, v in enumerate(nums) if v != i + 1]
    return (not bad), nums[:3], bad[:6]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--law", required=True)
    ap.add_argument("--url-a", required=True)
    ap.add_argument("--url-b", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect", type=int, default=0)
    ap.add_argument("--level", default="法律")
    ap.add_argument("--status", default="现行有效")
    ap.add_argument("--effective-date", default="")
    ap.add_argument("--expiry-date", default="")
    ap.add_argument("--doc-no", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    print("[..] 抓取源 A:", a.url_a, flush=True)
    ha = fetch(a.url_a)
    print("[..] 抓取源 B:", a.url_b, flush=True)
    hb = fetch(a.url_b)
    A, B = parse_articles(ha), parse_articles(hb)
    print("[ok] A 源解析 %d 条 | B 源解析 %d 条" % (len(A), len(B)), flush=True)

    fail = []
    if a.expect and (len(A) != a.expect or len(B) != a.expect):
        fail.append("条数与预期不符 expect=%d A=%d B=%d" % (a.expect, len(A), len(B)))
    if len(A) != len(B):
        fail.append("两源条数不一致 A=%d B=%d" % (len(A), len(B)))
    for tag, arts in (("A", A), ("B", B)):
        ok, head, bad = check_continuity(arts)
        print("  %s 源条号连续性: %s 起始%s 断号%s" % (tag, "OK" if ok else "FAIL", head, bad), flush=True)
        if not ok:
            fail.append("%s 源条号不连续，断号位置%s" % (tag, bad))

    diffs = []
    for (na, ta), (nb, tb) in zip(A, B):
        if na != nb:
            diffs.append((na, nb, "条号错位"))
            continue
        x, y = norm(ta), norm(tb)
        if x != y:
            ratio = difflib.SequenceMatcher(None, x, y).ratio()
            diffs.append((na, "", "相似度 %.4f" % ratio))
    if diffs:
        print("\n[差异] %d 条两源不一致：" % len(diffs), flush=True)
        for d in diffs[:12]:
            print("  -", d, flush=True)
        fail.append("存在 %d 条两源差异" % len(diffs))
    else:
        print("[ok] 双源逐条一致（%d 条）" % len(A), flush=True)

    if fail:
        print("\n[拒绝入库]", flush=True)
        for f in fail:
            print("  -", f, flush=True)
        return 2

    # 写出 corpus md（正文取 A 源，保留原始标点，仅去段首条号与缩进）
    today = time.strftime("%Y-%m-%d")
    lines = [
        "# %s · 逐字条文（L0 原文层）" % a.law,
        "",
        "> 本文件属 L0 逐字原文层，**不进 `build_kb.py` 的 FILES，不参与主检索索引**；"
        "由 `import_corpus.py` 校验后供 `build_v5.py` 写入 `article_text`。",
        "> 效力层级：%s；生效状态：%s；施行日期：%s。" % (a.level, a.status, a.effective_date or "以官方原文为准"),
        "> 双源核验（%s）：%s ｜ %s，逐条比对一致。" % (today, a.url_a, a.url_b),
        "",
    ]
    for no, body in A:
        lines.append("## 《%s》%s" % (a.law, no))
        lines.append("")
        lines.append(body)
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"

    if a.dry_run:
        print("\n[dry-run] 将写入 %s（%d 条，%d 字符），未落盘" % (a.out, len(A), len(text)), flush=True)
        print(text[:600], flush=True)
        return 0

    os.makedirs(CORPUS, exist_ok=True)
    out_path = os.path.join(CORPUS, a.out)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("[ok] 写出 %s（%d 条 / %d 字符）" % (out_path, len(A), len(text)), flush=True)

    # 登记 manifest（同 doc_id 则更新）
    man = json.load(open(MANIFEST, "r", encoding="utf-8"))
    doc_id = os.path.splitext(a.out)[0]
    entry = {
        "doc_id": doc_id, "file": a.out, "name": a.law, "doc_no": a.doc_no,
        "level": a.level, "status": a.status,
        "effective_date": a.effective_date, "expiry_date": a.expiry_date,
        "sources": [a.url_a, a.url_b], "source_count": 2,
        "article_count": len(A), "verified_at": today, "sha256": "",
        "note": a.note or "由 fetch_corpus.py 抓取两官方源并逐条比对一致后写入；正文未改写。",
    }
    docs = man.setdefault("documents", [])
    for i, d in enumerate(docs):
        if d.get("doc_id") == doc_id:
            docs[i] = entry
            break
    else:
        docs.append(entry)
    man["generated_at"] = today
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    print("[ok] manifest 已登记 %s（共 %d 份文档）" % (doc_id, len(docs)), flush=True)
    print("[next] 运行 import_corpus.py 校验并写入 corpus-articles.json", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
