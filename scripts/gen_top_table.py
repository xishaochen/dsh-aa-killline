#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""厂商最强模型 × AIHub 上架对照表（与斩杀线图联动更新）

产物：
  data/aa_top_vs_aihub_<YYYYMMDD>.csv
  data/aa_top_vs_aihub_<YYYYMMDD>.html   （自包含，可直接打开）

用法：
  AA_SNAP=2026-10-21 python3 scripts/gen_top_table.py
  可选环境变量：AA_FXR、AA_RADAR_DIR、AIHUB_KEY、AA_OUT_DIR、AA_HUB_URL（对照表网关地址，默认网易 AIHub）

设计要点：
1. 「厂商最强」口径与斩杀线图完全一致：非退役、AA 实测、AAII 最高，同分取更便宜者。
2. AIHub 比对不做模糊猜测，逐级降级并标注证据等级：
      ✅   精确命中（含 -hc 等托管后缀，且 AA 名称里的版本号/日期能在 id 中对上）
      ✅*  别名命中：id 是通用别名，上游实际为更旧构建（如 deepseek-v4-flash → 7 月 GA）
      ❓   仅前缀近似，需人工确认
      ❌   未上架
3. 「支持思考等级」只用 AA 数据的客观证据：同一模型族（去掉括号档位后的名称）
   在 AA 中出现的档位集合，当前行所用档位加 ★。AA 未按档评测的标「未分档」，
   不做无据推断。
"""

import os
import re
import sys
import csv
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_scatter_0915 as gs  # noqa: E402

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 输出目录：默认包内 output/（随包分发时可被 AA_OUT_DIR 覆盖）
DATA = os.environ.get("AA_OUT_DIR") or os.path.join(SKILL, "output")

SNAP = os.environ.get("AA_SNAP") or gs.SNAP
TAG = SNAP.replace("-", "")
FXR = gs.FXR

HUB_URL = os.environ.get("AA_HUB_URL") or "https://ai.yunxinapi.com/hub/v1/models"
# key 优先环境变量，其次读包内 config/aihub.env；都没有则对照表上架列标 —
_HUB_KEY = os.environ.get("AIHUB_KEY")


def hub_key():
    global _HUB_KEY
    if _HUB_KEY:
        return _HUB_KEY
    env = os.path.join(SKILL, "config", "aihub.env")
    try:
        for line in open(env, encoding="utf-8"):
            m = re.match(r"^AIHUB_KEY\s*=\s*(.+?)\s*$", line)
            if m:
                _HUB_KEY = m.group(1).strip("'\"" )
                return _HUB_KEY
    except OSError:
        pass
    return None


def fetch_hub_ids():
    key = hub_key()
    if not key:
        return None
    req = urllib.request.Request(HUB_URL, headers={
        "Authorization": "Bearer " + key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print("⚠️ AIHub 列表获取失败：%s" % e, file=sys.stderr)
        return None
    return sorted({m["id"] for m in data.get("data", [])})


# ── 思考等级 ──────────────────────────────────────────────────────────────
LEVELS = ["Minimal", "Low", "Medium", "High", "Xhigh", "Max"]
LORDER = {k.lower(): i for i, k in enumerate(LEVELS)}
FLAGS = {"reasoning", "non-reasoning"}


def base_name(name):
    return re.split(r"\s*\(", name)[0].strip()


def tokens(name):
    out = []
    for grp in re.findall(r"\(([^)]*)\)", name):
        out += [t.strip() for t in grp.split(",")]
    return out


def family_effort(all_models):
    """(creator, base_name) → {'levels': [...], 'flags': {...}}"""
    fam = {}
    for m in all_models:
        cr = gs.creator(m)
        k = (cr, base_name(m.get("name") or ""))
        t = tokens(m.get("name") or "")
        d = fam.setdefault(k, {"levels": set(), "flags": set()})
        for x in t:
            xl = x.lower()
            if xl in LORDER:
                d["levels"].add(LEVELS[LORDER[xl]])
            elif xl in FLAGS:
                d["flags"].add(xl)
    return fam


def effort_cell(m, fam):
    k = (gs.creator(m), base_name(m.get("name") or ""))
    d = fam.get(k) or {"levels": set(), "flags": set()}
    have = sorted(d["levels"], key=lambda x: -LORDER[x.lower()])
    cur = [x for x in tokens(m.get("name") or "") if x.lower() in LORDER]
    cur = cur[0] if cur else None
    if have:
        parts = [(x + "★") if x == cur else x for x in have]
        return " / ".join(parts)
    if d["flags"] == {"non-reasoning"}:
        return "不支持思考（non-reasoning）"
    if {"reasoning", "non-reasoning"} <= d["flags"]:
        return "可开关思考，AA 未分档"
    return "未分档（AA 未按档评测）"


# ── 厂商官方思考机制（2026-10-21 实测，证据见 references/effort-official.md）─────
# grade: 上游确认 > 效果实测 > 仅开关 > 未实测 > 未知
OFFICIAL = {
    "OpenAI": dict(
        mech="reasoning_effort",
        levels="low / medium / high / xhigh",
        off="可（省略或 none 即不思考）",
        ev="上游报错原文列举四档；实测 low 0 / high 54 / xhigh 101 reasoning tokens，单调递增",
        grade="上游确认"),
    "Z AI": dict(
        mech="reasoning_effort（模型始终思考）",
        levels="low / high / max",
        off="不可关闭",
        ev="上游报错原文「该模型始终思考，不支持关闭思考；请使用 low、high 或 max」；实测 low 0 / high 13 / max 226，单调",
        grade="上游确认"),
    "Google": dict(
        mech="reasoning_effort（thinking_level 被网关拒为 422）",
        levels="low / medium / high（max 被接受但 0 思考，实为无效）",
        off="可（low/medium 即 0 思考）",
        ev="逐档效果实测 low 0 / medium 0 / high 338 / max 0",
        grade="效果实测"),
    "Alibaba": dict(
        mech="enable_thinking（布尔）+ thinking_budget（token 预算）",
        levels="无离散档；reasoning_effort 七值均被接受但无单调性",
        off="可（enable_thinking=false → 0 tokens）",
        ev="none→0；low 95 / medium 124 / high 86 / max 49，非单调，说明七档是网关全局枚举而非模型能力",
        grade="效果实测"),
    "DeepSeek": dict(
        mech="reasoning_effort",
        levels="none / low / high / max 均接受，仅 none 与其余有稳定差异",
        off="可（none → 0 tokens）",
        ev="none→0；low 48 / high 46 / max 73，档位间无稳定单调",
        grade="效果实测"),
    "Kimi": dict(
        mech="reasoning_effort + thinking.type 开关",
        levels="none / low / medium / high / max 均接受但无单调性（非法值也放行）",
        off="可（none 或 thinking.type=disabled → 0 tokens）",
        ev="none→0；low 99 / medium 62 / high 38 / max 131，随机波动，仅开关可信",
        grade="仅开关"),
    "Anthropic": dict(
        mech="thinking.budget_tokens（token 预算，无离散档）",
        levels="无离散档，按预算 token 控制",
        off="可（thinking.type=disabled）",
        ev="AIHub 网关对 thinking/reasoning_effort 一律 422「unsupported conversation shape」，字段无法透传，未能实测",
        grade="未实测"),
    "SpaceXAI": dict(
        mech="reasoning_effort（据 AA 名称含 Xhigh）",
        levels="待核",
        off="待核",
        ev="上游路由 503，探测不可用",
        grade="未实测"),
}


# ── AIHub 匹配 ────────────────────────────────────────────────────────────
# 已核实的人工映射：AA slug → (hub id, 说明, 证据等级)
# 依据：直接请求该 id，读响应里的上游 model 字段（网关回填真实构建号）
OVERRIDES = {
    "deepseek-v4-1-flash-1017": (
        "deepseek-flash-prime",
        "上游 model=deepseek-v4-1-flash-261017",
        "✅"),
}

# 已知「通用别名 → 旧版构建」，命中时标 ✅*（已上架但不是 AA 评测的那一版）
STALE_ALIAS = {
    "deepseek-v4-flash": "上游 model=deepseek-flash（通用别名，非 1017）",
    "deepseek-flash": "上游 model=deepseek-flash（通用别名，非 1017）",
    "deepseek-v4-flash-prime": "上游 model=deepseek-v4-flash-ga-260731（早 2.5 个月）",
}


def norm(s):
    s = (s or "").lower()
    s = s.replace(".", "-").replace("_", "-")
    s = re.sub(r"[^a-z0-9\-\s]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return re.sub(r"-+", "-", s)


def variants(row):
    """由 AA 名称/slug 派生候选 hub id。命名风格各家不一：
    Anthropic/GPT 用连字符（claude-opus-5-5），通义/GLM/Kimi 保留点号（qwen3.8-max）。
    带日期/版本 token 的「具体构建」优先于通用别名。
    """
    slug = row["slug"]
    nm = base_name(row["name"])
    low = re.sub(r"\s+", "-", nm.strip().lower())
    forms = []
    for f in (low, norm(nm)):          # 保留点号 / 点号转连字符
        if f and f not in forms:
            forms.append(f)
    dated = []
    for t in tokens(row["name"]):
        if re.fullmatch(r"\d{3,8}", t):
            dated += [f + "-" + t for f in forms] + [slug + "-" + t]
    out = [slug] + dated + [f for f in forms if f != slug]
    seen, res = set(), []
    for x in out:
        if x and x not in seen:
            seen.add(x)
            res.append(x)
    return res


def match_hub(row, ids):
    """→ (状态, hub_id, 说明)"""
    if ids is None:
        return "—", "—", "AIHub 列表不可达"
    ov = OVERRIDES.get(row["slug"])
    if ov:
        hid, note, st = ov
        return (st if hid in ids else "❌"), hid, note if hid in ids else "映射 id 不在列表中"

    idset = set(ids)
    for cand in variants(row):
        for suf in ("", "-hc"):
            c = cand + suf
            if c in idset:
                st, note = "✅", ""
                if suf:
                    note = "托管版（-hc）"
                if c in STALE_ALIAS:
                    st, note = "✅*", STALE_ALIAS[c]
                return st, c, note
    # 前缀近似（只报疑似，不下结论）
    for cand in variants(row):
        if len(cand) < 6:
            continue
        near = [i for i in ids if i.startswith(cand + "-") or i.startswith(cand)]
        if near:
            near.sort(key=len)
            return "❓", near[0], "前缀近似，需人工确认"
    return "❌", "—", ""


# ── 思考等级：向 AIHub 网关实测可选值 ─────────────────────────────────────
EFFORT_ORDER = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
PROBE_CACHE = os.path.join(SKILL, ".cache", "_effort_probe.json")
PROBE_MODEL = "__probe__"   # 故意非法值：网关通常会回错误并列出全部可选值


def load_probe():
    try:
        return json.load(open(PROBE_CACHE))
    except Exception:  # noqa: BLE001
        return {}


def save_probe(d):
    os.makedirs(os.path.dirname(PROBE_CACHE), exist_ok=True)
    json.dump(d, open(PROBE_CACHE, "w"), ensure_ascii=False, indent=1)


def _call(hub_id, key, effort):
    """单次极小请求：→ (http_ok, body)"""
    payload = {"model": hub_id, "max_tokens": 4,
               "messages": [{"role": "user", "content": "hi"}]}
    if effort is not None:
        payload["reasoning_effort"] = effort
    req = urllib.request.Request(
        os.environ.get("AA_HUB_URL_BASE", "https://ai.yunxinapi.com/hub/v1") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return False, e.read().decode("utf-8", "ignore")
    except Exception as ex:  # noqa: BLE001
        return False, "EXC:%s" % ex


def parse_enum(body):
    """从错误信息里抓网关主动列出的可选值"""
    low = body.lower()
    found = set(m.group(1) for m in re.finditer(r"'([a-z]{2,8})'", low))
    for seg in re.findall(r"[：:]\s*([a-z、,\s]{8,})", low):
        found |= {x for x in re.split(r"[、,\s]+", seg) if x}
    lv = [x for x in EFFORT_ORDER if x in found]
    return lv if len(lv) >= 2 else None


def probe_effort(hub_id, key):
    """→ (levels|None, note)

    1) 先用非法值探测：网关通常会直接列出全部可选值；
    2) 若不列举但确实校验该参数，则逐档试（7 次极小请求）拿到真实支持集；
    3) 非法值也返回 200 → 网关不校验，判为无法枚举。
    """
    ok, body = _call(hub_id, key, PROBE_MODEL)
    if ok:
        return None, "网关不校验 reasoning_effort（非法值也放行），无法枚举"
    lv = parse_enum(body)
    if lv:
        return lv, "AIHub 网关实测（错误信息列举）"
    bl = body.lower()
    if "unsupported conversation shape" in bl:
        return None, "Claude 系走 thinking budget，不吃 reasoning_effort"
    if "route unavailable" in bl or "503" in bl:
        return None, "上游路由 503，暂时无法探测"
    if "reasoning_effort" not in bl and "thinking" not in bl:
        return None, "网关未就该参数报错，无法枚举"
    # 逐档试：只有明确校验参数时才值得花这 7 次
    good = [x for x in EFFORT_ORDER if _call(hub_id, key, x)[0]]
    if good:
        return good, "AIHub 网关实测（逐档试探）"
    return None, "网关拒绝该参数，疑似不支持 reasoning_effort"


def effort_for(hub_id, row_model, fam, key, cache):
    if hub_id and hub_id != "—" and key:
        c = cache.get(hub_id)
        if c is None:
            lv, note = probe_effort(hub_id, key)
            c = cache[hub_id] = {"levels": lv, "note": note}
        if c.get("levels"):
            return " / ".join(c["levels"]) + "（网关实测）"
    base = effort_cell(row_model, fam)
    if base.startswith("未分档"):
        return "未知（未上架，无法核验）"
    if "★" in base or " / " in base:
        return base + "（AA 分档）"
    return base   # 「不支持思考」「可开关但未分档」等定性结论，不再加来源后缀


# ── 主流程 ────────────────────────────────────────────────────────────────
def agent_price(pi, po, cc, R=50.0, h=0.90):
    c = cc if cc is not None else 0.10
    return (R * (c * h + (1 - h)) * pi + po) / (R + 1)


def main():
    cp = gs.load_cache_prices()
    rows = gs.extract(cp)
    allm = json.load(open(gs.CACHE))["data"]
    fam = family_effort(allm)
    by_slug = {m["slug"]: m for m in allm}
    tops = gs.vendor_tops(rows)
    ids = fetch_hub_ids()
    key = hub_key()
    cache = load_probe() if key else {}

    out = []
    for vendor, r in sorted(tops.items(), key=lambda kv: (-kv[1]["a"], kv[0])):
        st, hid, note = match_hub(r, ids)
        m = by_slug.get(r["slug"], {})
        off = OFFICIAL.get(vendor) or dict(
            mech="未知（未上架，无法核验）", levels="—", off="—",
            ev="", grade="未知")
        out.append({
            "厂商": vendor,
            "厂商最强模型(AAII)": r["name"],
            "AAII": r["a"],
            "AA 评测档位": next((x for x in tokens(r["name"]) if x.lower() in LORDER), "—"),
            "官方思考机制": off["mech"],
            "官方有效档位": off["levels"],
            "可关闭思考": off["off"],
            "证据等级": off["grade"],
            "AIHub已上架": st,
            "AIHub模型ID": hid if hid != "—" else "—",
            "备注": note,
        })

    if key and cache:
        save_probe(cache)
    os.makedirs(DATA, exist_ok=True)
    csv_path = os.path.join(DATA, "aa_top_vs_aihub_%s.csv" % TAG)
    cols = list(out[0].keys())
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)

    html_path = os.path.join(DATA, "aa_top_vs_aihub_%s.html" % TAG)
    open(html_path, "w", encoding="utf-8").write(render(out, cols))

    ok = sum(1 for r in out if r["AIHub已上架"].startswith("✅"))
    print("表已生成：%s" % csv_path)
    print("           %s" % html_path)
    print("共 %d 家厂商，AIHub 已上架 %d / %d" % (len(out), ok, len(out)))
    if ids is None:
        print("⚠️ AIHub 列表不可达，上架列全部标 —")
    return 0


def render(out, cols):
    import base64, io as _io
    _buf = _io.StringIO()
    _buf.write("\ufeff")
    _w = csv.DictWriter(_buf, fieldnames=cols, lineterminator="\n")
    _w.writeheader()
    _w.writerows(out)
    csv64 = base64.b64encode(_buf.getvalue().encode("utf-8")).decode("ascii")
    cn = [r for r in out if r["厂商"] in gs.CHINA]
    ok = sum(1 for r in out if r["AIHub已上架"].startswith("✅"))

    def cell(k, v):
        if k == "AIHub已上架":
            cls = {"✅": "ok", "✅*": "ok", "❓": "q", "❌": "no"}.get(v, "no")
            return '<td><span class="b %s">%s</span></td>' % (cls, esc(v))
        if k == "AAII":
            return '<td class="num"><b>%s</b></td>' % v
        if k.startswith("有效价"):
            return '<td class="num">$%.3f</td>' % v
        if k == "AA 评测档位":
            return '<td class="dim">%s</td>' % esc(v)
        if k == "官方思考机制":
            return '<td class="eff">%s</td>' % esc(v)
        if k == "官方有效档位":
            return '<td class="eff">%s</td>' % esc(v)
        if k == "证据等级":
            cls = {"上游确认": "ok", "效果实测": "q", "仅开关": "q",
                   "未实测": "dim", "未知": "no"}.get(v, "dim")
            return '<td><span class="b %s">%s</span></td>' % (cls, esc(v))
        if k == "可关闭思考":
            return '<td class="dim">%s</td>' % esc(v)
        if k == "AIHub模型ID":
            return '<td class="mono">%s</td>' % esc(v)
        if k == "备注":
            return '<td class="note">%s</td>' % esc(v)
        return "<td>%s</td>" % esc(v)

    trs = []
    for r in out:
        cls = " cn" if r["厂商"] in gs.CHINA else ""
        trs.append('<tr class="%s">%s</tr>' % (
            cls.strip(), "".join(cell(k, r[k]) for k in cols)))

    return """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>厂商最强模型 × AIHub 上架对照 %(snap)s</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;padding:28px 24px 48px;background:#0e1117;color:#e6e9f0;
 font:14px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif}
h1{font-size:20px;margin:0 0 6px;letter-spacing:.2px}
.sub{color:#8b93a7;font-size:12.5px;margin-bottom:18px}
.sub b{color:#e6e9f0}
.wrap{overflow:auto;border:1px solid #222839;border-radius:10px;background:#121620}
table{border-collapse:separate;border-spacing:0;width:100%%;min-width:1180px;font-size:12.8px}
th{position:sticky;top:0;z-index:2;background:#1a1f2c;color:#a7b0c6;font-weight:600;
 text-align:left;padding:10px 12px;border-bottom:1px solid #2a3145;white-space:nowrap}
td{padding:8px 12px;border-bottom:1px solid #1b2130;vertical-align:top}
tbody tr:hover td{background:#171d2a}
tr.cn td:first-child{box-shadow:inset 3px 0 0 #d9a441}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:#9fd0ff}
td.eff{color:#cfd6e6}
td.dim{color:#8b93a7}
td.note{color:#8b93a7;font-size:12px}
.st{color:#f2c14e}
.b{display:inline-block;min-width:24px;text-align:center;border-radius:5px;padding:1px 6px;
 font-size:12px;font-weight:600}
.b.ok{background:#12351f;color:#4ade80;border:1px solid #1d5e36}
.b.q{background:#332a12;color:#f2c14e;border:1px solid #5c4a1d}
.b.no{background:#31161a;color:#f87171;border:1px solid #5c232b}
.foot{margin-top:14px;color:#7a8296;font-size:12px;line-height:1.7}
code{background:#1a1f2c;padding:1px 5px;border-radius:4px;font-size:11.5px;color:#9fd0ff}
.bar{display:flex;align-items:center;gap:10px;margin:0 0 12px}
.bar .dl{cursor:pointer;background:#1a1f2c;color:#cfd6e6;border:1px solid #2a3145;text-decoration:none;
 border-radius:7px;padding:6px 13px;font-size:12.5px;font-weight:600;font-family:inherit}
.bar .dl:hover{background:#222a3b;border-color:#3a4560;color:#fff}
.bar .hint{color:#7a8296;font-size:12px}
</style></head><body>
<h1>厂商最强模型 × AIHub 上架对照</h1>
<div class="sub">数据快照 <b>%(snap)s</b> · AAII 与价格来自 Artificial Analysis · AIHub 列表实时拉取 ·
共 <b>%(n)d</b> 家厂商，已上架 <b>%(ok)d</b> 家 · 左金条为国产厂商</div>
<div class="bar"><a class="dl" download="aa_top_vs_aihub_%(snap)s.csv" href="data:text/csv;charset=utf-8;base64,%(csv64)s">⤓ 下载 CSV</a><span class="hint">字段与本地 CSV 完全一致（UTF-8 BOM，Excel 可直接打开）</span></div>
<div class="wrap"><table>
<thead><tr>%(head)s</tr></thead><tbody>
%(body)s
</tbody></table></div>
<div class="foot">
<b>厂商最强</b>：非退役、AA 实测（不含外部补充）中 AAII 最高；同分取更便宜者。与斩杀线图同一口径。<br>
<b>AA 评测档位</b>：Artificial Analysis 在模型名括号里标注的压测强度标签（Max/Xhigh/High…），是<b>评测标签，不是 API 参数</b>；空白表示 AA 未标注。<br>
<b>官方思考机制 / 官方有效档位</b>：按厂商原生参数逐个实测（reasoning_effort / enable_thinking / thinking.budget_tokens / thinking_level），并做<b>效果验证</b>——
同一问题下 reasoning tokens 是否随档位单调变化。仅 HTTP 200 不算数：网关对 reasoning_effort 有全局七值枚举，任何模型传非法值都会回这条枚举，
但 GLM 实际只认 low/high/max，Qwen/Kimi 的七档则无单调性（只有开关可信）。<br>
<b>证据等级</b>：上游确认（报错原文点名档位）＞效果实测（逐档单调）＞仅开关（只能开/关）＞未实测 ＞未知。<br>
<b>价格</b>：本表不列价格，价格维度（牌价、缓存折扣、Agent 有效价）见配套的两张斩杀线图。<br>
<b>上架判定</b>：✅ 精确命中（含 -hc 托管版）｜✅* 命中的是通用别名、上游为更旧构建｜❓ 仅前缀近似，需人工确认｜❌ 未上架。<br>
<b>国产合计</b>：%(cnn)d 家中已上架 %(cnok)d 家。
</div>
</body></html>""" % {
        "csv64": csv64,
        "snap": SNAP,
        "n": len(out),
        "ok": ok,
        "head": "".join("<th>%s</th>" % esc(c) for c in cols),
        "body": "\n".join(trs),
        "cnn": len(cn),
        "cnok": sum(1 for r in cn if r["AIHub已上架"].startswith("✅")),
    }


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


if __name__ == "__main__":
    sys.exit(main())
