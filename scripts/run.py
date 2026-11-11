#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键流水线：大类目 + 站点 → 细分小类目 → 每细分 20 个候选 → 选品表。

用法：
  python3 run.py --site DE --category "Insektenschutz" --subs 5 --per-sub 20 --out 选品表.xlsx
  python3 run.py --site DE --node "64187031:2860338031:2860457031" --subs 3
  python3 run.py --fake                       # 离线自测

产物：out/category.json、out/sub_*.json、<out>.xlsx
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def slug(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", name or "").strip("_")[:40] or "sub"


def run(cmd):
    print("$ " + " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("命令失败: %s" % " ".join(cmd))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="DE")
    ap.add_argument("--category")
    ap.add_argument("--node")
    ap.add_argument("--subs", type=int, default=5)
    ap.add_argument("--per-sub", type=int, default=20)
    ap.add_argument("--out", default="选品表.xlsx")
    ap.add_argument("--cn", default="", help="1688 采购关键词")
    ap.add_argument("--images", action="store_true")
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--date", default="")
    a = ap.parse_args()

    py = sys.executable
    scan = [py, os.path.join(HERE, "scan.py"), "--site", a.site, "--top", str(a.subs)]
    if a.fake:
        scan.append("--fake")
    else:
        if a.category:
            scan += ["--category", a.category]
        if a.node:
            scan += ["--node", a.node]
    run(scan)

    import json
    cat = json.load(open(os.path.join("out", "category.json"), encoding="utf-8"))
    for s in cat["subcategories"]:
        leaf = s.get("leaf") or s.get("name")
        cmd = [py, os.path.join(HERE, "candidates.py"), "--site", a.site,
               "--node", s["nodeIdPath"], "--name", leaf, "--n", str(a.per_sub),
               "--out", os.path.join("out", "sub_%s.json" % slug(leaf))]
        if a.fake:
            cmd.append("--fake")
        run(cmd)

    wbcmd = [py, os.path.join(HERE, "workbook.py"), "--out", a.out, "--site", a.site,
             "--date", a.date or "", "--cn", a.cn]
    if a.images:
        wbcmd.append("--images")
    run(wbcmd)


if __name__ == "__main__":
    main()
