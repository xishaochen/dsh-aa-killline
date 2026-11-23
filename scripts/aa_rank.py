#!/usr/bin/env python3
"""aa_rank - Artificial Analysis 数据 CLI（仅标准库，零依赖）。

查询 LLM 排行榜（Intelligence/Coding/Math Index、基准分、价格、速度）与媒体 arena 数据。
免费 key 限流（100-1000 次/天），所有请求默认走本地缓存，--refresh 强制刷新。

用法示例:
  aa_rank list --top 10                       # Intelligence Index 前 10
  aa_rank list --sort price_in --order asc    # 按输入价格升序
  aa_rank search deepseek                      # 搜索模型
  aa_rank compare deepseek-v4-flash gpt-5-6-sol-low kimi-k3
  aa_rank media text-to-video --top 5 --categories
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://artificialanalysis.ai/api/v2"
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(SKILL_DIR, ".cache")
KEY_FILE = os.path.join(SKILL_DIR, "config", "key.env")
TTL_HOURS = {"models": 6, "media": 24}

# 排序字段 -> model_row 扁平化后的键名
SORT_FIELDS = {
    "intelligence": "intelligence",
    "coding": "coding",
    "math": "math",
    "price_in": "price_in",
    "price_out": "price_out",
    "price_blended": "price_blended",
    "speed": "speed",
    "ttft": "ttft",
    "release": "release",
}

# 中国/中资模型厂商白名单（用于 --china 过滤）。按 model_creator.name 精确匹配。
# 备注：StepFun=阶跃星辰，InclusionAI=阶跃，Z AI=智谱，Kimi=月之暗面，OpenBMB=面壁，
# KwaiKAT=快手，ByteDance Seed=字节，LongCat=昆仑万维/长猫，China Mobile=中移九天
CHINA_CREATORS = {
    "Alibaba", "DeepSeek", "Kimi", "Z AI", "MiniMax", "Tencent", "Baidu",
    "ByteDance Seed", "Xiaomi", "KwaiKAT", "StepFun", "InclusionAI",
    "OpenBMB", "China Mobile", "LongCat", "Nanbeige",
}
DEFAULT_EVAL_COLS = [
    ("AAII", "artificial_analysis_intelligence_index"),
    ("Coding", "artificial_analysis_coding_index"),
    ("Math", "artificial_analysis_math_index"),
    ("MMLU-Pro", "mmlu_pro"),
    ("GPQA", "gpqa"),
    ("LiveCodeBench", "livecodebench"),
]
MEDIA_KINDS = {
    "text-to-image": "text-to-image",
    "image-editing": "image-editing",
    "text-to-speech": "text-to-speech",
    "text-to-video": "text-to-video",
    "image-to-video": "image-to-video",
}


def load_key():
    key = os.environ.get("AA_API_KEY", "").strip()
    if key:
        return key
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("AA_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("错误: 未找到 API key。请设置环境变量 AA_API_KEY，或在 config/key.env 中写入 AA_API_KEY=xxx")


def cache_path(name):
    return os.path.join(CACHE_DIR, name + ".json")


def read_cache(name):
    p = cache_path(name)
    if not os.path.exists(p):
        return None
    age = time.time() - os.path.getmtime(p)
    if age > TTL_HOURS.get(name, 6) * 3600:
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def write_cache(name, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path(name), "w") as f:
        json.dump(data, f, ensure_ascii=False)


def _curl_get(url, key):
    """curl 兜底：本机 python urllib 对部分上游会 TLS 握手/连接重置。"""
    import subprocess
    p = subprocess.run(
        ["curl", "-sS", "--max-time", "60", "-H", f"x-api-key: {key}", url],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        sys.exit(f"错误: 网络请求失败 - curl exit {p.returncode}: {p.stderr.strip()[:200]}")
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        sys.exit(f"错误: 响应非 JSON - {p.stdout[:200]}")


def api_get(path, refresh=False, extra_params=None):
    name = path.replace("/", "_")
    if not refresh:
        cached = read_cache(name)
        if cached is not None:
            return cached
    url = BASE + path
    if extra_params:
        q = "&".join(f"{k}={v}" for k, v in extra_params.items())
        url += ("&" if "?" in url else "?") + q
    req = urllib.request.Request(url, headers={"x-api-key": load_key()})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code == 401:
            sys.exit("错误: API key 无效 (401)。请检查 config/key.env 中的 AA_API_KEY")
        if e.code == 403:
            sys.exit(f"错误: 权限不足 (403)。{body}（该端点可能需要 Pro/Commercial 订阅）")
        if e.code == 429:
            retry = e.headers.get("Retry-After", "稍后")
            sys.exit(f"错误: 触发限流 (429)。请在 {retry} 秒后重试，或使用 --refresh 前先等待缓存过期")
        sys.exit(f"错误: HTTP {e.code} - {body}")
    except urllib.error.URLError:
        # 兜底：改用 curl 重试一次（本机 urllib 偶发连接重置 / TLS 握手失败）
        data = _curl_get(url, load_key())
    write_cache(name, data)
    return data


def get(path, refresh=False, extra_params=None):
    return api_get(path, refresh, extra_params)


def disp(v, digits=2, suffix=""):
    """None -> '—'，数值 -> 保留 digits 位小数。"""
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        return f"{v:.{digits}f}{suffix}"
    return str(v)


def width(s):
    return sum(2 if ord(c) > 127 else 1 for c in str(s))


def print_table(rows, headers):
    col_w = [max([width(h)] + [width(r[i]) for r in rows]) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(col_w[i]) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * w for w in col_w))
    for r in rows:
        print("  ".join(str(c).ljust(col_w[i]) for i, c in enumerate(r)))


def emit(rows, headers, fmt, out):
    if fmt == "json":
        text = json.dumps(rows, ensure_ascii=False, indent=2)
    elif fmt == "csv":
        if out:
            with open(out, "w", newline="") as f:
                cw = csv.writer(f)
                cw.writerow(headers)
                cw.writerows(rows)
            print(f"已写入 {out}")
            return
        w = csv.writer(sys.stdout)
        w.writerow(headers)
        w.writerows(rows)
        return
    else:
        lines = []
        col_w = [max([width(h)] + [width(r[i]) for r in rows]) for i, h in enumerate(headers)]
        lines.append("  ".join(h.ljust(col_w[i]) for i, h in enumerate(headers)))
        lines.append("  ".join("-" * w for w in col_w))
        for r in rows:
            lines.append("  ".join(str(c).ljust(col_w[i]) for i, c in enumerate(r)))
        text = "\n".join(lines)
    if out:
        with open(out, "w") as f:
            f.write(text + "\n")
        print(f"已写入 {out}")
    else:
        print(text)


def _flatten_performance(m):
    """新 V2 免费端点把中位速度/TTFT 收进 performance 子对象；拍平回顶层，
    让下游（散点图 / CLI）沿用旧字段名 median_output_tokens_per_second 等。"""
    perf = m.get("performance") or {}
    for dst, src in (
        ("median_output_tokens_per_second", "median_output_tokens_per_second"),
        ("median_time_to_first_token_seconds", "median_time_to_first_token_seconds"),
        ("median_end_to_end_response_time_seconds", "median_end_to_end_response_time_seconds"),
    ):
        if m.get(dst) is None and perf.get(src) is not None:
            m[dst] = perf[src]
    return m


def fetch_models(refresh=False):
    """拉取 LLM 全量数据。旧端点 /data/llms/models 已于 2026-11-04 退役（410 Gone），
    迁移到免费分页端点 /language/models/free；遍历 total_pages 合并后再拍平 performance。"""
    first = get("/language/models/free", refresh)
    items = list(first.get("data", []))
    meta = first.get("pagination") or {}
    total_pages = meta.get("total_pages", 1)
    # 第 1 页已取到，续抓剩余页
    for page in range(2, total_pages + 1):
        pg = get(f"/language/models/free?page={page}", refresh)
        items.extend(pg.get("data", []))
    models = [_flatten_performance(m) for m in items]
    ts = first.get("fetched_at") or datetime.now(timezone.utc).isoformat()
    return models, ts


def model_row(m):
    ev = m.get("evaluations") or {}
    pr = m.get("pricing") or {}
    creator = (m.get("model_creator") or {}).get("name", "—")
    return {
        "slug": m.get("slug", "—"),
        "name": m.get("name", "—"),
        "creator": creator,
        "release": m.get("release_date", "—"),
        "intelligence": ev.get("artificial_analysis_intelligence_index"),
        # 免费端点 /language/models/free 仅保留各 *_index，旧的单项基准与
        # coding/math 指数已不再下发；保留键名置 None，避免下游崩。
        "coding": ev.get("artificial_analysis_coding_index"),
        "math": ev.get("artificial_analysis_math_index"),
        "mmlu_pro": ev.get("mmlu_pro"),
        "gpqa": ev.get("gpqa"),
        "livecodebench": ev.get("livecodebench"),
        "price_in": pr.get("price_1m_input_tokens"),
        "price_out": pr.get("price_1m_output_tokens"),
        "price_blended": pr.get("price_1m_blended_3_to_1"),
        "speed": m.get("median_output_tokens_per_second"),
        "ttft": m.get("median_time_to_first_token_seconds"),
    }


def cmd_list(args):
    models, ts = fetch_models(args.refresh)
    rows = [model_row(m) for m in models]
    if args.creator:
        rows = [r for r in rows if args.creator.lower() in r["creator"].lower()]
    if args.china:
        rows = [r for r in rows if r["creator"] in CHINA_CREATORS]
    if args.search:
        kw = args.search.lower()
        rows = [r for r in rows if kw in r["name"].lower() or kw in r["slug"].lower() or kw in r["creator"].lower()]
    if args.min_aii is not None:
        rows = [r for r in rows if r["intelligence"] is not None and r["intelligence"] >= args.min_aii]
    sort_key = SORT_FIELDS.get(args.sort)
    if sort_key:
        # None（未评测）永远排最后，不受升降序影响：降序时 None 映射为 -inf，升序时映射为 +inf
        none_val = float("-inf") if args.order == "desc" else float("inf")
        def keyf(r):
            v = r.get(sort_key)
            return none_val if v is None else v
        rows.sort(key=keyf, reverse=(args.order == "desc"))
    if args.top:
        rows = rows[: args.top]
    headers = ["#", "Model", "Creator", "AAII", "Coding", "Math", "$In/1M", "$Out/1M", "t/s", "TTFT(s)"]
    out_rows = [
        [i + 1, r["name"], r["creator"], disp(r["intelligence"], 1), disp(r["coding"], 1),
         disp(r["math"], 1), disp(r["price_in"], 2), disp(r["price_out"], 2),
         disp(r["speed"], 0), disp(r["ttft"], 2)]
        for i, r in enumerate(rows)
    ]
    emit(out_rows, headers, args.format, args.output)
    if args.format == "table":
        print(f"\n共 {len(rows)} 个模型 | 数据时间: {ts[:19]} | 来源: artificialanalysis.ai")


def cmd_search(args):
    args.search = args.search or ""
    args.top = args.top or 20
    cmd_list(args)


def cmd_compare(args):
    models, ts = fetch_models(args.refresh)
    by_slug = {m.get("slug"): model_row(m) for m in models}
    by_name = {m.get("name"): model_row(m) for m in models}
    picked = []
    for q in args.slugs:
        r = by_slug.get(q) or by_name.get(q)
        if r is None:
            hits = [m for m in models if q.lower() in (m.get("slug") or "").lower() or q.lower() in (m.get("name") or "").lower()]
            if hits:
                r = model_row(hits[0])
        if r is None:
            sys.exit(f"未找到模型: {q}（可用 aa_rank search {q} 查看相似模型）")
        picked.append(r)
    fields = [
        ("模型", "name"), ("创建者", "creator"), ("发布时间", "release"),
        ("Intelligence Index", "intelligence"), ("Coding Index", "coding"), ("Math Index", "math"),
        ("MMLU-Pro", "mmlu_pro"), ("GPQA", "gpqa"), ("LiveCodeBench", "livecodebench"),
        ("输入价 $/1M", "price_in"), ("输出价 $/1M", "price_out"), ("混合价 $/1M", "price_blended"),
        ("输出速度 t/s", "speed"), ("TTFT s", "ttft"),
    ]
    rows = []
    for label, f in fields:
        rows.append([label] + [disp(r[f]) for r in picked])
    headers = ["指标"] + [r["name"] for r in picked]
    emit(rows, headers, args.format, args.output)


def cmd_media(args):
    kind = MEDIA_KINDS.get(args.kind)
    if kind is None:
        sys.exit(f"未知媒体类型: {args.kind}，可选: {', '.join(MEDIA_KINDS)}")
    params = {"include_categories": "true"} if args.categories else None
    # 旧端点 /data/media/* 已退役，迁移到 /media/{kind}/models/free
    data = get(f"/media/{kind}/models/free", args.refresh, params)
    items = data.get("data", [])
    if args.top:
        items = items[: args.top]
    headers = ["#", "Name", "Creator", "Elo", "Rank", "CI95", "Appearances", "Release"]
    rows = [
        [i + 1, it.get("name", "—"), (it.get("model_creator") or {}).get("name", "—"),
         disp(it.get("elo"), 0), it.get("rank", "—"), it.get("ci95", "—"),
         it.get("appearances", "—"), it.get("release_date", "—")]
        for i, it in enumerate(items)
    ]
    emit(rows, headers, args.format, args.output)
    if args.categories and args.format == "table":
        print("\n-- 分类 Elo 细分（前 3 个模型的分类）--")
        for it in items[:3]:
            print(f"\n{it.get('name')}:")
            for c in (it.get("categories") or [])[:8]:
                cat = " / ".join(v for v in [c.get("style_category"), c.get("subject_matter_category"), c.get("format_category")] if v)
                print(f"  {cat}: Elo {disp(c.get('elo'), 0)} (CI95 {c.get('ci95','—')}, n={c.get('appearances','—')})")


def main():
    p = argparse.ArgumentParser(prog="aa_rank", description="Artificial Analysis LLM/媒体数据查询")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="LLM 排行榜列表")
    pl.add_argument("--top", type=int)
    pl.add_argument("--sort", choices=list(SORT_FIELDS), default="intelligence")
    pl.add_argument("--order", choices=["desc", "asc"], default="desc")
    pl.add_argument("--creator")
    pl.add_argument("--china", action="store_true", help="仅保留中国/中资厂商（Alibaba/DeepSeek/Kimi/智谱/阶跃/字节/腾讯/百度/小米/快手等）")
    pl.add_argument("--search")
    pl.add_argument("--min-aii", type=float)
    pl.add_argument("--format", choices=["table", "json", "csv"], default="table")
    pl.add_argument("--output")
    pl.add_argument("--refresh", action="store_true", help="强制刷新缓存")
    pl.set_defaults(fn=cmd_list)

    ps = sub.add_parser("search", help="按名称/别名/创建者搜索")
    ps.add_argument("search")
    ps.add_argument("--top", type=int)
    ps.add_argument("--creator")
    ps.add_argument("--china", action="store_true", help="仅保留中国/中资厂商")
    ps.add_argument("--min-aii", type=float)
    ps.add_argument("--sort", choices=list(SORT_FIELDS), default="intelligence")
    ps.add_argument("--order", choices=["desc", "asc"], default="desc")
    ps.add_argument("--format", choices=["table", "json", "csv"], default="table")
    ps.add_argument("--output")
    ps.add_argument("--refresh", action="store_true")
    ps.set_defaults(fn=cmd_search)

    pc = sub.add_parser("compare", help="对比多个模型")
    pc.add_argument("slugs", nargs="+")
    pc.add_argument("--format", choices=["table", "json", "csv"], default="table")
    pc.add_argument("--output")
    pc.add_argument("--refresh", action="store_true")
    pc.set_defaults(fn=cmd_compare)

    pm = sub.add_parser("media", help="媒体模型 arena 排行")
    pm.add_argument("kind", choices=list(MEDIA_KINDS))
    pm.add_argument("--top", type=int)
    pm.add_argument("--categories", action="store_true")
    pm.add_argument("--format", choices=["table", "json", "csv"], default="table")
    pm.add_argument("--output")
    pm.add_argument("--refresh", action="store_true")
    pm.set_defaults(fn=cmd_media)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
