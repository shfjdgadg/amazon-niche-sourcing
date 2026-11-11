#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 A/B：大类目 → 下钻细分小类目 → 打分排序。

用法：
  python3 scan.py --site DE --category "Insektenschutz" --top 5
  python3 scan.py --site DE --node "64187031:2860338031:2860457031" --top 5
  python3 scan.py --fake            # 自测：不联网，用合成数据跑通流程

输出：out/category.json
"""
import argparse
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mcp_client
import specs

OUT_DIR = "out"


def _num(v, d=0):
    try:
        return float(v)
    except Exception:
        return d


def resolve(site, category=None, node=None):
    if node:
        return {"name": category or node, "nodeIdPath": node}
    data = mcp_client.call("product_node", {"request": {"marketplace": site, "keyword": category}})
    items = data.get("items") if isinstance(data, dict) else data
    items = items or []
    if not items:
        raise SystemExit("没找到类目: %s（换个关键词或直接传 --node）" % category)
    # 优先商品数最多的节点
    best = max(items, key=lambda x: _num(x.get("goodsCount") or x.get("products"), 0))
    path = best.get("nodeIdPath") or best.get("nodeId") or best.get("id")
    return {"name": best.get("nodeLabelPath") or category, "nodeIdPath": str(path),
            "goodsCount": best.get("goodsCount")}


def children(site, node_path):
    data = mcp_client.call("product_node", {"request": {"marketplace": site, "nodeIdPath": node_path}})
    items = data.get("items") if isinstance(data, dict) else data
    out = []
    for it in items or []:
        path = it.get("nodeIdPath") or it.get("nodeId") or it.get("id")
        if not path:
            continue
        p = str(path)
        # 只取直接子节点（比父多一层）
        if p.count(":") != str(node_path).count(":") + 1:
            continue
        out.append({"name": it.get("nodeLabelPath") or it.get("name") or p,
                    "leaf": (it.get("nodeLabelPath") or "").split(":")[-1],
                    "nodeIdPath": p,
                    "goodsCount": it.get("goodsCount")})
    return out


def metrics(site, node_path, limit=100):
    data = mcp_client.call("product_research", {"request": {
        "marketplace": site, "nodeIdPath": node_path, "size": limit, "page": 1,
        "order": {"field": "total_units", "desc": True}}})
    items = (data or {}).get("items") or []
    if not items:
        return None
    units = sum(_num(i.get("units")) for i in items)
    rev = sum(_num(i.get("revenue")) for i in items)
    prices = [p for p in (_num(i.get("price")) for i in items) if p > 0]
    brands = {}
    for i in items:
        brands[i.get("brand")] = brands.get(i.get("brand"), 0) + _num(i.get("units"))
    top3 = sum(sorted(brands.values(), reverse=True)[:3])
    cr3 = top3 / units if units else 0
    ratings = [r for r in (_num(i.get("ratings"), None) if i.get("ratings") is not None else None for i in items) if r is not None]
    new = [i for i in items if _num(i.get("createdTime") or i.get("availableDate")) > 0]
    return {
        "goodsCount": (data or {}).get("total"),
        "sample": len(items),
        "units": int(units), "revenue": int(rev),
        "avgPrice": round(sum(prices) / len(prices), 2) if prices else 0,
        "cr3": round(cr3, 3),
        "reviewMedian": st.median(ratings) if ratings else 0,
        "topUnits": int(sorted([_num(i.get("units")) for i in items], reverse=True)[0]) if items else 0,
    }


def score(m, demand_weight=1.0):
    """四维打分（0-20）：需求 / 竞争空间 / 价格带机会 / 进入难度。"""
    if not m:
        return 0, {}
    rev = m["revenue"]
    s_demand = 5 if rev > 150000 else 4 if rev > 80000 else 3 if rev > 40000 else 2 if rev > 15000 else 1
    s_comp = 5 if m["cr3"] < 0.30 else 4 if m["cr3"] < 0.40 else 3 if m["cr3"] < 0.50 else 2 if m["cr3"] < 0.65 else 1
    s_price = 5 if 10 <= m["avgPrice"] <= 25 else 4 if 25 < m["avgPrice"] <= 40 else 3 if m["avgPrice"] < 10 else 2
    s_entry = 5 if m["reviewMedian"] < 50 else 4 if m["reviewMedian"] < 150 else 3 if m["reviewMedian"] < 400 else 2 if m["reviewMedian"] < 1000 else 1
    total = s_demand + s_comp + s_price + s_entry
    return total, {"需求": s_demand, "竞争空间": s_comp, "价格带": s_price, "评论壁垒": s_entry}


def fake():
    """自测数据：模拟两个细分节点。"""
    return [
        {"name": "Test:Unterkategorie A", "leaf": "Unterkategorie A", "nodeIdPath": "1:2:3", "goodsCount": 300},
        {"name": "Test:Unterkategorie B", "leaf": "Unterkategorie B", "nodeIdPath": "1:2:4", "goodsCount": 120},
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="DE")
    ap.add_argument("--category")
    ap.add_argument("--node")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--max-subs", type=int, default=40, help="最多扫多少个子节点")
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "category.json"))
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)

    if a.fake:
        cat = {"name": "FAKE", "nodeIdPath": "1:2"}
        subs = fake()
    else:
        if not a.category and not a.node:
            raise SystemExit("需要 --category 或 --node")
        cat = resolve(a.site, a.category, a.node)
        subs = children(a.site, cat["nodeIdPath"])
        if not subs:
            raise SystemExit("该节点下没取到子节点。可换 --node 指定更上层节点，或检查 product_node 返回结构。")

    rows = []
    for s in subs[:a.max_subs]:
        if a.fake:
            m = {"goodsCount": 300, "sample": 100, "units": 2000, "revenue": 60000, "avgPrice": 16.5,
                 "cr3": 0.35, "reviewMedian": 40, "topUnits": 500}
        else:
            m = metrics(a.site, s["nodeIdPath"], a.limit)
        sc, detail = score(m)
        rows.append({**s, "metrics": m, "score": sc, "scoreDetail": detail})

    rows.sort(key=lambda r: -(r["score"] or 0))
    result = {"site": a.site, "category": cat, "subcategories": rows[:a.top],
              "allSubcategories": rows}
    json.dump(result, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("大类目: %s" % cat.get("name"))
    print("子节点: %d 个，取前 %d" % (len(rows), len(result["subcategories"])))
    for r in result["subcategories"]:
        m = r["metrics"] or {}
        print("  %-42s 分%2d  月销额€%-8s 均价€%-6s CR3 %.0f%% 评论中位%s"
              % (r["leaf"][:42], r["score"], m.get("revenue"), m.get("avgPrice"),
                 (m.get("cr3") or 0) * 100, m.get("reviewMedian")))
    print("已写: %s" % a.out)


if __name__ == "__main__":
    main()
