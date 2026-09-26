# T-10 文档 + dist 重建 + 全量回归

- AC: AC-009, AC-010, AC-012 · VC: VC-012, VC-016 · 波次: 4（最后）
- 写面：`packages/multi-workers/UPDATE.md`、`packages/multi-workers/README.md`、`packages/*/dist`（重建产物）

## 步骤

1. **文档**：`UPDATE.md` §2 指令矩阵加 `mw autopilot verify set/show/clear` 行（层级列 = 项目 / 机器）+ §1 锚点表补 A1b/A2b 行；`README.md` 加机器层（`~/.agents/autopilot-defaults.json`）/项目层两行对照表（照 RAG 段 `:258-267`）+ CLI 段；可机器判定的部分照 `test_rag_docs.py:157-189` 做 fenced block 与 CLI 输出逐字节比对（至少 usage 行）。**两侧同版本上线**的顺序写清（先 `mw build --install` 再重启 serve）。
2. **dist 重建**：确认工作树干净（仅本 key 改动）后 `python packages/multi-workers/mw.py build --install`；`git -c core.fileMode=false diff --exit-code -- packages/multi-workers/dist packages/coding-agent/dist` 必须为空。
3. **全量回归**：`packages/multi-workers` 默认套件 + `-m e2e_l2`；`packages/coding-agent` 相关 vitest；相对基线 `b0a30bc12` 记录零新增失败（两条外域先在红单独复核并说明）。
4. **交付**：`[VERIFY]` 行 + 报告含所有命令与原始输出片段。

## 验证

- 判据命令全部实跑并粘贴输出；产物 diff 为空；引用文档的 fenced block 与 CLI 输出一致。
