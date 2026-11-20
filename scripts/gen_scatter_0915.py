#!/usr/bin/env python3
"""生成性能-价格散点图（含帕累托前沿「斩杀线」）。

支持两种价格口径（前端可切换）：
  1) 官方 3:1 混合价（AA 口径）= (3×输入 + 1×输出) / 4
  2) Agent 口径 = [R×(c×h + 1−h)×输入 + 输出] / (R+1)
     其中 R=输入:输出比，h=缓存命中率，c=缓存读价÷输入价

模板：templates/scatter.html
"""
import json
import math
import os
from datetime import date as _date


def _days(s):
    try:
        return _date(*map(int, s.split("-"))).toordinal()
    except Exception:
        return 0

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
CACHE = os.path.join(SKILL, ".cache", "_data_llms_models.json")
CPRICE = os.path.join(SKILL, ".cache", "_cache_prices.json")
TPL = os.path.join(SKILL, "templates", "scatter.html")
# 输出目录：默认包内 output/（随包分发时可被 AA_OUT_DIR 覆盖）
OUT_DIR = os.environ.get("AA_OUT_DIR") or os.path.join(SKILL, "output")

# 数据快照日（与 AA 取数日一致）——用于输出文件名与图内注释，单点维护
# 可用环境变量 AA_SNAP=YYYY-MM-DD 覆盖（自动化脚本 update-killline.sh 用）
SNAP = os.environ.get("AA_SNAP") or "2026-10-20"
SNAP_TAG = SNAP.replace("-", "")

# 汇率：USD → CNY 人民币汇率中间价（中国货币网 CFETS）
# 取值日期与数据快照日一致（2026-09-29）。需更新时同步修改此处。
# 环境变量 AA_FXR / AA_FXR_DATE 可覆盖（自动化脚本用）
FXR = float(os.environ.get("AA_FXR") or 6.7220)

# ── 峰谷分时定价（AA 只收录峰值价，需单独标注并按需折算）────────────────────
# 来源：DeepSeek 官方定价页 https://api-docs.deepseek.com/quick_start/pricing（2026-10-21 核对）
#   谷时 = 峰值的一半；峰时 = UTC 01:00-04:00 + 06:00-10:00（周一至周五，扣中国法定节假日）
#   → 每周 7h×5d = 35h / 168h = 20.83% 为峰时，时间加权系数 = 0.2083×1 + 0.7917×0.5 = 0.6042
PEAK_PRICING = {
    "deepseek-v4-1-flash-1017": dict(off=0.50, peakshare=0.2083, wt=0.6042,
                                     hours="UTC 01-04、06-10（周一至周五）"),
    "deepseek-v4-pro": dict(off=0.50, peakshare=0.2083, wt=0.6042,
                            hours="UTC 01-04、06-10（周一至周五）"),
}
FXR_DATE = os.environ.get("AA_FXR_DATE") or "2026-10-16"
FXR_NOTE = ("中国货币网 CFETS 人民币汇率中间价（%s，最后可取日；2026-10-19 起"
            "CFETS 历史接口未返回数值，故沿用。US$ 为主单位，人民币仅作参考轴）" % FXR_DATE)

CHINA = {"Alibaba", "DeepSeek", "Kimi", "Z AI", "MiniMax", "Tencent", "Baidu",
         "ByteDance Seed", "Xiaomi", "KwaiKAT", "StepFun", "InclusionAI",
         "OpenBMB", "China Mobile", "LongCat", "Nanbeige"}

# 数据勘误：AA 对「已下线/旧代」模型保留的是历史挂牌价，与现役模型不可直接比价。
# 依据 DeepSeek 官方价格页脚注(1)：旧模型名 deepseek-v4-flash 等「对应模型已下线，
# 请求将由 DeepSeek-V4.1-Flash 提供服务，并按 Flash 价格计费」。
# 复核（2026-09-20）：官方页脚注仍为原文；AA 已把 deepseek-v4-flash 实测速度归零（已停测）；
# OpenRouter 上该档位仍有 27 个第三方提供方（无 DeepSeek 官方端点），最低 $0.04/$0.08（fp4 量化）。
# 注：用户搜不到该模型是因为「已下线」条目默认被过滤——图内已加搜索空命中提示。
RETIRED = {
    "deepseek-v4-flash-0420": "已下线（2026-04 版）",
    "deepseek-v4-flash-0420-high": "已下线（2026-04 版）",
    "deepseek-v4-flash-0420-non-reasoning": "已下线（2026-04 版）",
    "deepseek-v4-flash": "已下线（2026-07 版）",
    "deepseek-v4-flash-vision": "已下线（2026-08 版）",
}
RETIRED_ERRATA = (
    "数据勘误（已剔除已下线模型）：<b>DeepSeek V4 Flash 已下线</b>——官方价格页脚注明确，"
    "旧模型名 <code>deepseek-v4-flash</code> 仍可调用，但请求由 <b>DeepSeek-V4.1-Flash</b> "
    "提供服务并按 Flash 价计费（即两者<b>现价相同</b>）。该家族在 AA 那里保留的是"
    "<b>退役版本的历史价</b>（4 月档 <span id='nv1'></span>、7 月档 <span id='nv2'></span>、"
    "6 月非推理档 <span id='nv3'></span>），拿它与现役模型比价会<b>系统性便宜</b>——"
    "这就是图上「V4 Flash 比 V4.1 Flash 便宜 3 倍」的全部原因。"
    "本图<span id='nret'></span>。"
    "若把它们加回，国内版斩杀线会由 <b>5 个增至 6 个</b>（DeepSeek V4 Flash 重新出现在线上）。<br>"
    "但要说清：<b>官方「已下线」≠ 不可用</b>——该档位在 OpenRouter 上仍由 <b>27 个第三方提供方</b>托管"
    "（<b>无 DeepSeek 官方端点</b>），fp4/fp8 <b>量化重托管</b>低至 <b>$0.04/$0.08</b>（约为上图价的 1/11，"
    "AA 记录的 $0.44/$1.32 对应的是最贵一档），且周用量居 <b>全球第 5</b>（约 5.29 亿次请求）——"
    "单价低来自量化托管，与官方口径不可直接比价。<br>"
    "另：DeepSeek 现价为<b>分时计价</b>（官方人民币牌价：高峰 ¥2/¥8、空闲 ¥1/¥4，空闲价减半），"
    "AA 只记录<b>高峰档</b>，故 V4.1 Flash 在空闲时段实际可低至图中一半。")

PALETTE = ["#5d8be8", "#f5a623", "#e05d5d", "#4ec9b0", "#9b8afb", "#f0883e",
           "#e8a33d", "#d97757", "#10a37f", "#4a7fe8", "#8b8f9a", "#c05dd9",
           "#6fcf97", "#eb6f92", "#7aa2f7"]


def creator(m):
    c = m.get("model_creator")
    return c.get("name", "?") if isinstance(c, dict) else (c or "?")


def short(name):
    """保留推理档位，便于区分同模型的多个变体。"""
    if " (" not in name:
        return name
    base, rest = name.split(" (", 1)
    rest = rest.rstrip(")")
    low = rest.lower()
    for key, tag in (("max effort", "max"), ("max", "max"), ("xhigh", "xhigh"),
                     ("high effort", "high"), ("high", "high"), ("medium", "medium"),
                     ("low effort", "low"), ("low", "low"), ("non-reasoning", "non-reasoning")):
        if key in low:
            return base + " (" + tag + ")"
    return base


# 外部补充模型：AA 尚未收录，价格取自厂商官方定价页（非 AA 口径），图中默认不显示。
# 加入原因：用户告知国内已上线 GLM-5.3-FlashX（2026-09-18），但当日 AA/OpenRouter 均未收录。
EXT = [
    {"slug": "glm-5-3-flashx", "name": "GLM-5.3-FlashX", "sn": "GLM-5.3-FlashX",
     "c": "Z AI", "china": True, "rel": "2026-09-18",
     # AA 未单独评测 FlashX；它与 GLM-5.3-Flash 同基座（320B/18B），仅为提速版，故沿用同一 AAII
     "a": 41.9,
     # 价格 = AA 口径下 GLM-5.3-Flash 的 2.5 倍（官方牌价 ¥2/¥7 vs ¥0.8/¥2.8，恰为 2.5×）
     "pi": 0.375, "po": 1.25, "cr": 0.1069,
     "sp": 200, "ttft": 0, "ret": None,
     "esrc": ("智谱官方牌价 ¥2 / ¥7 每百万 tokens（缓存命中 ¥0.57），"
              "为 GLM-5.3-Flash 的 2.5 倍；官方称推理速度 200 t/s。"
              "图中价格按 AA 口径归一（即 AA 中 GLM-5.3-Flash 的 2.5 倍），故人民币值略高于官方牌价")},
    # 2026-10-20：DeepSeek V4.1-Flash-1017（2026-10-17 发布）曾被列在这里作外部补充
    # （当时 AA 未收录，手工借用前代 AAII 39.5、价格 $0.15/$0.60）。
    # AA 已于 2026-10-20 正式收录（AI Index 45.1，$0.30/$1.20，缓存读 $0.006）。
    # 现由 extract() 从 AA 缓存直接取真值，**本条必须删除**，否则会与真实条目同 slug 重复且注入错误分数。
]


def escattr(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def fmt(p):
    if p < 0.01:
        return "$%.4f" % p
    return ("$%.3f" % p) if p < 0.1 else ("$%.2f" % p)


def load_cache_prices():
    """真实逐模型缓存读价（来自 fetch_cache_prices.py，源 OpenRouter）。"""
    if not os.path.exists(CPRICE):
        print("! 未找到 %s，将退化为统一折扣。先跑 fetch_cache_prices.py" % CPRICE)
        return {}
    return json.load(open(CPRICE))


def extract(cp):
    d = json.load(open(CACHE))["data"]
    rows = []
    for m in d:
        a = (m.get("evaluations") or {}).get("artificial_analysis_intelligence_index")
        pr = m.get("pricing") or {}
        i, o = pr.get("price_1m_input_tokens"), pr.get("price_1m_output_tokens")
        if a is None or not i or not o:
            continue
        c = creator(m)
        real = cp.get(m.get("slug")) or {}
        # 缓存折扣一律用 AA 的输入价做分母重算：OpenRouter 记录的 c 用的是 OR 上的
        # prompt 价，某些模型匹配到的是另一价档（如第三方托管版），会算出 c≈88% 的假值。
        # 重算后只保留 0 < c <= 50% 的合理区间，越界视为匹配不可靠，回退统一折扣。
        cr = real.get("cr")
        cr = cr if (cr is not None and cr > 0) else None
        cc = round(cr / i, 6) if (cr is not None and 0 < cr / i <= 0.5) else None
        rows.append({"slug": m.get("slug"), "name": m.get("name"), "sn": short(m.get("name")),
                     "c": c, "a": a, "pi": i, "po": o,
                     "sp": m.get("median_output_tokens_per_second") or 0,
                     "ttft": m.get("median_time_to_first_token_seconds") or 0,
                     "china": c in CHINA, "rel": m.get("release_date") or "",
                     "cr": cr, "cc": cc,
                     "pk": PEAK_PRICING.get(m.get("slug")),
                     "orid": real.get("orid"),
                     "ret": RETIRED.get(m.get("slug"))})
    return rows


def frontier(rows, key):
    s = sorted(rows, key=lambda r: (r[key], -r["a"]))
    out, best = [], -1
    for r in s:
        if r["a"] > best:
            out.append(r)
            best = r["a"]
    return out


def vendor_tops(rows):
    """标记「厂商最强」：该厂商当前在售（非退役）、AA 实测（不含外部补充）中 AAII 最高者。

    同分取更便宜者。必须用全局集合计算，国产图直接继承同一标记。
    """
    best = {}
    for r in rows:
        if r.get("ret") or r.get("ext"):
            continue
        p = r.get("p")
        if p is None:
            p = (3 * r["pi"] + r["po"]) / 4
        cur = best.get(r["c"])
        if cur is None or (r["a"], -p) > (cur["a"], -cur.get("_p", 0)):
            r["_p"] = p
            best[r["c"]] = r
    topset = {r["slug"] for r in best.values()}
    for r in rows:
        r["top"] = 1 if r["slug"] in topset else 0
    for r in rows:
        r.pop("_p", None)
    return best


def legend_html(counts, cmap, cn_toggle):
    items = []
    for c in sorted(counts, key=lambda x: (-counts[x], x)):
        items.append('<span class="lg" data-vendor="%s" title="点击筛选 %s（%d 个）">'
                     '<i style="background:%s"></i>%s</span>'
                     % (escattr(c), escattr(c), counts[c], cmap[c], escattr(c)))
    if cn_toggle:
        items.append('<span class="lgsep"></span>')
        items.append('<span class="lg" data-cn="1" title="仅看中国/中资厂商模型">'
                     '<i class="cnm"></i>仅国产模型</span>')
    items.append('<span class="lgsep"></span>')
    items.append('<span class="lg starhint" title="每个厂商当前在售、AA 实测 AAII 最高的模型，'
                 '用五角星表示（颜色仍为厂商色）">'
                 '<i class="star"></i>厂商最强</span>')
    return "".join(items)


def build(rows, title, sub, note, out, cn_toggle=False, cov=None, ext=None):
    # 外部补充条目并入数据集（与退役条目一样参与斩杀线计算，但默认不显示）
    rows = [dict(r) for r in rows] + [dict(e) for e in (ext or [])]
    for r in rows:
        if r.get("esrc"):
            r["ext"] = 1
            # 近 30 天发布的外部补充默认展示（刚发布的新模型用户就是要看它），更早的仍默认隐藏
            r["extnew"] = 1 if (SNAP and r.get("rel") and (SNAP[:7] == r["rel"][:7] or abs(_days(SNAP) - _days(r["rel"])) <= 30)) else 0
            if r.get("cr"):
                r["cc"] = r["cr"] / r["pi"]
    # 图例计数只统计「默认展示」的模型（已下线条目默认剔除，可在图内勾选加回）
    allc = {}
    for r in rows:
        allc[r["c"]] = allc.get(r["c"], 0) + 1
    cmap, pal = {}, list(PALETTE)
    for c in sorted(allc, key=lambda x: -allc[x]):
        cmap[c] = pal.pop(0) if pal else "#7c8397"
    counts = {}
    for r in rows:
        if r.get("ret"):
            continue
        counts[r["c"]] = counts.get(r["c"], 0) + 1

    for r in rows:
        r["p"] = (3 * r["pi"] + r["po"]) / 4

    # 「厂商最强」由 main() 用**全局口径**预先算好并写入 top 标记（build 内不重算，
    # 否则国产子集会把「中国最强」错标成「厂商最强」）。此处仅透传。
    fr = frontier(rows, "p")
    fset = {r["slug"] for r in fr}
    top = {r["slug"] for r in sorted(rows, key=lambda r: -r["a"])[:8]}
    for r in rows:
        r["lb"] = 2 if r["slug"] in fset else (1 if r["slug"] in top else 0)

    payload = [{"slug": r["slug"], "name": r["name"], "sn": r["sn"], "c": r["c"], "a": r["a"],
                "pi": r["pi"], "po": r["po"], "sp": r["sp"], "ttft": r["ttft"],
                "rel": r["rel"], "china": r["china"], "co": cmap[r["c"]], "lb": r["lb"],
                "cr": r["cr"], "cc": r["cc"], "ret": r.get("ret"),
                "top": r.get("top") or 0,
                "ext": r.get("ext") or 0, "extnew": r.get("extnew") or 0, "esrc": r.get("esrc"),
                "pk": r.get("pk")}
               for r in rows]
    y1 = int(math.ceil(max(r["a"] for r in rows) * 1.06))
    cfg = {"W": 1000, "H": 600, "y1": y1, "yticks": list(range(0, y1 + 1, 10)),
           "nret": sum(1 for r in rows if r.get("ret")),
           "next": sum(1 for r in rows if r.get("ext")),
           "cov": cov or {"have": 0, "total": len(rows)}}

    tpl = open(TPL, encoding="utf-8").read()
    html = (tpl.replace("__TITLE__", title).replace("__SUB__", sub)
            .replace("__LEGEND__", legend_html(counts, cmap, cn_toggle))
            .replace("__NOTE__", note)
            .replace("__DATA__", json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c"))
            .replace("__FXR__", "%.4f" % FXR)
            .replace("__CFG__", json.dumps(cfg))
            .replace("__W__", str(cfg["W"])).replace("__H__", str(cfg["H"])))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(html)
    return fr, len(rows)


NOTE_HEAD = (
    "数据来源：<a href='https://artificialanalysis.ai'>artificialanalysis.ai</a>"
    "（Artificial Analysis Data API），快照 " + SNAP + "。仅收录<b>同时具备 AAII 与价格</b>的模型。<br>"
    "<b>价格单位</b>：<span id='ncur'></span>。海外厂商实际按各自渠道币种与汇率结算，"
    "此处为统一折算，仅便于横向比较，不等同于实际账单金额。<br>"
    "<b>斩杀线</b>＝帕累托前沿：位于线上的模型，不存在「比它更便宜且更聪明」的模型；"
    "线<b>右下方</b>的模型即被支配，视为被「斩杀」。"
    "AAII 为纯能力分，<b>不含价格因素</b>，性价比判断来自两条独立轴的交叉观察。<br>"
    "<b>外部补充</b>：<span id='next'></span>"
    "<b>价格口径</b>：<span id='nmode'></span><span id='nclip'></span><br>"
    "<b>参数含义</b>：<b>R</b>＝输入:输出比（agent 循环每轮重发上下文，输入远多于输出）；"
    "<b>h</b>＝缓存命中率（多大比例的输入 token 命中前缀缓存、按缓存读价计费）；"
    "<b>c</b>＝缓存读价 ÷ 输入价。"
    "有效输入价 = 牌价 × [ h×c + (1−h) ]，最终有效价 = R/(R+1) × 有效输入价 + 1/(R+1) × 输出价。<br>"
    "<b>缓存价来源</b>：<span id='ncache'></span>"
    "真实缓存读价来自 <a href='https://openrouter.ai'>OpenRouter</a> 公开 API 的 <code>pricing.input_cache_read</code>"
    "（逐模型真实挂牌价，非估算；<b>AA 免费 API 不提供该字段</b>）。"
    "注意：<b>同一厂商内部 c 也不同</b>（DeepSeek 内部 2.0%~70%、OpenAI 内部 10%~100%），"
    "统一折扣会掩盖这种差异。<b>真实缓存价会改变斩杀线成员</b>：例如国内版在统一 c=10% 时 "
    "DeepSeek V4 Flash 在线上，但按其真实 c=20% 计算后会被小米 MiMo-V2.5（c=2%）挤出斩杀线。<br>"
    "<b>为什么 Agent 口径不同</b>：AA 官方混合价按 3:1 输入:输出、且<b>不含缓存定价</b>。"
    "但实测 agent 循环中（AA Coding Agent Index）输入:输出接近 <b>50:1 ~ 77:1</b>，"
    "且 <b>约 90% 的输入 token 是缓存读</b>（前缀命中率可达 96%）。"
    "缓存读价通常仅为输入价的 2.5%~10%，故 3:1 口径会<b>系统性高估输入成本、并扭曲模型排序</b>。"
    "切换上方「Agent 口径」并调整 R / h / c 可看斩杀线如何移动。<br>"
    "<b>交互</b>：点击<b>图例中的厂商</b>可点亮该厂商全部模型（再次点击取消）；"
    "搜索框支持模型名/厂商关键词（空格分隔为多条件 AND）；"
    "命中模型以黄色光环点亮，点击下方标签可直接跳到该模型。"
    "<br>" + RETIRED_ERRATA)

NOTE_CN = NOTE_HEAD + ("<br>国产口径：Z AI(智谱)、Kimi(月之暗面)、Alibaba(通义)、DeepSeek、"
                       "MiniMax、Xiaomi、Tencent、ByteDance Seed、StepFun、InclusionAI、"
                       "OpenBMB、China Mobile、KwaiKAT、LongCat、Nanbeige。")


def main():
    cp = load_cache_prices()
    allrows = extract(cp)
    have = sum(1 for r in allrows if r["cc"] is not None)
    print("真实缓存读价覆盖：%d / %d（%.0f%%）" % (have, len(allrows), have / len(allrows) * 100))
    if cp:
        cs = sorted(r["cc"] for r in allrows if r["cc"] is not None)
        print("  真实 c 中位数 %.1f%%，区间 %.1f%% ~ %.1f%%"
              % (cs[len(cs) // 2] * 100, cs[0] * 100, cs[-1] * 100))
    vendor_tops(allrows)          # 全局口径打标，国产图继承同一结果
    ch = [r for r in allrows if r["china"]]
    cov_g = {"have": have, "total": len(allrows)}
    cov_c = {"have": sum(1 for r in ch if r["cc"] is not None), "total": len(ch)}
    g = build(allrows, "全球模型 性能–价格散点图（含斩杀线）",
              "AAII 智能指数 vs 有效价 · 全球 · " + SNAP + " · 白描边为国产模型 · 点击图例筛选厂商",
              NOTE_HEAD, os.path.join(OUT_DIR, "aa_global_scatter_price_%s.html" % SNAP_TAG), True, cov_g,
              ext=EXT)
    c = build(ch, "中国模型 性能–价格散点图（含斩杀线）",
              "AAII 智能指数 vs 有效价 · 仅中国/中资厂商 · " + SNAP + " · 点击图例筛选厂商",
              NOTE_CN, os.path.join(OUT_DIR, "aa_china_scatter_price_%s.html" % SNAP_TAG), False, cov_c,
              ext=EXT)
    for name, rows, (fr, n) in (("全球", allrows, g), ("国内", ch, c)):
        live = [r for r in rows if not r.get("ret")]
        for r in live:
            r["p"] = (3 * r["pi"] + r["po"]) / 4
        dfl = frontier(live, "p")
        print("%s：AA 收录 %d 个，默认展示 %d 个（剔除 %d 个已下线），另含外部补充 %d 个；斩杀线 %d 个（官方 3:1）"
              % (name, len(rows), len(live), len(rows) - len(live), len(EXT), len(dfl)))
        for r in sorted(dfl, key=lambda x: x["p"])[:12]:
            print("   %-42s aii %5s  %s  ¥%.2f" % (r["sn"][:42], r["a"], fmt(r["p"]), r["p"] * FXR))
        tops = sorted([r for r in live if r.get("top")], key=lambda x: -x["a"])
        if name == "全球":
            print("★ 厂商最强标记 %d 个：" % len(tops))
            for r in tops:
                print("   %-22s %-40s aii %5.1f" % (r["c"][:22], r["sn"][:40], r["a"]))


if __name__ == "__main__":
    main()
