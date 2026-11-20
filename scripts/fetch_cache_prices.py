#!/usr/bin/env python3
"""抓取并匹配「真实缓存读价」（per-model cache read price）。

数据源：OpenRouter 公开 API `GET /api/v1/models`
  字段 pricing.input_cache_read（$ per token）—— 逐模型真实价，非估算。
  这是 AA 免费 API 不提供的字段（AA 免费端点只有 blended/input/output 三个价格字段）。

输出：.cache/_cache_prices.json
  { "<AA slug>": {"cr": 缓存读价$/1M, "c": cr/输入价, "orid": 来源 OR id}, ... }

用法：
  python3 scripts/fetch_cache_prices.py            # 读缓存（24h）
  python3 scripts/fetch_cache_prices.py --refresh  # 强制重新抓取
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
CACHE_DIR = os.path.join(SKILL, ".cache")
AA_CACHE = os.path.join(CACHE_DIR, "_data_llms_models.json")
OR_CACHE = os.path.join(CACHE_DIR, "_openrouter_models.json")
OUT = os.path.join(CACHE_DIR, "_cache_prices.json")
TTL = 24 * 3600


def norm(s):
    """归一化模型名：去括号档位、去非字母数字，用于跨源匹配。"""
    s = str(s).lower()
    s = re.sub(r"\([^)]*\)", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def norm_nodate(s):
    """再去掉尾部日期（-0902 / -2026-08-26）。"""
    s = str(s).lower()
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"[-_]?\d{2,4}(?:[-_]\d{2}){0,2}$", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def _curl_json(url):
    """curl 兜底：本机 python urllib 直连 openrouter.ai 会 TLS 握手/连接重置。"""
    p = subprocess.run(
        ["curl", "-sS", "--max-time", "40", "-A", "aa-llm-rank/1.0", url],
        capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("OpenRouter 抓取失败: curl exit %d: %s" % (p.returncode, p.stderr.strip()[:200]))
    return json.loads(p.stdout)


def fetch_openrouter(refresh=False):
    if not refresh and os.path.exists(OR_CACHE):
        if time.time() - os.path.getmtime(OR_CACHE) < TTL:
            print("• OpenRouter 缓存命中（<24h）")
            return json.load(open(OR_CACHE))["data"]
    print("• 抓取 OpenRouter /api/v1/models ...")
    raw = _curl_json("https://openrouter.ai/api/v1/models")
    json.dump(raw, open(OR_CACHE, "w"))
    print("  模型数 %d" % len(raw.get("data", [])))
    return raw["data"]


def build_index(orx):
    """建 OR 索引：多种归一形式 → 缓存价记录。"""
    idx = {}

    def put(k, rec):
        if k and k not in idx:
            idx[k] = rec

    n_cache = 0
    for m in orx:
        p = m.get("pricing") or {}
        cr = p.get("input_cache_read")
        pr = float(p.get("prompt") or 0)
        if cr is None or pr <= 0:
            continue
        cr = float(cr)
        if cr <= 0:
            continue
        mid = m["id"]
        vid, last = mid.split("/", 1) if "/" in mid else ("", mid)
        rec = {"cr": round(cr * 1e6, 6), "c": cr / pr,
               "orid": mid, "orname": m.get("name") or mid}
        put(norm(mid), rec)
        put(norm(last), rec)
        put(norm(vid) + norm(last), rec)
        put(norm_nodate(last), rec)
        put(norm(vid) + norm_nodate(last), rec)
        n_cache += 1
    print("• OR 含缓存读价模型：%d 个，索引键 %d 个" % (n_cache, len(idx)))
    return idx


def match_one(a, idx):
    mc = a.get("model_creator") or {}
    v = (mc.get("name") if isinstance(mc, dict) else mc) or ""
    n = norm(a["name"])
    nd = norm_nodate(a["name"])
    for k in (n, norm(v) + n, nd, norm(v) + nd):
        if k in idx:
            return idx[k]
    # 前缀容错（处理 -0902 / preview 等尾部差异）
    cands = [c for c in (n, norm(v) + n, nd, norm(v) + nd) if len(c) >= 6]
    best = None
    for c in cands:
        for k, rec in idx.items():
            if k.startswith(c) or c.startswith(k):
                d = abs(len(k) - len(c))
                if best is None or d < best[0]:
                    best = (d, rec)
        if best:
            return best[1]
    return None


def main():
    refresh = "--refresh" in sys.argv
    os.makedirs(CACHE_DIR, exist_ok=True)
    orx = fetch_openrouter(refresh)
    idx = build_index(orx)
    aa = json.load(open(AA_CACHE))["data"]

    out, miss = {}, []
    for a in aa:
        p = a.get("pricing") or {}
        i = p.get("price_1m_input_tokens")
        if not i:
            continue
        rec = match_one(a, idx)
        if rec:
            out[a["slug"]] = {"cr": rec["cr"], "c": round(rec["c"], 6),
                              "orid": rec["orid"]}
        else:
            miss.append(a["slug"])

    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=0)
    tot = len(out) + len(miss)
    print("• 匹配成功 %d / %d（%.0f%%）；未匹配 %d 个"
          % (len(out), tot, len(out) / tot * 100, len(miss)))
    print("• 已写入 %s" % OUT)

    import collections
    b = collections.Counter()
    for v in out.values():
        c = v["c"]
        k = ("0-5%" if c <= .05 else "5-12%" if c <= .12 else "12-26%" if c <= .26
             else "26-50%" if c <= .5 else "50-99%" if c < 1 else "100%")
        b[k] += 1
    print("• 真实 c 值分布：", dict(b))


if __name__ == "__main__":
    main()
