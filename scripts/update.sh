#!/bin/bash
# aa-killline：模型斩杀线一键更新（DSH 插件公开版）
# 流程：刷新 AA LLM 数据 → 刷新 OpenRouter 真实缓存读价 → 重算全球/国产斩杀线图
#       → 重算「厂商最强 × AIHub 上架 × 思考等级」对照表 → 产物落本包 output/
# 注意：不含 PagesHub 发布；凭证不随包分发，首次使用前按 README 配置
#
# 可调环境变量：
#   AA_SNAP=YYYY-MM-DD  数据快照日（默认今天）
#   AA_FXR=6.7220       人民币中间价
#   AA_FXR_DATE=...     汇率取值日（图内注记）
#   PY=python3          Python 解释器（默认优先 DSH 自带 3.12，回退 /usr/bin/python3）
#   AIHUB_KEY=...       对照表用 AIHub 网关 key（默认读 config/aihub.env，缺失时上架列标 —）
#   AA_RADAR_DIR=...    额外同步目录（可选，默认不同步）
#
# 用法：
#   bash scripts/update.sh                # 全量刷新（AA 免费 key 限流，日跑一次安全）
#   bash scripts/update.sh --no-refresh   # 只用本地缓存重算（不耗 AA key）
#   bash scripts/update.sh --offline      # 同上（别名）

set -uo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${AA_OUT_DIR:-$SKILL_DIR/output}"
NO_REFRESH=0
[ "${1:-}" = "--no-refresh" ] || [ "${1:-}" = "--offline" ] && NO_REFRESH=1

# Python：优先 DSH 自带运行时（3.12，脚本仅标准库，任何 3.9+ 均可）
PY="${PY:-}"
if [ -z "$PY" ]; then
  for c in "${DSH_PYTHON:-}" "$HOME/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3" /usr/bin/python3 python3; do
    if [ -n "$c" ] && command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "❌ 未找到可用的 python3"; exit 1; }

SNAP="${AA_SNAP:-$(date +%Y-%m-%d)}"
TAG="${SNAP//-/}"
FXR="${AA_FXR:-6.7220}"
FXR_DATE="${AA_FXR_DATE:-2026-10-16}"

mkdir -p "$OUT_DIR"

echo "🔪 aa-killline 斩杀线更新 | 数据快照 ${SNAP}"
echo "────────────────────────────────────"

# 1) 刷新 AA 数据并回灌斩杀线缓存
if [ $NO_REFRESH -eq 1 ]; then
  echo "① 跳过 AA 数据刷新（--no-refresh，直接用本地缓存）"
else
  echo "① 刷新 Artificial Analysis LLM 数据并回灌斩杀线缓存…"
  if ! AA_OUT=$("$PY" "$SKILL_DIR/scripts/refresh_killline_cache.py" --refresh 2>&1); then
    echo "   ❌ AA 数据刷新失败："
    echo "$AA_OUT" | tail -8 | sed 's/^/   /'
    exit 1
  fi
  echo "$AA_OUT" | sed 's/^/   /'
fi

# 2) 刷新真实缓存读价（Agent 口径用；失败不阻断）
if [ $NO_REFRESH -eq 1 ]; then
  echo "② 跳过缓存读价刷新"
else
  echo "② 刷新 OpenRouter 真实缓存读价…"
  if ! CP_OUT=$("$PY" "$SKILL_DIR/scripts/fetch_cache_prices.py" --refresh 2>&1); then
    echo "   ⚠️ 缓存读价刷新失败，沿用旧缓存"
    echo "$CP_OUT" | tail -5 | sed 's/^/   /'
  fi
fi

# 3) 重算斩杀线图（输出直接落 output/）
echo "③ 重算全球 / 国产斩杀线图（汇率 ${FXR}，取值日 ${FXR_DATE}）…"
if ! GEN_OUT=$(AA_OUT_DIR="$OUT_DIR" AA_SNAP="$SNAP" AA_FXR="$FXR" AA_FXR_DATE="$FXR_DATE" "$PY" "$SKILL_DIR/scripts/gen_scatter_0915.py" 2>&1); then
  echo "   ❌ 斩杀线图生成失败："
  echo "$GEN_OUT" | tail -15 | sed 's/^/   /'
  exit 1
fi
echo "$GEN_OUT" | sed 's/^/   /'

# 4) 厂商最强 × AIHub 上架 × 思考等级 对照表（失败不阻断）
echo "④ 重算厂商最强 × AIHub 对照表…"
# AIHub key：环境变量 → config/aihub.env；都没有则 hub_key() 返回 None，上架列标 —
if [ -z "${AIHUB_KEY:-}" ] && [ -f "$SKILL_DIR/config/aihub.env" ]; then
  export AIHUB_KEY="$(grep -E '^AIHUB_KEY=' "$SKILL_DIR/config/aihub.env" | head -1 | cut -d= -f2- | tr -d '"'"'"'')"
fi
TBL_OUT=$(AA_OUT_DIR="$OUT_DIR" AA_SNAP="$SNAP" "$PY" "$SKILL_DIR/scripts/gen_top_table.py" 2>&1)
TBL_RC=$?
echo "$TBL_OUT" | sed 's/^/   /'
[ $TBL_RC -ne 0 ] && echo "   ⚠️ 对照表生成失败（图已生成，表未更新）"

# 5) 产物归集：直接在 output/ 生成，再补中文语义化副本
G="$OUT_DIR/aa_global_scatter_price_${TAG}.html"
C="$OUT_DIR/aa_china_scatter_price_${TAG}.html"
T1="$OUT_DIR/aa_top_vs_aihub_${TAG}.html"
T2="$OUT_DIR/aa_top_vs_aihub_${TAG}.csv"
echo "⑤ 产物："
[ -f "$G" ] && cp "$G" "$OUT_DIR/斩杀线图_全球_${TAG}.html" && echo "   ✅ 斩杀线图_全球_${TAG}.html"
[ -f "$C" ] && cp "$C" "$OUT_DIR/斩杀线图_国产_${TAG}.html" && echo "   ✅ 斩杀线图_国产_${TAG}.html"
[ -f "$T1" ] && cp "$T1" "$OUT_DIR/厂商最强_对照_${TAG}.html" && echo "   ✅ 厂商最强_对照_${TAG}.html"
[ -f "$T2" ] && cp "$T2" "$OUT_DIR/厂商最强_对照_${TAG}.csv" && echo "   ✅ 厂商最强_对照_${TAG}.csv"

# 6) 可选：额外同步目录（如另一份产出归档目录）
if [ -n "${AA_RADAR_DIR:-}" ] && [ -d "$AA_RADAR_DIR" ] && [ -f "$G" ] && [ -f "$C" ]; then
  cp "$OUT_DIR/斩杀线图_全球_${TAG}.html" "$AA_RADAR_DIR/"
  cp "$OUT_DIR/斩杀线图_国产_${TAG}.html" "$AA_RADAR_DIR/"
  echo "   ✅ 已同步到 ${AA_RADAR_DIR}"
fi

echo
echo "完成。产物目录：$OUT_DIR"
echo "打开示例：open \"$OUT_DIR/斩杀线图_全球_${TAG}.html\""
exit 0
