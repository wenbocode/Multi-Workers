# decision-loop-design.md 配图资产

由 `mermaid-diagram-export` skill 从 `decision-loop-design.md` 导出，共 5 张。
高清规格：deviceScaleFactor=2、最大边 2400 CSS px、白底、neutral 主题。

| # | 文件 | 标题 |
|---|------|------|
| 01 | flow-01 | 图 1：入口在哪 —— 8 个决策入口 |
| 02 | prepare | 图 2：prepare —— 决策本里装什么 |
| 03 | decide | 图 3：decide —— 四道机械检查 |
| 04 | apply | 图 4：apply —— 答案、效果、结果三条轴 |
| 05 | flow-05 | 图 5：人在哪里 |

## 再生成

```bash
python ~/.workbuddy/skills/mermaid-diagram-export/scripts/export_diagrams.py --md H:\git\Multi-Workers\docs\decision-loop-design.md --out H:\git\Multi-Workers\docs\diagrams\decision-loop
```

改写是**幂等**的：重复执行会先收起旧的 PNG 引用与折叠块，再按本次参数重建——
换 `--out` 不会叠加嵌套。若手上的 md 被旧版本叠加污染过，加 `--repair-md` 只修 md、不重渲。

`*.mmd` 为源码，可贴进 https://mermaid.live 二次编辑。
