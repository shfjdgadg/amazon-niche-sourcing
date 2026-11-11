#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从商品标题里抽取规格维度：件数 / 颜色 / 形状 / 材质 / 安装方式 / 尺寸。

只依赖正则，不调 API，方便离线测试。
"""
import re

PACK = re.compile(r"(\d{1,3})\s*(?:x\s*)?(?:stück|stk\.?|st\.?|er[- ]?set|pack|pcs|piece|teilig)", re.I)
PACK2 = re.compile(r"(?:set\s*(?:von|aus)?\s*)(\d{1,3})", re.I)
SIZE_CM = re.compile(r"(\d{1,3}(?:[.,]\d)?)\s*[x×*]\s*(\d{1,3}(?:[.,]\d)?)\s*(?:[x×*]\s*(\d{1,3}(?:[.,]\d)?))?\s*(cm|mm)", re.I)

COLORS = {
    "schwarz": ["schwarz", "black", "schwarz matt"], "weiß": ["weiß", "weiss", "white"],
    "gold": ["gold", "messing", "brass"], "silber": ["silber", "silver", "edelstahl"],
    "beige": ["beige", "creme", "cream", "sand"], "grau": ["grau", "grey", "gray"],
    "braun": ["braun", "brown", "eiche", "nussbaum", "walnuss"],
}
SHAPES = {"rund": ["rund", "round", "kreis"], "eckig": ["eckig", "quadrat", "square", "rechteck"],
          "oval": ["oval", "langloch"]}
MATERIALS = {"metall": ["metall", "metal", "stahl", "steel"], "aluminium": ["aluminium", "alu"],
             "edelstahl": ["edelstahl", "rostfrei", "stainless"], "holz": ["holz", "wood", "eiche"],
             "kunststoff": ["kunststoff", "plastik", "plastic", "3d"], "messing": ["messing", "brass"]}
MOUNTS = {"ohne bohren": ["ohne bohren", "bohrfrei", "no drill", "ohne schrauben"],
          "kleben": ["kleb", "adhesive", "selbstklebend"],
          "schrauben": ["schraub", "screw"], "klemmen": ["klemm", "clip", "klemme"]}


def _find(title, table):
    t = title.lower()
    out = []
    for name, keys in table.items():
        if any(k in t for k in keys):
            out.append(name)
    return out


def extract(title, price=None):
    t = (title or "").lower()
    pack = None
    m = PACK.search(t) or PACK2.search(t)
    if m:
        try:
            pack = int(m.group(1))
        except Exception:
            pack = None
    dims = None
    ms = SIZE_CM.search(t)
    if ms:
        unit = (ms.group(4) or "cm").lower()
        f = 0.1 if unit == "mm" else 1.0
        parts = [ms.group(1), ms.group(2), ms.group(3)]
        dims = [round(float(p.replace(",", ".")) * f, 1) for p in parts if p]
    return {
        "pack": pack,
        "colors": _find(t, COLORS),
        "shapes": _find(t, SHAPES),
        "materials": _find(t, MATERIALS),
        "mounts": _find(t, MOUNTS),
        "dims": dims,
        "price": price,
    }


def price_band(p):
    if not p:
        return "?"
    for lo, hi in [(0, 9.99), (10, 12.99), (13, 15.99), (16, 19.99), (20, 24.99), (25, 34.99), (35, 49.99)]:
        if lo <= p <= hi:
            return "€%g-%g" % (lo, hi)
    return "€50+"
