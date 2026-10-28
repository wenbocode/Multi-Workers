# agent-loop-autopilot-decide.md 配图资产

由 `mermaid-diagram-export` skill 从 `agent-loop-autopilot-decide.md` 导出，共 5 张。
高清规格：deviceScaleFactor=2、最大边 2400 CSS px、白底、neutral 主题。

| # | 文件 | 标题 |
|---|------|------|
| 01 | agent-loop-llm | 第一层：Agent Loop —— 一个「LLM ↔ 工具」的纯内循环 |
| 02 | autopilot-key | 第二层：Autopilot —— 跨 key 的编排外循环 |
| 03 | flow-03 | 从 25 个编号到 8 个职责 |
| 04 | gate-approve | gate 四选项：只有 approve 放行 |
| 05 | sequence-05 | 三层如何咬合：一次「不等人」的推进 |

## 再生成

```bash
python ~/.workbuddy/skills/mermaid-diagram-export/scripts/export_diagrams.py --md H:\git\Multi-Workers\docs\agent-loop-autopilot-decide.md --out H:\git\Multi-Workers\docs\diagrams\agent-loop-autopilot-decide
```

改写是**幂等**的：重复执行会先收起旧的 PNG 引用与折叠块，再按本次参数重建——
换 `--out` 不会叠加嵌套。若手上的 md 被旧版本叠加污染过，加 `--repair-md` 只修 md、不重渲。

`*.mmd` 为源码，可贴进 https://mermaid.live 二次编辑。
