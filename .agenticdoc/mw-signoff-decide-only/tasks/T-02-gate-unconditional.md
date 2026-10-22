# T-02 — 门禁改造：`decision_signoff` 无条件执行 + 零决策行跳过

- type: coding
- owner key: mw-signoff-decide-only
- 派生自：`design.md` §2、`spec.md` AC-001/AC-002/AC-002b

## 上下文

项目目标见 `.agenticdoc/goal.md`。`done` 门禁不该要求一个决策模型没参与过的 key 交签收文件；`decision-scope.md` 标记彻底忽略。

必读证据（已落盘）：

- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-gate-structure-20261022.md` —— `check_gate` 结构、三个候选写法与推荐、插入点证明、廉价判据草案与行为矩阵、副本归属、测试影响。
- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-archive-scan-20261022.md` —— 判据取 raw `kind=decide`（含 dp25）的实测依据、`_row_matches_key` 边界、`collect()` 成本。

关键锚点（canonical = `.agents/skills/agentic-task/scripts/advance_phase.py`）：

- `.agents/skills/agentic-task/scripts/advance_phase.py:37` `DECISION_SCOPE_MARKER`
- `.agents/skills/agentic-task/scripts/advance_phase.py:107-121` 两条无条件旧规则（`glob_has_files` 与 `content_match(conclusion:)`）
- `.agents/skills/agentic-task/scripts/advance_phase.py:123-133` `decision_signoff` 规则定义
- `.agents/skills/agentic-task/scripts/advance_phase.py:343` 循环级 disable 短路
- `.agents/skills/agentic-task/scripts/advance_phase.py:420-426` `decision_signoff` 分支
- `.agents/skills/agentic-task/scripts/advance_phase.py:256` `_decision_signoff_disabled`
- `.agents/skills/agentic-task/scripts/advance_phase.py:271-329` `_decision_signoff_problems`
- `.agents/skills/agentic-task/scripts/advance_phase.py:307` `_load_decide_signoff`（插入点必须在其之前）

## 要求

1. 删除 `GATES["done"]` 里两条旧规则：`evidence/review/sign-final.md` 的 `glob_has_files` 与 `content_match(conclusion:)`。
2. 把 `decision_signoff` 规则改成哨兵路径 `DECISION_SIGNOFF_RULE_TARGET = ""` 并**无条件执行**：分支内删掉 `if full_path.is_file():` 守卫，直接 `failures.extend(_decision_signoff_problems(key_dir))`。
3. 删除 `DECISION_SCOPE_MARKER` 常量与 `:343` 的循环级 disable 短路（旧规则删掉后它成为死代码）。
4. 在 `_decision_signoff_disabled` 之后新增 `DECISION_ARCHIVE_REL`、`_matches_key`、`_key_has_decide_rows`（纯标准库，`json`/`Path` 已导入），并在 `_decision_signoff_problems` 的 `disable` 判断之后、`sign = key_dir / ...` 之前插入 `if not _key_has_decide_rows(key_dir): return []`。
5. 判据：`row["kind"] == "decide"` 且（`row["key"] == key_dir.name` 或 `str` 型 `decision_id.endswith(":" + key)`）；**不排除 dp25**；`FileNotFoundError` → False，其它 `OSError`/`UnicodeDecodeError` → True（fail-loud）。
6. 空 key 保护：`if not key: return False`（仅后缀分支）；不做 `str()` 强转。
7. 跑 `python .agents/skills/agentic-task/install.py .` 刷新 `core/scripts`、`claude/scripts` 镜像与 `.claude/`。
8. 更新规则描述文案：删掉"仅当 key 目录存在 decision-scope.md 时生效"，改为"无条件执行；无 `kind=decide` 行或 `signoff: disable` → 跳过"。

## 写入允许面

- `.agents/skills/agentic-task/scripts/advance_phase.py`
- `.agents/skills/agentic-task/core/scripts/advance_phase.py`（`install.py` 生成）
- `.agents/skills/agentic-task/claude/scripts/advance_phase.py`（`install.py` 生成）
- `.claude/scripts/advance_phase.py`（`install.py` 生成）

## 写入禁止面

- `packages/multi-workers/**`（T-01 与 T-04 的写面）
- `packages/coding-agent/**`（T-03）
- `docs/**`（T-06）
- 任何 `test_advance_phase.py`（若需新增用例，写在 `report.md` 的"建议"里，由 PM 决定）

## 验收命令

```bash
python -c "import sys; sys.path.insert(0,'.agents/skills/agentic-task/scripts'); import advance_phase as a; print(a.DECISION_SIGNOFF_RULE_TARGET); print(any(r[1]=='glob_has_files' and r[0].endswith('sign-final.md') for r in a.GATES['done']))"
python -c "import hashlib,pathlib; f=[pathlib.Path(p) for p in ['.agents/skills/agentic-task/scripts/advance_phase.py','.agents/skills/agentic-task/core/scripts/advance_phase.py','.agents/skills/agentic-task/claude/scripts/advance_phase.py']]; print(len({hashlib.sha256(p.read_bytes()).hexdigest() for p in f}))"
```

期望：哨兵为空串；旧规则已消失（False）；三个镜像 sha 一致（1）。

## 改动历史

| date | change |
| --- | --- |
| 2026-10-22 | 卡片创建 |
