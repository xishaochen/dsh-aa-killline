# dsh-aa-killline

<a id="english"></a>

## Model Kill-Line Charts (English)

The "kill line" is the intelligence-vs-price Pareto frontier: any model below and to the right of it is dominated by a model that is both cheaper and smarter. This plugin recomputes on demand:

- **Global / China kill-line charts** (self-contained HTML): AIII intelligence vs effective price scatter with the Pareto frontier, switchable between the official 3:1 blended price and an agent perspective (R=50, h=90%, per-model real cache-read prices)
- **Strongest-model-per-vendor table** (HTML + CSV): each vendor's best AA-measured model cross-checked against an OpenAI-compatible gateway listing, plus official thinking controls

Data: [Artificial Analysis](https://artificialanalysis.ai) Data API (free key) + [OpenRouter](https://openrouter.ai) public API (no key). Python stdlib only, zero pip dependencies.

### Install

```sh
dsh plugin add dsh-aa-killline
```

First-time setup (credentials never ship with the package): copy `config.example.env` to `config/key.env` and fill in `AA_API_KEY=...` (Artificial Analysis free key). Optionally `config/aihub.env` with `AIHUB_KEY=...` for the gateway column; without it that column shows `—`.

Run: `bash scripts/update.sh` (full refresh, once a day is enough) or `bash scripts/update.sh --offline` (local recompute, spends no API quota).

If a local customized copy exists in `~/.dsh/skills/aa-killline/`, the local one (rank 400) wins over this plugin (rank 600) — by design.

[中文](#中文)

<a id="中文"></a>

## 模型斩杀线

「斩杀线」= 性能-价格帕累托前沿：前沿右下方的模型被「更便宜且更聪明」的模型支配，视为被斩杀。本插件一键产出：

- **全球/国产斩杀线图**（自包含 HTML）：AAII 智能指数 vs 有效价散点 + 帕累托前沿，支持「官方 3:1 混合价 / Agent 口径（R=50、h=90%、逐模型真实缓存读价）」切换
- **厂商最强对照表**（HTML + CSV）：每家厂商 AA 实测最强模型 × OpenAI 兼容网关上架状态 × 官方思考机制

数据源：[Artificial Analysis](https://artificialanalysis.ai) Data API（免费 key）+ [OpenRouter](https://openrouter.ai) 公开 API（无需 key）。Python 脚本仅标准库，零 pip 依赖。

## 安装

```sh
dsh plugin add dsh-aa-killline          # npm
# 或
dsh plugin add github:xishaochen/dsh-aa-killline
```

## 首次配置（一次性，凭证不随包分发）

```bash
cd <插件安装目录>   # npm 装的通常在 profile 的 node_modules/dsh-aa-killline
cp config.example.env config/key.env   # 然后填入你的 AA_API_KEY
chmod 600 config/key.env
```

可选（对照表的网关上架列；不配则显示 —）：

```bash
echo "AIHUB_KEY=<你的 OpenAI 兼容网关 key>" > config/aihub.env && chmod 600 config/aihub.env
```

## 使用

对 agent 说「刷新斩杀线」，或直接跑：

```bash
bash scripts/update.sh                 # 全量刷新（建议一天一次）
bash scripts/update.sh --offline       # 纯本地重算，不耗 API 额度
```

产物在 `output/`，浏览器直接打开。

## 与本地版本的关系

若同时在 `~/.dsh/skills/aa-killline/` 有本地特化版，本地版（rank 400）优先于本插件（rank 600）——刻意的，插件不覆盖用户自己的版本。

## 口径

- 斩杀线 = 帕累托前沿（价格升序，AAII 严格递增）
- 双价格口径：官方 3:1 混合价 / Agent 口径 `[R×(c×h+1−h)×输入 + 输出]/(R+1)`，默认 R=50、h=90%、c=OpenRouter 真实缓存读价
- 厂商最强 = 非退役、AA 实测中 AAII 最高，同分取更便宜者
- 图与表同批更新（同一快照、同一口径）

## License

MIT
