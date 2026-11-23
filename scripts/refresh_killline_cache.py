#!/usr/bin/env python3
"""刷新斩杀线图读取的本地缓存 _data_llms_models.json。

背景（2026-11-12）：AA 旧端点 /api/v2/data/llms/models 已退役（410），
aa_rank.fetch_models 已迁移到新免费分页端点 /language/models/free（并拍平 performance）。
但 gen_scatter_0915.py 仍直接读旧缓存文件 _data_llms_models.json，
不含 11-02 之后的新模型（如 Claude Fable 5.2）。

本脚本用修好的 fetch_models 拉全量（分页合并 + performance 拍平），
按旧缓存格式 {"data": [...]} 回灌到 _data_llms_models.json，供散点图继续读取。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aa_rank

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(SKILL, ".cache", "_data_llms_models.json")


def main():
    refresh = "--refresh" in sys.argv
    models, ts = aa_rank.fetch_models(refresh=refresh)
    out = {"status": 200, "prompt_options": {}, "data": models}

    # 与旧缓存字段名完全对齐：确保散点图读到的 median_* 在顶层
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, CACHE)

    n = len(models)
    n_fable52 = sum(1 for m in models if "fable-5-2" in (m.get("slug") or ""))
    print(f"已回灌斩杀线缓存 {CACHE}")
    print(f"  模型总数 {n}，其中含 Fable 5.2 {n_fable52} 个")
    print(f"  数据时间 {ts[:19]}")


if __name__ == "__main__":
    main()
