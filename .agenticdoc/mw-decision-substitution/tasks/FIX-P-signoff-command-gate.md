# FIX-P：签收 (a) 命令 + (b) 门禁（`mw decide sign` + done 门禁的 engine/N 校验）

- type: coding
- owner key: mw-decision-substitution

## 上下文

用户 2026-10-21 裁定：签收取向 = **(a) + (b)**。

- (a) 新增 `mw decide sign`：先打印本 key 的决策摘要，人只回 `continue|narrow|revoke`，命令生成
  `evidence/review/sign-final.md` 并写授权档案行；`N=0` 时必须显式 `--allow-empty`。
- (b) done 门禁收窄：`conclusion: continue` 时必须 `N≥1` 且**每一行**都来自真 jev
  （`transport=timi-decisions` / `model=jev-latest` / `confidence_source=api`）；`narrow`/`revoke` 不受此约束
  （减权，N=0 也允许）。

现状：`advance_phase.py` 的 `GATES["done"]` 已有两条签收检查（文件存在 + `conclusion:` 机器行），但对所有 key
无条件生效，且**不校验内容真伪**。本卡只加"条件生效 + 内容校验"，不改已有两条。

## 事实依据（不要重新设计）

- 权威档案：`.agenticdoc/_autopilot/decisions.jsonl`（`decide_archive`），每行有
  `seq`/`prev_sha`/`kind`/`decision_id`/`dp`/`key`/`mode`/`acted`/`escalated_reason`/`transport`/`model`/
  `confidence_source`/`available`/`answers`/`ts`。`key` 缺失时用 `decision_id` 的 `:<key>` 后缀匹配。
- 证据行 `.agenticdoc/_autopilot/triage-decisions.jsonl` **没有 `key` 字段**，不能用于按 key 归集——不要用它。
- 真 jev 的 engine 三元组：`transport="timi-decisions"`, `model="jev-latest"`, `confidence_source="api"`。

## 要求

**1. 新模块 `packages/multi-workers/decide_signoff.py`**（纯函数，无网络）

- `collect(project_dir, key) -> SignoffFacts`：读档案，按 `kind=="decide"` + key 归集；返回
  `rows`（计数行快照：`seq/dp/available/acted/mode/escalated_reason/transport/model/confidence_source/ts`）、
  `n_available`、`n_acted`、`n_escalated`、`engines`（三元组计数）、`sha256`（被计数行的规范 JSON 链哈希）、
  `chain_ok`（`seq` 从 1 连续 + `prev_sha` 闭合；链断则 `chain_ok=False`）。
- `verdict(facts, conclusion) -> (ok: bool, problems: list[str])`：
  - `conclusion=="continue"`：要求 `facts.n_available >= 1`、`facts.chain_ok`、且**所有**行的 engine 三元组等于真 jev；
    否则 problems 里逐条给可读原因（含 `N=0` / 链断 / 混引擎 + 那一行的 seq 与 engine）。
  - `narrow`/`revoke`：只要求 `chain_ok`（N 不限）。
- `render(facts, conclusion, reason, key, claim) -> str`：markdown，含
  `conclusion: <x>`（列 0、单独一行，门禁正则要求）、`counted_rows: N`、`rows_sha256: …`、
  `engine: timi-decisions/jev-latest/api`、按 dp 的计数表、被上抛行的 `escalated_reason` 分布、
  已开 P0 列表（读 `.mw/decide-points.json`，缺失则写 `none`）、`reason:`（无则 `-`）、`ts`、`claim`。
- `write_signoff(project_dir, key, text)`：写到 `evidence/review/sign-final.md`；**agent 会话内拒绝**
  （复用 `mw.py` 已有的 `dp apply` 会话检测，不要发明新判据）；父目录自动创建。

**2. CLI `mw decide sign`**（`mw.py`）

```
mw decide sign [--project DIR] [--conclusion continue|narrow|revoke] [--reason TEXT]
               [--allow-empty] [--dry-run] [--json]
```

- 不带 `--conclusion`：只打印摘要 + 机器行草稿（不写文件），exit 0。
- 带 `--conclusion`：先算 `verdict`；不通过 → stderr 打 problems、exit 2、**不写文件**。
- `N=0` 且 `conclusion=continue` 且无 `--allow-empty` → exit 2，提示"先跑出真实决策行，或改签 narrow/revoke"；
  带 `--allow-empty` 时文件里必须出现 `allow_empty: true` 与 `counted_rows: 0`。
- 写入成功后追加授权档案行（`kind="authority-change"`、`by="human:signoff-<conclusion>"`、
  `change="signoff"`、`prev_sha`/`config_sha_after` 走既有 `decide_archive` 接口）。
- `--json` 输出 `{conclusion, ok, problems, facts, path}`。

**3. done 门禁条件化 + 校验**（4 份 `advance_phase.py` 副本 + `.claude/scripts/advance_phase.py`，**保持 sha 一致**）

- 新增 check_type `decision_signoff`，加进 `GATES["done"]`，**仅当** key 目录存在 `decision-scope.md` 时生效
  （其它 key 零影响；本 key 由 PM 写该标记文件）。
- 校验内容：①文件存在；②`conclusion:` 行可解析；③`counted_rows:` 与 `rows_sha256:` 存在；
  ④用 `decide_signoff.collect` 重算并比对 sha（防止签名后档案被追加/篡改）；
  ⑤`conclusion=="continue"` 时跑 `verdict(...)`。
- 失败信息要指出具体原因（`N=0` / repo 引擎不符 / sha 不匹配 / 缺机器行）。
- 五份脚本文本必须逐字相同（除已有已知差异外），报告给 `sha256sum` 证明。

**4. 测试 `packages/multi-workers/test_decide_signoff.py`**（全新，hermetic）

至少 10 例：`continue` 且 N=0 → 拒；`continue` N=1 真 jev → 通过；`continue` 混一行 `llm-transitional` → 拒且
problems 指向该 seq；`continue` 链断 → 拒；`narrow`/`revoke` N=0 → 通过；`allow_empty` 只影响 `continue` 且文件带
`allow_empty: true`；`render` 的 `conclusion:` 行匹配 `(?m)^conclusion:\s*(continue|narrow|revoke)\s*$`；
`sha256` 决定性（同输入同值、增行变值）；`mw decide sign --json` 的键集合；agent 会话内写入被拒（用既有检测的
环境变量注入模拟）。

**5. 文档**：`packages/multi-workers/README.md` decide 小节加 `mw decide sign` 用法与 `decision-scope.md` 标记说明；
`docs/decision-substitution.md` §签收段补 (a)(b) 两段；`packages/multi-workers/CHANGELOG.md` `[Unreleased]/### Added`。

## 必做用例（验收命令）

```bash
cd packages/multi-workers
python -m pytest -q test_decide_signoff.py
python -m pytest -q test_decide_cli.py test_decide_backends.py test_decision_points.py
python mw.py decide sign --help
python -c "import decide_signoff as s; print(sorted(s.__all__))"
cd H:/git/Multi-Workers && python -c "from pathlib import Path; import hashlib; [print(hashlib.sha256(p.read_bytes()).hexdigest()[:12], p) for p in [Path('.agents/skills/agentic-task/scripts/advance_phase.py'), Path('.agents/skills/agentic-task/core/scripts/advance_phase.py'), Path('.agents/skills/agentic-task/claude/scripts/advance_phase.py'), Path('.claude/scripts/advance_phase.py')]]"
```

最后一条必须四行 sha 相同（第四份若无差异也相同）。

## 写入允许面

- `packages/multi-workers/decide_signoff.py`（新建）
- `packages/multi-workers/test_decide_signoff.py`（新建）
- `packages/multi-workers/mw.py`
- `packages/multi-workers/README.md`、`packages/multi-workers/CHANGELOG.md`
- `.agents/skills/agentic-task/scripts/advance_phase.py`
- `.agents/skills/agentic-task/core/scripts/advance_phase.py`
- `.agents/skills/agentic-task/claude/scripts/advance_phase.py`
- `.claude/scripts/advance_phase.py`
- `docs/decision-substitution.md`

## 写入禁止面

- `packages/multi-workers/decision.py`、`decision_backends.py`、`decision_points.py`、`decide_archive.py`（只读复用）
- `packages/multi-workers/test_decide*.py`（除新建的 `test_decide_signoff.py`）
- `packages/coding-agent/**`、`packages/ai/**`
- `.agenticdoc/**`（本卡要求 PM 自己写 `decision-scope.md`；worker 不许碰 key 目录）
- 禁止 `git` 写操作、`npm run check`、全量 pytest、真实网络调用、`Set-Content`

## 交付格式

`report.md`：结论 / 落点（文件:行）/ 五条验收输出原文（含四份 sha 对比）/ 残留 / 未覆盖面。
禁止声称"已在真 jev 上签收"——真跑由 PM 执行（本卡不联网）。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 真 jev 用例与全链路：`.agenticdoc/mw-decision-substitution/evidence/runs/jev-live-20261021/transcript.md`
- 资产锚点：`packages/multi-workers/decide_archive.py`（`append`/`iter_rows`/`prev_sha` 模式）、
  `mw.py` 的 `_decide_dp_apply`（会话检测 + 写 `.mw/decide-points.json` 的既有护栏）、
  `.agents/skills/agentic-task/core/scripts/advance_phase.py:41-113`（`GATES` + `check_gate`）、
  `:69-113`（done 段两条签收检查）、`decision.py:964-1010`（`_append_evidence` 档案字段）

## 改动历史

- 2026-10-21 建卡：用户裁定签收取向 = (a)+(b)；事实依据来自真 jev 用例与权威档案字段。
