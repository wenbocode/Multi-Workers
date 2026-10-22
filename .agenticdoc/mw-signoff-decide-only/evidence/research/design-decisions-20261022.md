# design 证据：四个取舍与它们的来源

- date: 2026-10-22
- key: mw-signoff-decide-only
- 来源：`evidence/research/spec-gate-structure-20261022.md`（RQ2）、`spec-signoff-faces-20261022.md`（RQ1）、`spec-archive-scan-20261022.md`（RQ4）、PM 直接复核的行号。

## D-1 判据取 raw `kind=decide` 行（含 dp25），不取 `collect().rows`

实测（RQ4 §2、§6）：

| key | raw decide | collect().rows |
| --- | ---: | ---: |
| claim-driven-review | 1 | 1 |
| mw-decision-dashboard | 1 | 1 |
| mw-decision-substitution | 4 | 2 |
| mw-signoff-per-key | 2 | 0 |
| mw-usage-monitor | 2 | 0 |

若取 `collect().rows`：`mw-signoff-per-key` / `mw-usage-monitor` 从"需签收"变成"跳过"，两份已存在的合法签收文件不再被校验；且 `verdict()` 的 `"N=0 + continue"` 分支在门禁上不可达（RQ2 §5.1 的 `test_gate_blocks_continue_with_n_zero` 会失效）。

取 raw：5 个 key 都需签收，其中 2 个 `counted_rows: 0` 的文件仍能通过 sha 重算（`collect()` 一致地排除 dp25），`verdict(continue, N=0)` 仍可触发。

代价：签收动作本身会追加一条 dp25 `kind=decide` 行，于是"要求"可以被签收自身建立。可接受——文件缺失时重签一次即可，且不需要人。

## D-2 删掉两条无条件旧规则，而不是给它们加条件

`advance_phase.py:107-121` 的 `glob_has_files` 与 `content_match(conclusion:)` 对**所有** key 生效，`decision-scope.md` 只影响内容重算那一层（RQ4 §6 实测：77 个 key 里 74 个当前就被"缺 sign-final.md"拦）。

因此 AC-001（零决策行 → 不要求文件）在保留旧规则时不可达。选择删除旧规则、把"存在性 + 机器行 + 重算 + verdict"全部下沉到 `decision_signoff`，而不是给旧规则加 `kind=decide` 前置条件：后者会留下三套判据（存在性、机器行、内容），条件重复且容易再次漂移。

框架自带 `test_advance_phase.py` 的 done 夹具只写文件、不断言缺失（`:48`、`:417`），删规则不会红。

## D-3 廉价判据必须在导入之前

`_load_decide_signoff`（`advance_phase.py:307`）在导入失败时返回 `None`，调用方直接产出 `SIGNOFF: cannot import decide_signoff` 硬失败。门禁改为无条件执行后，没有 `packages/multi-workers` 的项目会集体变红。

因此 `_key_has_decide_rows` 用纯标准库实现（`json` + `Path`，两者文件头已导入），并在 `disable` 判断之后、文件存在性之前返回。RQ2 用 `%TEMP%` 副本实跑的行为矩阵（A/B/C/D/E/F/G/H 八场景）验证了该位置的早退效果。

## D-4 只收窄写面词表，读面保留四个值

`decide_signoff.py:103`（写/渲染）与 `decision_history.py:713`（读/解析）是两套独立词表（RQ1 §2、§5）。收窄写面到 `("auto-decide",)` 后：

- `decision_history.py:2149` 仍接受 `cli`/`tui`/`auto-llm`，历史签收不会被判 `unknown signed_via`；
- `human_basis` 分支（`:1772`）保留，`test_decision_history.py:818` 起的 `cli` 夹具继续成立；
- 删除 `AUTO_SIGNED_VIA` 时 `mw.py:1854` 的 `AGENT_SESSION_ENV_VARS` 必须保留（模块级初始化 `_DP_AGENT_ENV_VARS`），否则 CLI 导入即崩。

## 未决（不阻塞本 key）

- `Trigger.key` 默认 `""`（`decision_points.py:229`）+ `_validate_row` 接受空串（`decide_archive.py:395`）→ 无 key 的 decide 行对所有真实 key 不可见。今天 0 实例，记录待后续 key。
- `mw decide dp apply` 仍在 agent 会话内拒绝；它与签收是两条不同的写面，本 key 不改。
