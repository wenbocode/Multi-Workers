# W2：Python 侧 state 字段去缩写（重命名）

- type: coding
- owner key: mw-decision-substitution

## 上下文

用户审阅 `decide_registry.json` 后指出：`required_state_fields` 里的 `v`、`dp`、`scope.ext`、`progress.elapsed_min`
语义不明、是缩写，要求"字段都要简单好理解，不要缩写"。本卡负责 **Python 侧**（TS 侧由 W3 同时改，映射表一致）。

现状：

- 泛型 state 组装 `packages/multi-workers/decision_points.py:349 _state_builder`（`{"v": 1, "dp": dp_id}`）
- 必填字段表 `decision_points.py:872 REQUIRED_STATE_FIELDS`
- 其它读取/写入这些键的位置（`mw.py` 的 `_decide_run`、`decision_points.decide_for` 的 `_lookup`、报告/档案代码）
- 测试夹具：`test_decision_points.py:205`、`test_decide_report.py:124/140/179`、`test_decide_signoff.py:92`、
  `test_decide_dp_cli.py:727/745` 等

## 字段重命名映射（本次唯一口径，禁止自行发挥）

| 旧 | 新 | 说明 |
| --- | --- | --- |
| `v` | `schema_version` | 值从 `1` 升到 `2`（字段名变了就是新 schema） |
| `dp` | `decision_point` | 决策点 id |
| `scope.ext` | `scope.file_extensions` | 允许扩展名 |
| `progress.elapsed_min` | `progress.elapsed_minutes` | 已消耗分钟 |
| `progress.budget_min` | `progress.budget_minutes` | 预算分钟 |
| `key` | `key`（不改） | 与 `decisions.jsonl` 的 `key` 列保持一致，别改成 `agentic_key` |
| `risk_source` / `authority_tier` / `task_summary` / `phase` / `task_type` / `requested_type` / `questions_version` / `ambiguity.kind` / `ambiguity.question` / `local_candidates` | 不改 | 已经是完整词 |

同义清理：代码里 `qid` 仍是内部变量名，不用改；state 里的 `key` 在注释/文档里写成 "AgenticTask key"。


## 要求

1. 全仓 Python（`packages/multi-workers/`，含测试）把上表旧键改成新键，**不留兼容别名**（用户明确不要向后兼容）。
   `_state_builder` 产出的 state 变成 `{"schema_version": 2, "decision_point": dp_id, ...}`。
2. `REQUIRED_STATE_FIELDS` 的键名同步；`dp2-checkpoint-split` 的 `progress.elapsed_minutes` / `progress.budget_minutes`，
   `dp1-dispatch-type` 的 `scope.file_extensions` 必须一起改。
3. 任何对这些键做校验/兜底的地方（例如 `decide_for` 里检查 `state.get("dp")`、报告里读 state）同步改；
   用 `rg -n 'schema_version|decision_point|file_extensions|elapsed_minutes|budget_minutes'` 自查无遗漏。
4. 测试：所有夹具/断言改成新字段；`test_decision_points.py` 里若有"缺 `v` 就 input-incomplete"之类用例，改成缺 `schema_version`。
5. 不碰 `decisions.jsonl` 的档案字段（`key` 等列不动），也不改 `answers` 结构。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest -q test_decision_points.py test_decide_run_authority.py test_decide_report.py test_decide_signoff.py test_decide_dp_cli.py
python -m pytest -q test_decide.py test_decide_backends.py test_decide_archive.py
rg -n '"v": 1|"dp":|elapsed_min|budget_min|scope\.ext' --glob '*.py' . | wc -l
```

（最后一条应为 0；若有命中必须是无关的局部变量，逐条说明。）

## 写入允许面

- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/mw.py`
- `packages/multi-workers/decide_report.py`（如存在，读 state 的地方）
- `packages/multi-workers/test_decision_points.py`、`test_decide_run_authority.py`、`test_decide_report.py`、
  `test_decide_signoff.py`、`test_decide_dp_cli.py`、`test_decide_archive.py`、`test_decide_cli.py`

## 写入禁止面

- `packages/multi-workers/decision.py`（W1 在改）、`decision_backends.py`、`decide_registry.json`、`test_decide.py`
- `packages/coding-agent/**`（W3 在改）
- `.agenticdoc/**`、`.agents/**`、`.mw/**`、`docs/**`
- 禁止 `git` 写、`npm run check`、`npm run build`、`mw build --install`、全量 pytest、真实网络、`Set-Content`

## 交付格式

`report.md`：结论 / 落点（文件:行）/ 两条 pytest 原文 + rg 计数 / 改过的测试夹具清单 / 残留。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 必须与 W3 同步的映射表见上；TS 侧同名文件是 `triage-client.ts`（dp1）、`pm-orchestrator.ts`（dp2）、
  `worker-mode.ts`（dp3）、`decision-tool.ts`（通用 state 组装）、`ui-bridge.ts`（dp1 state 构造）
- 现有 `docs/decision-points.md` §2 的字段表是旧名，PM 之后统一改；你**不要**改 docs

## 改动历史

- 2026-10-21 建卡：用户要求 state 字段去缩写、语义直白。
