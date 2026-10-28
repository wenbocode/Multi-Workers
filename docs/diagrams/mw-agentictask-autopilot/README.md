# mw-agentictask-autopilot-layered.md 配图资产

由 `mermaid-diagram-export` skill 从 `mw-agentictask-autopilot-layered.md` 导出，共 2 张。
高清规格：deviceScaleFactor=2、最大边 2400 CSS px、白底、neutral 主题。

| # | 文件 | 标题 |
|---|------|------|
| 01 | autopilot-conductor | 图 1：Autopilot —— conductor 编排主循环 |
| 02 | agentictask | 图 3：AgenticTask —— 阶段链与门禁 |

## 再生成

```bash
python ~/.workbuddy/skills/mermaid-diagram-export/scripts/export_diagrams.py --md H:\git\Multi-Workers\docs\mw-agentictask-autopilot-layered.md --out H:\git\Multi-Workers\docs\diagrams\mw-agentictask-autopilot
```

改写是**幂等**的：重复执行会先收起旧的 PNG 引用与折叠块，再按本次参数重建——
换 `--out` 不会叠加嵌套。若手上的 md 被旧版本叠加污染过，加 `--repair-md` 只修 md、不重渲。

`*.mmd` 为源码，可贴进 https://mermaid.live 二次编辑。
