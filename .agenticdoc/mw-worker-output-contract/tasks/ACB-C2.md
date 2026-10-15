# ACB-C2 · AC-010(b) 编码类探针 2（launcher 环境变量检查）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「凭证隔离：每个 Worker 只拿到它需要的 API key」）。
- 本任务是 T-08 部署后的 **AC-010(b) 编码类验证探针**：验证新 bundle 下受判产物能拿到「标题判定 + 机械段自动补齐」，从而 `exit=0`。
- 检查对象：`packages/multi-workers/launcher.py:130`（`base_url_env` 凭证剥离逻辑附近）。

## 写入允许面

- `packages/multi-workers/launcher.py`（仅修一处明显笔误，若有）
- `.agenticdoc/mw-worker-output-contract/evidence/acb-c2-notes.md`（改动记录）

## 写入禁止面

其余一切路径。**禁止 `npm run check`**；禁止无参全量 vitest/pytest。

## 要求

1. 只读检查 `launcher.py` 的凭证剥离：确认 `base_url_env` 命中的 provider 会在 worker 环境里删掉 base_url 变量（AC-024/AC-025）。若逻辑正确，明确说「正确」，不改代码；若有明显笔误修 1 处并说明。
2. 结论落 `evidence/acb-c2-notes.md`。
3. 若改代码，用 `python -X utf8 -m py_compile packages/multi-workers/launcher.py` 验证。

## 交付格式

`report.md` 五段齐全：`结论` / `证据` / `残留与未验证` / `上下文来源` / `改动清单`（若改：`launcher.py` 1 处 + 原因；未改：写「无改动」）。不要写 `## Questions` 段。

## 验收命令

```powershell
cd H:/git/Multi-Workers
python -X utf8 -m py_compile packages/multi-workers/launcher.py
```

## 改动历史

- 2026-10-15 PM 建立：AC-010(b) 编码类探针；改动记录落 `evidence/acb-c2-notes.md`（对照 trace.log 写入事件）。

[VERIFY] ACB-C2 探针交付：exit=0。
