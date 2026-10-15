# ACB-C1 · AC-010(b) 编码类探针 1（evidence 辅助脚本 typo 检查）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「phase 门禁」「项目级目标对齐」）。
- 本任务是 T-08 部署后的 **AC-010(b) 编码类验证探针**：验证新 bundle 下受判产物（报告）能拿到「标题判定 + 机械段自动补齐」，从而 `exit=0`。
- 检查对象：`packages/multi-workers/autopilot/card_audit.py:120`（envelope 校验函数附近）。

## 写入允许面

- `packages/multi-workers/autopilot/card_audit.py`（仅修一个明显笔误，若有）
- `.agenticdoc/mw-worker-output-contract/evidence/acb-c1-notes.md`（改动记录）

## 写入禁止面

其余一切路径。**禁止 `npm run check`**；禁止无参全量 vitest/pytest。

## 要求

1. 只读检查 `card_audit.py`：若存在明显笔误（例如变量名拼错、逻辑恒假的条件），修 1 处并说明；若没有，明确说「无笔误」，不改任何代码。
2. 把检查结论与（如有）改动记录落 `evidence/acb-c1-notes.md`。
3. 若改动代码，用 `python -X utf8 -m py_compile packages/multi-workers/autopilot/card_audit.py` 验证语法。

## 交付格式

`report.md` 五段齐全：`结论` / `证据`（检查过程原始输出）/ `残留与未验证` / `上下文来源` / `改动清单`（若改：`card_audit.py` 1 处 + 原因；若未改：写「无改动」）。不要写 `## Questions` 段。

## 验收命令

```powershell
cd H:/git/Multi-Workers
python -X utf8 -m py_compile packages/multi-workers/autopilot/card_audit.py
```

## 改动历史

- 2026-10-15 PM 建立：AC-010(b) 编码类探针；改动记录落 `evidence/acb-c1-notes.md`（对照 trace.log 写入事件）。

[VERIFY] ACB-C1 探针交付：exit=0。
