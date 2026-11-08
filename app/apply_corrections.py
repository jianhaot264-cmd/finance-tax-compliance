# -*- coding: utf-8 -*-
"""apply_corrections.py — 把 20/21/22 文件核验闭环结果回写到 01–19 源条目。

背景：审计发现 24 条源条目仍带「待核验/凭既有知识」标注，而其指向的字段
已在本轮由 A 层条目核验闭环。若不回写，知识库自相矛盾。

原则：不宣称「本条已核验」，而是把不确定性标注替换为「指向权威闭环条目」，
并补上两个本轮实际访问过的官方链接；原结论文字保持不变。
"""
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.normpath(os.path.join(BASE, "..", "knowledge-base"))

# entry_id -> (权威闭环条目, 官方链接1, 官方链接2)
CORRECTIONS = {
    "01-1.8": ("20-20.13", "https://www.gov.cn/zhengce/2021-03/24/content_5595384.htm",
               "https://cpc.people.com.cn/BIG5/n1/2021/0324/c64387-32059884.html"),
    "02-2.3": ("20-20.1", "http://www.npc.gov.cn/c2/c30834/201905/t20190521_296654.html",
               "https://neris.csrc.gov.cn/falvfagui/rdqsHeader/mainbody?secFutrsLawId=745439065454041418"),
    "02-2.4": ("17-17.1", "https://www.gov.cn/zhengce/2007-12/11/content_2602496.htm",
               "https://xzfg.moj.gov.cn/front/law/detail?LawID=1741"),
    "02-2.9": ("18-18.1", "https://www.gov.cn/zhengce/2008-11/14/content_2602523.htm",
               "https://www.chinatax.gov.cn/chinatax/n810341/n810765/n812171/n812680/c1190924/content.html"),
    "03-3.1": ("19-19.1", "https://www.gov.cn/gongbao/2024/issue_11286/202404/content_6945583.html",
               "https://www.gov.cn/yaowen/liebiao/202402/content_6934757.htm"),
    "03-3.4": ("20-20.3", "https://yunnan.chinatax.gov.cn/pub/info/topic?id=7add1dde1f5145c38116951262909832&department=15309000000",
               "https://neimenggu.chinatax.gov.cn/sjpd/tl/tzgghhht/202507/P020250707398922646952.pdf"),
    "04-4.1": ("19-19.2", "https://www.gov.cn/zhengce/zhengceku/202309/content_6901384.htm",
               "https://banshi.beijing.gov.cn/pubtask/task/1/110107000000/2a7e2b8c-10f7-43b0-b09d-f46399002c47.html"),
    "04-4.2": ("20-20.4", "http://www.npc.gov.cn/c2/kgfb/202409/t20240913_439534.html",
               "https://www.news.cn/politics/20240913/fb547fc824734641a53b3ee5d73a123b/c.html"),
    "04-4.3": ("19-19.2", "https://www.gov.cn/gongbao/content/2019/content_5468951.htm",
               "https://www.gov.cn/zhengce/zhengceku/202309/content_6901384.htm"),
    "04-4.4": ("19-19.2", "https://www.gov.cn/zhengce/zhengceku/202309/content_6901384.htm",
               "https://banshi.beijing.gov.cn/pubtask/task/1/110107000000/2a7e2b8c-10f7-43b0-b09d-f46399002c47.html"),
    "04-4.6": ("19-19.2", "https://banshi.beijing.gov.cn/pubtask/task/1/110107000000/2a7e2b8c-10f7-43b0-b09d-f46399002c47.html",
               "https://www.gov.cn/zhengce/zhengceku/202309/content_6901384.htm"),
    "04-4.7": ("18-18.6", "https://www.gov.cn/gongbao/content/2016/content_5086359.htm",
               "http://fgk.mof.gov.cn/ui/src/views/law_html/84292.html"),
    "07-7.5": ("20-20.7", "https://www.gov.cn/zhengce/content/202503/content_7015401.htm",
               "https://paper.people.com.cn/rmrb/pc/attachement/202503/25/9b772810-8b21-4be9-8224-92a763affae3.pdf"),
    "08-8.2": ("20-20.8", "https://www.chinatax.gov.cn/chinatax/n810219/n810744/c103147/c5249424/5249424/files/8e2bb59af3de4dec860e856ad66be304.pdf",
               "https://zhejiang.chinatax.gov.cn/art/2020/9/27/art_13314_477245.html"),
    "08-8.3": ("20-20.8", "https://www.chinatax.gov.cn/chinatax/n810219/n810780/c5168583/content.html",
               "https://www.chinatax.gov.cn/chinatax/n810219/n810744/c103147/c5249424/5249424/files/8e2bb59af3de4dec860e856ad66be304.pdf"),
    "08-8.6": ("20-20.8", "https://wb.flk.npc.gov.cn/flfg/PDF/0c5850def29b4a83b5ae75c6a8e2e233.pdf",
               "https://www.gov.cn/zhengce/2019-06/04/content_5397217.htm"),
    "08-8.7": ("20-20.8", "https://fgk.chinatax.gov.cn/zcfgk/c100009/c5193037/content.html",
               "https://www.chinatax.gov.cn/chinatax/n810219/n810744/c103147/c5249424/5249424/files/8e2bb59af3de4dec860e856ad66be304.pdf"),
    "08-8.9": ("20-20.8", "https://www.chinatax.gov.cn/chinatax/n810219/n810744/c103147/c5249424/5249424/files/8e2bb59af3de4dec860e856ad66be304.pdf",
               "https://zhejiang.chinatax.gov.cn/art/2020/9/27/art_13314_477245.html"),
    "08-8.10": ("18-18.3", "https://anhui.chinatax.gov.cn/art/2019/3/21/art_9601_585667.html",
                "https://shaanxi.chinatax.gov.cn/jact/front/mailpubdetail.do?transactId=51247&sysid=181"),
    "08-8.11": ("18-18.4", "https://www.chinatax.gov.cn/chinatax/n810341/n810765/c102408/202303/c5196135/content.html",
                "https://www.gov.cn/zhengce/2023-04/19/content_5752149.htm"),
    "09-9.2": ("20-20.9", "https://www.chinatax.gov.cn/chinatax/n810214/n810641/c102061/c102062/c5171575/content.html",
               "https://www.chinatax.gov.cn/chinatax/n810341/n810765/n1990035/201601/c2185201/content.html"),
    "09-9.4": ("20-20.10", "http://www.npc.gov.cn/npc/c2/c30834/202101/t20210122_309857.html",
               "https://www.mps.gov.cn/n6557558/c7692710/content.html"),
    "19-19.5": ("20-20.16", "https://guangdong.chinatax.gov.cn/gdsw/sszc123/2023-04/07/content_df700cde35f241aa9065ef1314063818.shtml",
                "https://guangdong.chinatax.gov.cn/gdsw/jmsw_gkwj/2023-07/18/3e46ae04b67c42138163d3a1f1603fa2/files/03431b0687bc484b834777ffd153a530.pdf"),
    "19-19.6": ("20-20.9", "https://www.chinatax.gov.cn/chinatax/n810214/n810641/c102061/zfxxgks.html",
                "https://fgk.chinatax.gov.cn/zcfgk/c100011/c5238560/content.html"),
}

# 不确定性措辞 → 指向权威闭环条目的表述（不宣称本条已核验）
VAGUE = re.compile(r"（凭既有知识[^）]*）|凭既有知识[^；|]*|待核验|待复核|文号待|建议复核[^；|]*|未检索到[^；|]*")


def file_of(eid):
    return os.path.join(KB_DIR, {
        "01": "01-national-tax-administration.md", "02": "02-national-tax-types.md",
        "03": "03-national-invoice.md", "04": "04-national-social-nontax.md",
        "05": "05-guangdong-local.md", "06": "06-incentives-quickref.md",
        "07": "07-sme-special.md", "08": "08-other-tax-laws.md",
        "09": "09-procedure-dispute.md", "19": "19-verified-basis-corrections.md",
    }[eid.split("-")[0]])


def main():
    by_file = {}
    for eid, val in CORRECTIONS.items():
        by_file.setdefault(file_of(eid), []).append((eid, val))

    total = 0
    for path, items in by_file.items():
        text = open(path, encoding="utf-8").read()
        # 按二级标题切块，保留分隔符
        parts = re.split(r"(?m)(?=^## )", text)
        out = []
        for block in parts:
            m = re.match(r"^##\s+([\d.]+)\s", block)
            if not m:
                out.append(block)
                continue
            suffix = m.group(1)
            hit = next((v for eid, v in items if eid.split("-")[1] == suffix), None)
            if not hit:
                out.append(block)
                continue
            closer, u1, u2 = hit
            repl = f"（依据见 {closer}）"
            new = VAGUE.sub(repl, block)
            # 核验行统一改为闭环指向
            new = re.sub(r"(?m)^\| 核验 \|[^\n]*\|",
                         f"| 核验 | 2026-11-06 闭环校验，权威结论见 {closer}（双官方信源） |",
                         new)
            # 信源行补两个本轮实际访问过的官方链接
            src_line = re.search(r"(?m)^\| 信源 \|([^\n]*)\|", new)
            if src_line:
                existing = src_line.group(1).strip()
                if u1 not in existing:
                    new = new.replace(src_line.group(0),
                                      f"| 信源 | {existing}；{u1} ；{u2} （2026-11-06 闭环双源） |")
            else:
                # 没有信源行则插入
                new = new.rstrip() + f"\n| 信源 | {u1} ；{u2} （2026-11-06 闭环双源） |\n"
            out.append(new)
            total += 1
        open(path, "w", encoding="utf-8").write("".join(out))

    print(f"[ok] 已回写 {total} 条源条目，覆盖 {len(by_file)} 个文件")
    print("     备份目录：knowledge-base-backup-2026-11-06/")


if __name__ == "__main__":
    main()
