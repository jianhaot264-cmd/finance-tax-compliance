# -*- coding: utf-8 -*-
"""build_report_html.py — 极简 Markdown → HTML（支持标题/表格/列表/引用/加粗/代码）。
仅用于本项目报告排版，不追求完整 Markdown 兼容。
"""
import html
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "sme-tax-compliance-incentives-2026-11-05.md")
OUT = sys.argv[2] if len(sys.argv) > 2 else SRC.rsplit(".", 1)[0] + ".html"


def inline(text):
    s = html.escape(text)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_sep(line):
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c)


def convert(md):
    lines = md.split("\n")
    out = []
    i = 0
    n = len(lines)
    in_ul = in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while i < n:
        line = lines[i]
        s = line.strip()

        if not s:
            close_lists()
            i += 1
            continue

        # 表格
        if s.startswith("|") and i + 1 < n and is_sep(lines[i + 1]):
            close_lists()
            header = split_row(s)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                if not is_sep(lines[i]):
                    rows.append(split_row(lines[i]))
                i += 1
            out.append('<div class="table-wrap"><table><thead><tr>' +
                       "".join(f"<th>{inline(c)}</th>" for c in header) +
                       "</tr></thead><tbody>")
            for r in rows:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table></div>")
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            close_lists()
            level = min(len(m.group(1)), 4)
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # 引用
        if s.startswith(">"):
            close_lists()
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + "<br>".join(inline(x) for x in buf if x) + "</blockquote>")
            continue

        # 无序列表
        if re.match(r"^[-*]\s+", s):
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            out.append("<li>" + inline(re.sub(r"^[-*]\s+", "", s)) + "</li>")
            i += 1
            continue

        # 有序列表
        if re.match(r"^\d+\.\s+", s):
            if not in_ol:
                close_lists()
                out.append("<ol>")
                in_ol = True
            out.append("<li>" + inline(re.sub(r"^\d+\.\s+", "", s)) + "</li>")
            i += 1
            continue

        # 分隔线
        if re.fullmatch(r"-{3,}", s):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        close_lists()
        buf = [s]
        i += 1
        while i < n:
            t = lines[i].strip()
            if (not t or t.startswith("#") or t.startswith("|") or t.startswith(">")
                    or re.match(r"^[-*]\s+", t) or re.match(r"^\d+\.\s+", t) or re.fullmatch(r"-{3,}", t)):
                break
            buf.append(t)
            i += 1
        out.append("<p>" + "<br>".join(inline(x) for x in buf) + "</p>")

    close_lists()
    return "\n".join(out)


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --ink:#102a43; --text:#1f3a56; --muted:#5b7288; --line:#dbe5f0; --bg:#f5f8fc; --surface:#fff; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font-family:"Microsoft YaHei","PingFang SC","Noto Sans SC",system-ui,-apple-system,sans-serif; line-height:1.75; font-size:15px; }}
.page {{ max-width:1120px; margin:0 auto; padding:44px 30px 70px; }}
h1 {{ color:var(--ink); font-size:30px; line-height:1.35; margin:0 0 14px; letter-spacing:.5px; padding-bottom:14px; border-bottom:3px solid var(--ink); }}
h2 {{ color:var(--ink); font-size:21px; margin:38px 0 14px; padding-left:12px; border-left:5px solid var(--ink); }}
h3 {{ color:var(--ink); font-size:17px; margin:24px 0 10px; }}
p {{ margin:10px 0; }}
strong {{ color:var(--ink); }}
blockquote {{ margin:14px 0 22px; padding:12px 16px; background:#eaf1f9; border-left:4px solid #2f6fa8; color:#2c4a66; border-radius:0 8px 8px 0; font-size:13.6px; }}
blockquote br {{ line-height:1.9; }}
.table-wrap {{ overflow-x:auto; margin:12px 0 22px; border:1px solid var(--line); border-radius:10px; background:var(--surface); }}
table {{ width:100%; border-collapse:collapse; font-size:13px; min-width:640px; }}
th {{ background:var(--ink); color:#fff; text-align:left; padding:10px 12px; font-weight:600; white-space:nowrap; }}
td {{ padding:9px 12px; border-top:1px solid var(--line); vertical-align:top; }}
tbody tr:nth-child(even) {{ background:#f7fafd; }}
tbody tr:hover {{ background:#eef5fc; }}
ul, ol {{ margin:10px 0 16px; padding-left:24px; }}
li {{ margin:6px 0; }}
code {{ background:#eef3f9; color:#0f4c81; padding:1px 5px; border-radius:4px; font-family:Consolas,monospace; font-size:12.6px; }}
hr {{ border:none; border-top:1px solid var(--line); margin:30px 0; }}
@media (max-width:700px) {{ .page {{ padding:26px 16px 50px; }} h1 {{ font-size:23px; }} h2 {{ font-size:19px; }} table {{ font-size:12px; min-width:560px; }} }}
@media print {{ body {{ background:#fff; }} .page {{ max-width:none; padding:0; }} .table-wrap {{ overflow:visible; }} th {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }} }}
</style>
</head>
<body><div class="page">
{body}
</div></body></html>
"""


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        md = f.read()
    body = convert(md)
    title = html.escape(md.split("\n", 1)[0].lstrip("# ").strip() or "财税合规报告")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(TEMPLATE.format(body=body, title=title))
    print("[ok]", OUT, len(body), "chars")


if __name__ == "__main__":
    sys.exit(main())
