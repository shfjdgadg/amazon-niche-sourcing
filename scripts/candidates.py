#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 C：单个细分小类目 → 规格矩阵 → 20 个候选产品（含对标 ASIN / 链接 / 初步可行性）。

用法：
  python3 candidates.py --site DE --node "1:2:3" --name "Haken für Akustikpaneele" --n 20

输出：out/sub_<slug>.json
"""
import argparse
import collections
import json
import os
import math
import re
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mcp_client
import specs

OUT_DIR = "out"
CNY_RATE = 7.8          # EUR/CNY
VAT = 0.19
REFERRAL = 0.15


def _num(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def fetch_products(site, node, size=100):
    data = mcp_client.call("product_research", {"request": {
        "marketplace": site, "nodeIdPath": node, "size": size, "page": 1,
        "order": {"field": "total_units", "desc": True}}})
    return (data or {}).get("items") or []


def fetch_keywords(site, seed, size=100):
    try:
        data = mcp_client.call("keyword_miner", {"request": {
            "marketplace": site, "keyword": seed, "size": size, "page": 1}})
        return (data or {}).get("items") or []
    except Exception:
        return []


def build_matrix(products):
    rows = []
    for p in products:
        s = specs.extract(p.get("title"), _num(p.get("price")))
        rows.append({"asin": p.get("asin"), "title": p.get("title"), "brand": p.get("brand"),
                     "price": _num(p.get("price")), "units": int(_num(p.get("units"))),
                     "revenue": _num(p.get("revenue")), "ratings": p.get("ratings"),
                     "rating": p.get("rating"), "fba": p.get("fba"),
                     "imageUrl": p.get("imageUrl"), "bsr": p.get("bsr"),
                     "pkgDimensions": p.get("pkgDimensions"), "pkgWeight": p.get("pkgWeight"),
                     "weight": p.get("weight"), "dimension": p.get("dimension"),
                     "createdTime": p.get("createdTime") or p.get("availableDate"),
                     **{k: s[k] for k in ("pack", "colors", "shapes", "materials", "mounts", "dims")}})
    return rows


def _first(lst, default=None):
    return lst[0] if lst else default


def top_values(rows, key, n=4):
    """按销量聚合某个维度值。"""
    agg = collections.defaultdict(lambda: [0, 0])   # units, count
    for r in rows:
        v = r.get(key)
        if v is None:
            continue
        vals = v if isinstance(v, list) else [v]
        for x in vals:
            agg[x][0] += r["units"]
            agg[x][1] += 1
    out = sorted(agg.items(), key=lambda kv: -kv[1][0])
    return [{"value": k, "units": u, "count": c} for k, (u, c) in out[:n]]


COLOR_CN = {"schwarz": "黑", "weiß": "白", "gold": "金", "silber": "银", "beige": "米", "grau": "灰", "braun": "棕"}


def generate(rows, name, n=20):
    """规格矩阵 → 候选。

    候选分四类：
      1 规格组合（件数 × 颜色）—— 该件数有量、该颜色没铺开 = 真实缺口
      2 材质错位 —— 材质占比极低
      3 安装方式错位 —— 安装方式稀缺
      4 延伸款（加量/套装/升级/引流/包装）—— 补齐到 n 个，保证每个都有对标
    每类按「需求/供给」打分，分数越高越值得做。
    """
    packs = top_values(rows, "pack", 5)
    colors = top_values(rows, "colors", 6)
    materials = top_values(rows, "materials", 4)
    mounts = top_values(rows, "mounts", 3)
    band_demand = collections.defaultdict(int)
    for r in rows:
        band_demand[specs.price_band(r["price"])] += r["units"]
    best_band = max(band_demand.items(), key=lambda kv: kv[1])[0] if band_demand else "€16-19.99"
    base_price = {"€0-9.99": 8.99, "€10-12.99": 11.99, "€13-15.99": 14.99, "€16-19.99": 18.99,
                  "€20-24.99": 22.99, "€25-34.99": 29.99, "€35-49.99": 42.99, "€50+": 54.99}.get(best_band, 18.99)
    avg_pack = statistics_median([r["pack"] for r in rows if r.get("pack")])
    all_units = sum(r["units"] for r in rows) or 1

    def pack_price(pk):
        if not avg_pack or not pk:
            return base_price
        return round(max(5.99, min(89.99, base_price * (pk / float(avg_pack)) ** 0.55)), 2)

    def anchor(pred, k=3):
        c = [r for r in rows if pred(r)]
        c.sort(key=lambda r: -r["units"])
        return c[:k]

    cands, seen = [], set()

    def push(key, kind, pack, color, reason, supply, demand, anchors, score, price=None, label=None):
        if key in seen:
            return
        seen.add(key)
        cands.append({"key": key, "kind": kind, "label": label or kind, "pack": pack, "color": color,
                      "price": price if price is not None else pack_price(pack),
                      "reason": reason, "supply": supply, "demand": int(demand),
                      "anchors": [a["asin"] for a in anchors], "score": round(score, 1)})

    # ---- 1 规格组合（件数 × 颜色）----
    for pk in packs[:4]:
        same = [r for r in rows if r["pack"] == pk["value"]]
        demand = sum(r["units"] for r in same) or 1
        for col in colors[:6]:
            supply = sum(1 for r in same if col["value"] in r["colors"])
            ratio = supply / float(max(1, len(same)))
            score = 42 + (1 - ratio) * 45 + 13 * (demand / float(all_units))
            cn = COLOR_CN.get(col["value"], col["value"])
            why = ("%s件装是主力件数（占样本销量 %.0f%%），%s色仅 %d/%d 个在售，配色缺口"
                   % (pk["value"], 100.0 * demand / all_units, cn, supply, len(same)))
            a = anchor(lambda r, p=pk["value"], c=col["value"]: r["pack"] == p and c in r["colors"], 2) \
                or anchor(lambda r, p=pk["value"]: r["pack"] == p, 2)
            push("P%sC%s" % (pk["value"], col["value"]), "规格组合", pk["value"], col["value"], why,
                 supply, demand, a, score, label="%s件装/%s色" % (pk["value"], cn))

    # ---- 2 材质错位 ----
    for mt in materials[:3]:
        sub = [r for r in rows if mt["value"] in r["materials"]]
        share = len(sub) / float(len(rows))
        if share <= 0.12:
            pk = packs[0]["value"] if packs else None
            cn = {"metall": "金属", "aluminium": "铝", "edelstahl": "不锈钢", "holz": "木",
                  "kunststoff": "塑料", "messing": "黄铜"}.get(mt["value"], mt["value"])
            push("MAT%s" % mt["value"], "材质", pk, (colors[0]["value"] if colors else "schwarz"),
                 "%s材质仅占 %.0f%%，属材质错位机会（现有买家买不到该材质）" % (cn, share * 100),
                 len(sub), all_units, anchor(lambda r: True, 3), 68 + (1 - share) * 20)

    # ---- 3 安装方式错位 ----
    for mo in mounts[:2]:
        sub = [r for r in rows if mo["value"] in r["mounts"]]
        share = len(sub) / float(len(rows))
        if share <= 0.15:
            push("MNT%s" % mo["value"], "安装方式", (packs[0]["value"] if packs else None), "schwarz",
                 "%s安装仅占 %.0f%%，安装方式可做卖点差异" % (mo["value"], share * 100),
                 len(sub), all_units, anchor(lambda r: True, 3), 64 + (1 - share) * 18)

    # ---- 4 延伸款 ----
    fillers = [
        ("加量装（×2）", 2.0, "同规格×2 件装，摊薄单件成本，拉高客单"),
        ("套装（主品+配件）", 1.6, "主品搭配件组合，避开单品价格战"),
        ("加厚/升级款", 1.35, "材质/厚度升级，承接对质量不满的买家"),
        ("入门小包装", 0.55, "小包装低价引流，测款成本最低"),
        ("零售礼盒装", 1.15, "礼盒包装做礼赠场景，提升溢价"),
        ("多色套装", 1.2, "多种颜色打包，覆盖装修配色不确定性"),
    ]
    i = 0
    while len(cands) < n and i < 60:
        f = fillers[i % len(fillers)]
        pk0 = packs[0]["value"] if packs else None
        col = colors[i % len(colors)]["value"] if colors else "schwarz"
        i += 1
        key = "EXT%s%d" % (f[0], i)
        pk_new = pack_round(pk0, f[1]) if pk0 else None
        push(key, "延伸", pk_new, col,
             "%s；对标同规格在售品做差异化" % f[2], 0, all_units, anchor(lambda r: True, 3),
             45 + (i % 9),
             price=round(pack_price(pk0) * f[1], 2) if pk0 else None,
             label="%s（%s件装/%s色）" % (f[0], pk_new or "-", COLOR_CN.get(col, col)))

    cands.sort(key=lambda c: (-c["score"], c["anchors"][0] if c["anchors"] else ""))
    out = []
    for idx, c in enumerate(cands[:n], 1):
        price = c["price"] or base_price
        fba = round(min(6.5, 1.9 + 0.22 * math.sqrt(max(1.0, price))), 2)
        cost = round(price * 0.22 * CNY_RATE, 1)
        net = price / (1 + VAT)
        margin = (net - net * REFERRAL - fba - cost / CNY_RATE) / net if net else 0
        cn = COLOR_CN.get(c["color"], c["color"])
        if c["kind"] == "规格组合":
            tier = "优先" if (c["supply"] or 0) <= 2 else "备选"
        elif c["kind"] in ("材质", "安装方式"):
            tier = "观察"
        else:
            tier = "备选"
        out.append({
            "tier": tier,
            "no": "C-%02d" % idx,
            "name": "%s · %s" % (name.split(":")[-1], c["key"].split("-")[0] if False else c["key"]),
            "label": c["label"],
            "showName": "%s · %s" % (name.split(":")[-1], c["label"]),
            "kind": c["kind"], "pack": c["pack"], "color": c["color"],
            "params": "建议 %s 件装 / %s / 价位 %s" % (c["pack"] or "-", cn, specs.price_band(price)),
            "diff": c["reason"],
            "price": price, "fba": fba, "cost": cost, "margin": round(margin, 3),
            "anchors": c["anchors"], "demand": c["demand"], "supply": c["supply"], "score": c["score"],
        })

    matrix = {"packs": packs, "colors": colors, "materials": materials, "mounts": mounts,
              "bestBand": best_band, "bands": dict(band_demand), "avgPack": avg_pack}
    return out, matrix


def statistics_median(vals):
    vals = sorted(v for v in vals if v)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


def pack_round(pk, mult):
    if not pk:
        return None
    return max(1, int(round(pk * mult)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="DE")
    ap.add_argument("--node", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", default=None, help="关键词种子，默认用 --name")
    ap.add_argument("--out", default=None)
    ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()

    if a.fake:
        _cols = ["schwarz", "weiß", "gold", "silber"]
        _packs = [4, 6, 10, 20]
        _mats = ["Metall", "Aluminium", "Holz", "Kunststoff"]
        products = [{"asin": "B0TEST%04d" % i,
                     "title": "Test Haken für Akustikpaneele %d Stück %s %s" % (_packs[i % 4], _cols[i % 4], _mats[i % 4]),
                     "brand": "B%d" % (i % 5), "price": 9 + i % 12, "units": 100 * (i % 7 + 1),
                     "revenue": 1000, "ratings": 10 * i, "rating": 4.5, "fba": 3, "bsr": i,
                     "imageUrl": "", "createdTime": 0} for i in range(30)]
    else:
        products = fetch_products(a.site, a.node, 100)
        if not products:
            raise SystemExit("细分节点没取到商品：%s" % a.node)

    rows = build_matrix(products)
    cands, matrix = generate(rows, a.name, a.n)
    kws = []
    if not a.fake:
        kws = [{"keyword": k.get("keyword"), "searches": k.get("searches"), "products": k.get("products"),
                "purchaseRate": k.get("purchaseRate"), "bid": k.get("bid")}
               for k in fetch_keywords(a.site, a.seed or a.name.split(" ")[-1], 100)]
    slug = re.sub(r"[^A-Za-z0-9]+", "_", a.name)[:40].strip("_") or "sub"
    out = a.out or os.path.join(OUT_DIR, "sub_%s.json" % slug)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"site": a.site, "name": a.name, "node": a.node, "products": rows,
               "matrix": matrix, "keywords": kws, "candidates": cands},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("%s：商品 %d 条，生成候选 %d 个 → %s" % (a.name, len(rows), len(cands), out))
    for c in cands[:5]:
        print("  %s %-30s 价€%-6s 毛利%.0f%% 对标%s" % (c["no"], c.get("showName", "")[:30], c["price"], c["margin"] * 100, ",".join(c["anchors"])))


if __name__ == "__main__":
    main()
