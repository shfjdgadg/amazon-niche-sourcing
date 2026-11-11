#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卖家精灵 MCP 客户端（JSON-RPC over HTTP）。

key 解析顺序：
  1) 环境变量 SELLERSPRITE_KEY
  2) 工作区 ./.mcp.json 里 sellersprite 的 secret-key
  3) 参数传入

带磁盘缓存（cache/ 目录），配额用尽时自动回退到缓存，避免重复烧额度。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = "https://mcp.sellersprite.com/mcp"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cache")

QUOTA_HINTS = ("ERROR_VISIT_MAX", "接口访问次数已达上限", "secret_no_remaining")


def _key():
    k = os.environ.get("SELLERSPRITE_KEY")
    if k:
        return k.strip()
    for path in (".mcp.json", os.path.join(os.getcwd(), ".mcp.json")):
        if os.path.exists(path):
            try:
                cfg = json.load(open(path, encoding="utf-8"))
                for name, srv in (cfg.get("mcpServers") or {}).items():
                    if "sellersprite" in name.lower():
                        h = srv.get("headers") or {}
                        v = h.get("secret-key") or h.get("secret_key")
                        if v:
                            return v.strip()
            except Exception:
                pass
    raise SystemExit("缺少卖家精灵 key：请设置环境变量 SELLERSPRITE_KEY，或在 ./.mcp.json 里配置 sellersprite 的 secret-key")


def _cache_path(tool, args):
    key = json.dumps([tool, args], ensure_ascii=False, sort_keys=True)
    import hashlib
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, "%s_%s.json" % (tool, h))


def call(tool, arguments, timeout=180, use_cache=True, allow_stale=True):
    """调用一个 MCP 工具，返回已解析的 data 部分（dict/list）。

    失败时：若 allow_stale，回退到最近一次缓存，并在结果里加 __stale__ 标记。
    """
    cp = _cache_path(tool, arguments)
    if use_cache and os.path.exists(cp) and time.time() - os.path.getmtime(cp) < 3600:
        return json.load(open(cp, encoding="utf-8"))

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments}}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "secret-key": _key(),
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        return _fallback(cp, allow_stale, "网络错误: %s" % e)

    env = json.loads(raw)
    if "error" in env:
        return _fallback(cp, allow_stale, json.dumps(env["error"], ensure_ascii=False)[:200])
    text = "".join(c.get("text", "") for c in (env["result"].get("content") or [])
                   if c.get("type") == "text")
    try:
        out = json.loads(text)
    except Exception:
        out = {"_raw": text}
    code = (out or {}).get("code") if isinstance(out, dict) else None
    if code and code != "OK":
        msg = (out or {}).get("message", "")
        return _fallback(cp, allow_stale, "%s %s" % (code, msg))
    data = out.get("data") if isinstance(out, dict) else out
    json.dump(out, open(cp, "w", encoding="utf-8"), ensure_ascii=False)
    return data


def _fallback(cp, allow_stale, reason):
    if allow_stale and os.path.exists(cp):
        d = json.load(open(cp, encoding="utf-8"))
        if isinstance(d, dict):
            d["__stale__"] = reason
        return d
    raise RuntimeError("接口调用失败且无缓存可用: %s" % reason)


if __name__ == "__main__":
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(call(tool, args), ensure_ascii=False)[:4000])
