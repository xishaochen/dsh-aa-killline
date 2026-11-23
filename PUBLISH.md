# awesome-dsh-plugin 收录条目（提交 PR 用）

已收录：https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/pull/17407（2026-11-22 合并）
描述更新（去掉对照表）：https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/pull/18031

条目文件：`data/plugins/xishaochen__dsh-aa-killline.yml`，当前内容（与 main 上已合并版本一致）：

```yaml
url: https://github.com/xishaochen/dsh-aa-killline
name: xishaochen/dsh-aa-killline
category: skill
description:
  en: 'Model kill-line charts for DSH. Reads Artificial Analysis model data and OpenRouter cache prices, then renders two self-contained HTML charts (global and China) plotting the AI intelligence index against effective price with the Pareto frontier drawn on top; each chart switches between the official 3-to-1 blended price and an agent-shaped price (50-to-1 input/output ratio, 90 percent cache hit rate, per-model real cache-read prices). Offline mode recomputes from the local cache without spending API quota; python3 standard library only, no pip install.'
  zh: '模型斩杀线图：读取 Artificial Analysis 模型数据与 OpenRouter 缓存价，渲染全球与国产两张自包含 HTML 图，横轴为价格、纵轴为智能指数，并画出帕累托前沿（即斩杀线）；可在官方 3:1 混合价与 Agent 口径（输入输出 50:1、缓存命中 90%、按模型真实缓存读价）之间切换。支持离线模式：用本地缓存重算，不消耗 API 额度；纯 python3 标准库，无需 pip 安装。'
```

注意（来自 contributing.md 的官方要求）：
- `description.en` 必填；`zh` 可留空由维护者补，这里已经写好
- 描述只说功能，不带营销词、不带 superlatives；描述必须与代码一致（0.1.1 起已无对照表，勿再写）
- 仓库需满 1 天（CI 自动检查，未满时由 regate.yml 每 6 小时自动重跑，不必重提）
- 不要手工编辑 awesome 列表的 README（由 `data/plugins/*.yml` 自动生成，合并后在 main 重建）
- 更新自己的条目只改自己那一个文件，别碰邻居

## 发版备忘（npm）

```bash
# 本机默认 registry 是内网 npm.nie.netease.com，必须显式指定公网并注入 token：
npm publish --registry https://registry.npmjs.org/ --//registry.npmjs.org/:_authToken=<granular token>
```

- `NODE_AUTH_TOKEN=` 单独设环境变量在 npm 11 下不生效（仍报 ENEEDAUTH），要用上面的命令行配置项
- PUT 返回 202 后 registry 要 1-2 分钟才出正式版本，期间 `npm view` 仍是旧版本，不要误判失败
- 发布后核对 `dist.shasum` 与本地 `npm pack` 是否逐字节一致
