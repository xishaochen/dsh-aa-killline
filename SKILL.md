---
name: aa-killline
description: 模型斩杀线工具。当用户要更新或生成「模型斩杀线图」（全球/国产 AAII 性能-价格帕累托前沿散点图）、「厂商最强 × 网关上架对照表」，或提到「刷新斩杀线」「斩杀线更新」「更新模型收益榜」时使用。数据源为 Artificial Analysis Data API + OpenRouter 真实缓存读价 + OpenAI 兼容网关模型列表。支持 --offline 纯本地重算。
---

# 模型斩杀线

一键重算「全球/国产模型斩杀线图」+「厂商最强 × 网关上架对照表」。

## 首次使用（一次性）

```bash
# 1) 免费取一个 Artificial Analysis Data API key（https://artificialanalysis.ai）
# 2) 写入凭证（AIHub 列为可选，不配则对照表上架列显示 —）
mkdir -p config
echo "AA_API_KEY=你的key" > config/key.env
chmod 600 config/key.env
# 可选：
echo "AIHUB_KEY=你的网关key" > config/aihub.env && chmod 600 config/aihub.env
```

## 一键运行

```bash
bash scripts/update.sh
```

流程：刷新 AA 数据 → 刷新 OpenRouter 真实缓存读价 → 重算全球/国产斩杀线图 → 重算厂商最强对照表 → 产物落 `output/`。

| 产物（SNAP 默认当天） | 说明 |
|---|---|
| `斩杀线图_全球_YYYYMMDD.html` | AAII vs 有效价散点图（帕累托斩杀线、Agent 口径切换） |
| `斩杀线图_国产_YYYYMMDD.html` | 仅中国厂商版本 |
| `厂商最强_对照_YYYYMMDD.html/.csv` | 每家厂商最强模型 × 网关上架 × 官方思考机制 |

## 参数

| 参数 | 说明 |
|---|---|
| `--offline` | 不耗 API key，只用本地缓存重算（改汇率/快照日重算用这个） |
| `AA_SNAP=YYYY-MM-DD` | 数据快照日（默认今天） |
| `AA_FXR=6.7220` | USD→CNY 中间价（需更新时手动传） |
| `AA_FXR_DATE=YYYY-MM-DD` | 汇率取值日（图内注记） |
| `AA_OUT_DIR=...` | 产物目录（默认包内 `output/`） |
| `AA_RADAR_DIR=...` | 额外同步目录（可选） |

## 环境要求

- python3（3.9+，仅标准库，零 pip 依赖）
- curl（网络请求兜底）
- 凭证不随包分发：`config/key.env`（必需，刷新时）、`config/aihub.env`（可选，对照表网关列）

## 边界

- AA 免费 key 限流（约 100-1000 次/天），全量刷新一天一次即可；其余场景用 `--offline`。
- 图与表必须同批更新（口径一致铁律）；本 skill 已绑定为一条链路。
- 斩杀线 = 帕累托前沿：线右下方的模型被「更便宜且更聪明」的模型支配，视为被斩杀。
- 图内可切「官方 3:1 混合价 / Agent 口径（R=50, h=90%, c=真实缓存价）」。
