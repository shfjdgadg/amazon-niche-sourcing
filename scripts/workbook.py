#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 D：把 category.json + sub_*.json 渲染成选品表（XLSX）。

用法：
  python3 workbook.py --out 选品表.xlsx --site DE --dates 20261111
  python3 workbook.py --out 选品表.xlsx --images     # 下载并嵌入对标品主图
"""
import argparse
import glob
import json
import os
import sys
import urllib.request

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

OUT_DIR = "out"
IMG_DIR = "out/img"
def parse_dims(txt):
    """'38.7 x 20.3 x 14.6 cm' -> ['38.7','20.3','14.6']"""
    import re as _re
    if not txt:
        return ["", "", ""]
    m = _re.search(r"(\d+(?:[.,]\d+)?)\s*[x×*]\s*(\d+(?:[.,]\d+)?)\s*[x×*]\s*(\d+(?:[.,]\d+)?)", str(txt))
    if not m:
        return ["", "", ""]
    return [x.replace(",", ".") for x in m.groups()]


def feasibility(c, sub):
    d, s_, m = c.get("demand") or 0, c.get("supply"), c.get("margin") or 0
    parts = []
    tier = c.get("tier") or "备选"
    if c.get("kind") == "规格组合":
        if (s_ or 0) <= 2:
            parts.append("同件数月销 %d 件，该配色仅 %s 个在售 → 规格缺口真实存在" % (d, s_))
        else:
            parts.append("同件数月销 %d 件，该配色已有 %s 个在售 → 缺口一般，需靠图/价竞争" % (d, s_))
        parts.append("建议价 €%.2f，估毛利 %.0f%%" % (c.get("price") or 0, m * 100))
        parts.append("风险：配色属浅层差异，需配一套主图/场景图才能被搜到")
        concl = tier
    elif c.get("kind") in ("材质", "安装方式"):
        parts.append("该%s在样本中占比极低，属错位竞争" % c.get("kind"))
        parts.append("建议价 €%.2f，估毛利 %.0f%%" % (c.get("price") or 0, m * 100))
        parts.append("风险：需求未被验证，需先看关键词搜索量")
        concl = "观察"
    else:
        parts.append("延伸款，客户群与现有 listing 重叠，靠组合/包装拉客单")
        parts.append("建议价 €%.2f，估毛利 %.0f%%" % (c.get("price") or 0, m * 100))
        parts.append("风险：无结构性差异，易被跟卖")
        concl = tier
    return "【%s】%s" % (concl, "；".join(parts))


HEAD = ["开发", "站点", "sku", "参考链接1", "参考链接2", "参考链接3", "类目排名/销量", "采购商",
        "采购商链接(1688)", "图片", "产品名称参数", "关键词", "售价(€)", "FBA费用(€)", "采购价(¥)",
        "毛利率", "备注", "长(cm)", "宽(cm)", "高(cm)", "机会分", "可行性分析", "细分小类目"]

HFILL = PatternFill("solid", fgColor="1F4E78")
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def down_image(asin, url):
    os.makedirs(IMG_DIR, exist_ok=True)
    p = os.path.join(IMG_DIR, "%s.jpg" % asin)
    if os.path.exists(p) and os.path.getsize(p) > 1000:
        return p
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        open(p, "wb").write(urllib.request.urlopen(req, timeout=15).read())
        return p
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--site", default="DE")
    ap.add_argument("--cn", default="", help="1688 采购关键词（中文），留空则不生成采购链接")
    ap.add_argument("--images", action="store_true")
    ap.add_argument("--date", default="")
    a = ap.parse_args()

    cat = json.load(open(os.path.join(OUT_DIR, "category.json"), encoding="utf-8"))
    subs = cat["subcategories"]

    wb = Workbook()
    ws0 = wb.active
    ws0.title = "细分总览"
    h0 = ["排名", "细分小类目", "节点", "商品数", "月销量", "月销额(€)", "均价(€)", "CR3", "评论中位数", "机会分", "四维得分"]
    ws0.append(h0)
    for c in ws0[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = HFILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    rank = 0
    for s in subs:
        rank += 1
        m = s.get("metrics") or {}
        ws0.append([rank, s.get("leaf") or s.get("name"), s.get("nodeIdPath"),
                    m.get("goodsCount"), m.get("units"), m.get("revenue"), m.get("avgPrice"),
                    round((m.get("cr3") or 0) * 100, 1), m.get("reviewMedian"),
                    s.get("score"), json.dumps(s.get("scoreDetail") or {}, ensure_ascii=False)])
    widths0 = {"A": 6, "B": 34, "C": 26, "D": 10, "E": 10, "F": 12, "G": 10, "H": 8, "I": 12, "J": 8, "K": 40}
    for k, v in widths0.items():
        ws0.column_dimensions[k].width = v
    ws0.freeze_panes = "A2"

    ws = wb.create_sheet("候选明细")
    ws.append(HEAD)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = HFILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "D2"

    r = 2
    for s in subs:
        slug = __import__("re").sub(r"[^A-Za-z0-9]+", "_", s.get("leaf") or s.get("name"))[:40].strip("_")
        f = os.path.join(OUT_DIR, "sub_%s.json" % slug)
        if not os.path.exists(f):
            continue
        d = json.load(open(f, encoding="utf-8"))
        prods = {p["asin"]: p for p in d.get("products") or []}
        for c in d.get("candidates") or []:
            anchors = [x for x in (c.get("anchors") or []) if x]
            links = ["https://www.amazon.%s/dp/%s" % (("de" if a.site == "DE" else a.site.lower()), x) for x in anchors]
            links += [""] * (3 - len(links))
            met = []
            for x in anchors[:2]:
                p = prods.get(x) or {}
                met.append("%s: 月销%s 评%s" % (x, p.get("units"), p.get("ratings")))
            sku = "%s-%s" % (a.site, c["no"])
            procurement = ("https://s.1688.com/selloffer/offer_search.htm?keywords=%s" % a.cn) if a.cn else ""
            dims = parse_dims((prods.get(anchors[0]) or {}).get("pkgDimensions")) if anchors else ["", "", ""]
            feas = feasibility(c, s.get("leaf"))
            tier = c.get("tier") or "备选"
            badge = {"优先": "🔴 优先", "备选": "🟡 备选", "观察": "🟢 观察"}.get(tier, "🟡 备选")
            ws.append([badge, a.site, sku,
                       links[0], links[1], links[2], " ｜ ".join(met), "（1688 待询）", procurement, "",
                       (c.get("showName") or c.get("name")) + "｜" + (c.get("params") or ""), "", c.get("price"), c.get("fba"), c.get("cost"),
                       c.get("margin"), c.get("diff"),
                       dims[0], dims[1], dims[2], round(c.get("score") or 0, 1),
                       feas, s.get("leaf")])
            for col in range(1, len(HEAD) + 1):
                ws.cell(r, col).border = BORDER
                ws.cell(r, col).alignment = Alignment(vertical="center",
                                                      wrap_text=col in (8, 11, 17, 22, 23))
            for col in (4, 5, 6, 9):
                cell = ws.cell(r, col)
                if cell.value:
                    cell.hyperlink = cell.value
                    cell.font = Font(color="0563C1", underline="single", size=9)
            ws.cell(r, 16).number_format = "0.0%"
            ws.row_dimensions[r].height = 46
            if a.images and anchors:
                p = down_image(anchors[0], (prods.get(anchors[0]) or {}).get("imageUrl"))
                if p:
                    try:
                        im = XLImage(p); im.width = 62; im.height = 62
                        ws.add_image(im, "J%d" % r)
                    except Exception:
                        pass
            r += 1

    for k, v in {"A": 10, "B": 6, "C": 16, "D": 34, "E": 34, "F": 34, "G": 24, "H": 12, "I": 26,
                 "J": 11, "K": 40, "L": 18, "M": 9, "N": 10, "O": 9, "P": 8, "Q": 34, "R": 7,
                 "S": 7, "T": 7, "U": 8, "V": 26, "W": 26}.items():
        ws.column_dimensions[k].width = v

    ws1b = wb.create_sheet("细分结论")
    ws1b.append(["排名", "细分小类目", "机会分", "四维得分", "候选数", "结论", "建议"])
    for c in ws1b[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = HFILL
    for i, s_ in enumerate(subs, 1):
        slug_ = __import__("re").sub(r"[^A-Za-z0-9]+", "_", s_.get("leaf") or s_.get("name"))[:40].strip("_")
        f = os.path.join(OUT_DIR, "sub_%s.json" % slug_)
        n = 0
        if os.path.exists(f):
            n = len(json.load(open(f, encoding="utf-8")).get("candidates") or [])
        sc = s_.get("score") or 0
        concl = "强推" if sc >= 17 else "可做" if sc >= 14 else "观察"
        adv = {"强推": "本月排期打样，优先组货", "可做": "列入候选池，小批量测款", "观察": "先看关键词需求再定"}[concl]
        ws1b.append([i, s_.get("leaf") or s_.get("name"), sc,
                     json.dumps(s_.get("scoreDetail") or {}, ensure_ascii=False), n, concl, adv])
    for k, v in {"A": 6, "B": 34, "C": 8, "D": 40, "E": 8, "F": 8, "G": 30}.items():
        ws1b.column_dimensions[k].width = v
    ws1b.freeze_panes = "A2"

    ws2 = wb.create_sheet("说明")
    notes = [["项目", "说明"],
             ["数据来源", "卖家精灵 MCP（Amazon %s 站）" % a.site],
             ["生成时间", a.date],
             ["机会分", "四维：需求(月销额) / 竞争空间(CR3) / 价格带 / 评论壁垒，各 0-5 分，满分 20"],
             ["毛利率", "(售价/1.19 - 售价/1.19*15% - FBA - 采购价/7.8) / (售价/1.19)"],
             ["采购价", "按售价 22% 估算，需以 1688 实际报价替换"],
             ["FBA", "估算值，需用亚马逊费用计算器复核"],
             ["1688", "采购链接为搜索链接，供应商需自行筛选"]]
    for x in notes:
        ws2.append(x)
    for c in ws2[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = HFILL
    ws2.column_dimensions["A"].width = 16
    ws2.column_dimensions["B"].width = 100

    wb.save(a.out)
    print("已生成 %s（候选 %d 行）" % (a.out, r - 2))


if __name__ == "__main__":
    main()
