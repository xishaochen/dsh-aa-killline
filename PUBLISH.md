# awesome-dsh-plugin 收录条目（提交 PR 用）

仓库提交地址：https://github.com/awesome-dsh-plugin/awesome-dsh-plugin
PR 内容 = 新增一个文件 `data/plugins/xishaochen__dsh-aa-killline.yml`，内容如下：

```yaml
url: https://github.com/xishaochen/dsh-aa-killline
name: xishaochen/dsh-aa-killline
category: skill
description:
  en: 'Model kill-line charts: global and China AIII-vs-price Pareto frontiers from Artificial Analysis data plus a strongest-model-per-vendor table against an OpenAI-compatible gateway, recomputed on demand.'
  zh: '模型斩杀线图：基于 Artificial Analysis 数据的全球/国产性能-价格帕累托前沿，附厂商最强模型对照表（OpenAI 兼容网关上架状态），按需一键重算。'
```

注意（来自 contributing.md 的官方要求）：
- `description.en` 必填；`zh` 可留空由维护者补，这里已经写好
- 描述只说功能，不带营销词、不带 superlatives
- 仓库需满 1 天（CI 自动检查），加 `dsh-plugin` topic，含真实可用代码
- 发 npm 后市场还能拿到版本号与更新通道；GitHub-only 条目也能收录（装的时候用 github: 前缀）
- 不要手工编辑 awesome 列表的 README（由 `data/plugins/*.yml` 自动生成）
