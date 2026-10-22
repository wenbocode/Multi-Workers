# D-CFG：把 24 个决策点落成一份框架可读的固定配置

- type: coding
- owner key: mw-decision-substitution

## 上下文

用户要求：dp 清单不能只是说明文档，要落成一份**固定配置，后续给框架可读**。当前状态：24 个 dp 只在
`packages/multi-workers/decision_points.py` 的 `DP_REGISTRY` 里是代码常量；人只能读 Python；
`.mw/decide-points.json` 是**授权表**（tier/enabled/mode/note，人来写，机器禁写），不能当注册表快照用。

事实来源（本卡直接读，别猜）：

- 注册表：`packages/multi-workers/decision_points.py` 的 `DP_REGISTRY`；`DecisionPoint` 字段：
  `id/tier/default_enabled/default_mode/questions/build_state/executor/questions_version/description/p0_consequences`。
- 必需 state 字段：`decision_points.py:872 REQUIRED_STATE_FIELDS`（只有 dp1/dp2/dp3 有条目）。
- 接线事实（已由四份 research 证据采集，逐 dp 带 path:line）：
  - `.agenticdoc/mw-decision-substitution/evidence/research/dp-inventory-A-20261021.md`（dp1..dp6，dp1/dp2/dp3 已接线）
  - `.agenticdoc/mw-decision-substitution/evidence/research/dp-inventory-B-20261021.md`（dp7..dp12，全未接线）
  - `.agenticdoc/mw-decision-substitution/evidence/research/dp-inventory-C-20261021.md`（dp13..dp18，全未接线）
  - `.agenticdoc/mw-decision-substitution/evidence/research/dp-inventory-D-20261021.md`（dp19..dp24，全未接线）
- `mw decide dp` 子命令在 `packages/multi-workers/mw.py`（`list/show/on/off/set/refresh/check/apply`），
  新增的 `export` 要挂在同一层，argparse 在 `mw.py:9xxx` 的 `decide dp` 段落附近。

## 要求

### 1. 生成器

`packages/multi-workers/decision_points.py` 新增 `registry_snapshot() -> dict`，纯函数、不读写文件：

```python
{
  "schema": 1,
  "generated_from": "decision_points.DP_REGISTRY",
  "question_types": ["choice", "noul", "score", "box"],
  "points": [
    {
      "id": "dp3-worker-clarify",
      "tier": "P2",
      "default_enabled": True,
      "default_mode": "auto",
      "description": "…",
      "questions_version": "q-fcbd3847",
      "p0_consequences": None,          # P0 才有文本
      "required_state_fields": ["v", "dp", ...],   # 来自 REQUIRED_STATE_FIELDS，缺省 []
      "executor": "wired" | "unwired" | "none",    # _unwired_executor → unwired；None → none；其它 → wired
      "questions": [
        {"id": "answerable", "type": "noul", "instructions": "…", "criteria": {"true": "...", "false": "..."}},
        {"id": "candidate", "type": "choice", "instructions": "…", "dynamic_choices": "…"},
        {"id": "answer_kind", "type": "choice", "instructions": "…", "choices": ["fact","intent","reuse"], "labels": {…}}
      ]
    }
  ]
}
```

字段顺序稳定（`sort_keys=True` 或显式顺序），`ensure_ascii=False`，2 空格缩进，文件末尾一个换行 —— 生成结果必须可字节比较。

### 2. 固定配置文件 `packages/multi-workers/decide_registry.json`

- 由 `registry_snapshot()` 生成，外加**手工维护的一节** `wiring`（每 dp 一条，从四份证据文件抄 path:line）：

  ```json
  "wiring": {
    "dp3-worker-clarify": {"wired": true, "trigger": "packages/coding-agent/src/.../worker/worker-mode.ts:3903",
                           "adopted_at": "packages/coding-agent/src/.../worker/worker-mode.ts:3753",
                           "note": "settle exitCode===2 唯一插入点；答案本地生成后 followUp 注入"}
  }
  ```

- **重新生成时 `wiring` 必须被保留**（`--write` 读旧文件、只替换 `points` 及其它生成字段），否则手写内容会丢。
- 覆盖全部 24 个 dp，一个不能少；未接线的写 `{"wired": false, "trigger": null, "adopted_at": null, "note": "…替代机制…"}`。

### 3. CLI

```
mw decide dp export [--project DIR] [--json] [--write]
```

- 默认（无 `--json`/`--write`）：打印一屏汇总（`id｜tier｜enabled默认｜executor｜wired｜questions_version`）。
- `--json`：整份快照打到 stdout（含 `wiring`）。
- `--write`：重写 `packages/multi-workers/decide_registry.json`（路径相对本包目录，不随 `--project` 变），
  打印 `wrote <path> (24 points, 3 wired)`。
- **严禁**读写 `.mw/decide-points.json`（那是授权表，机器禁写）。

### 4. 漂移守卫测试 `packages/multi-workers/test_decide_registry_export.py`

1. 磁盘上的 `decide_registry.json` 与 `registry_snapshot()` + 现文件的 `wiring` 重新生成结果**逐字节相同**（漂移即失败，
   提示跑 `mw decide dp export --write`）。
2. 24 个 dp 全在，id 集合 == `{p.id for p in DP_REGISTRY}`。
3. 每个 `wiring` 条目：字段齐全；`wired=true` 时 `trigger`/`adopted_at` 形如 `<path>:<line>`，把 path 部分拼到仓库根能
   找到真实文件，且 line ≤ 文件行数；`wired=false` 时两者为 null。
4. `questions_version` 与 `DecisionPoint.questions_version` 一致；`required_state_fields` 与 `REQUIRED_STATE_FIELDS` 一致。
5. `executor` 三分法与运行时一致：`_unwired_executor` 的执行器 → `unwired`。

### 5. CHANGELOG

`packages/multi-workers/CHANGELOG.md` 的 `[Unreleased] / ### Added` 追加一条（英文，一句话讲清：注册表导出成
`decide_registry.json`，`mw decide dp export [--json|--write]`，wiring 手工维护、重生成保留，漂移测试锁定）。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest -q test_decide_registry_export.py test_decide_dp_cli.py
python mw.py decide dp export --json | python -c "import json,sys; d=json.load(sys.stdin); print(len(d['points']), sum(1 for w in d['wiring'].values() if w['wired']))"
```

（第二条应打印 `24 3`。）

## 写入允许面

- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/mw.py`
- `packages/multi-workers/decide_registry.json`（新建）
- `packages/multi-workers/test_decide_registry_export.py`（新建）
- `packages/multi-workers/CHANGELOG.md`

## 写入禁止面

- `packages/multi-workers/decision.py`（另一张卡在改）、`decision_backends.py`、`decide_signoff.py`
- 其它 `test_decide_*.py`、`.mw/**`（尤其 `.mw/decide-points.json`）、`packages/ai/**`、`packages/coding-agent/**`、
  `.agenticdoc/**`（证据文件只读）
- 禁止 `git` 写操作、`npm run check`、`npm run build`、`mw build --install`、全量 pytest、真实网络调用、`Set-Content`

## 交付格式

`report.md`：结论 / 落点（文件:行）/ 三条验收输出原文 / `decide_registry.json` 的 size 与 24 条 dp 的 executor 分布
（wired/unwired/none 各几个）/ 残留。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 已接线事实（必须与配置一致）：dp1 `ui-bridge.ts:1730`，采纳 `ui-bridge.ts:281`；dp2 `pm-orchestrator.ts:2602`，
  采纳 `pm-orchestrator.ts:2620`；dp3 `worker-mode.ts:3903`，采纳 `worker-mode.ts:3753`
- 只注册未接线：dp7/dp9 有占位执行器（act 必抛 over-authority），dp21/dp22/dp23 是 `_unwired_executor`，
  其余（dp4/dp5/dp6/dp8/dp10..dp20/dp24 中除上述）`executor=None`
- 读参考：`docs/decision-substitution.md`、`mw.py` 的 `_dp_list/_dp_set` 实现风格（输出格式照抄它的克制程度）

## 改动历史

- 2026-10-21 建卡：用户要求 dp 清单落成框架可读的固定配置。
