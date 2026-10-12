# T-23: G3 锚点建立（`contract-freeze` CLI + 两处接受边界自动锚）

- 波次: **3** · 依赖: T-04, T-10, T-11（均已 done）
- 写面（独占）:
  - `packages/multi-workers/mw.py`（新增 `_ap_contract_freeze` + argparse 子命令）
  - `packages/multi-workers/autopilot/conductor.py`（新增 `_freeze_contract_first_sight` + `tick` 内一处调用）
  - `packages/multi-workers/autopilot/timeline.py`（`EVENT_TYPES` += `contract-frozen`，**只加这一个名字**）
  - 新测试 `packages/multi-workers/test_autopilot_contract_freeze.py`（新文件）
- AC: AC-025 · VC: VC-047
- 基线: `776b82d7f`
- **落地理由（T-11 交接 R1，PM 判定）**：design D-015 / §4.5 要求 `mw autopilot contract-freeze` 与两处接受边界冻结，但**无卡承载**；
  PM 实测全仓零 sidecar ⇒ `no_anchor` ⇒ **AC-011 在生产中永不触发**（G3 休眠）。本卡把它接活。

## 目标

让 AC/VC 文本身份锚**由框架自身在正确的时机建立**：新 key 在 design / plan 边界自动锚（幂等一次写），
历史 key 不回溯、只能由人显式补锚；两个入口都不重写已存在的块。

## 交付物

1. **自动锚（`conductor.py`）**
   - 新函数 `_freeze_contract_first_sight(project_root, st, cfg) -> None`（或等价命名），在 `tick` 内**一处**调用
     （位置自行选安全点：必须在 enabled/paused 检查之后，且**不得**插进 L3 段与 done 事务段中间——
     建议紧邻既有 `_remind_pending_gates` 那一步）。
   - 语义（逐条照做，AC-025）：
     - 对每个 key：`phase == "design"` 且 `read_freeze(key_dir)` 的 `spec` 块为空 ⇒ 冻结 AC 块；
       `phase == "plan"` 且 `design` 块为空 ⇒ 冻结 VC 块；
     - **合并写**：把已有 sidecar 的块原样保留，只放新块，**一次** `write_freeze`（不得两次写、不得重写非空块）；
     - **不回溯**：`phase ∈ {tasks, execute, verify, done, ""}` ⇒ 不动；无 `spec.md`/`design.md` ⇒ 不动（不得抛错）；
     - **留痕**：一次 `st.timeline.append("contract-frozen", key=key, detail=..., data={"block": "ac"|"vc", "phase": ..., "source": "conductor-first-sight", "freeze_rel": ..., "ids": [...]})`；
       `ids` = 该块冻结的编号列表（排序）；
     - **never raises**：任何 OSError/解析失败都吞掉并把降级信息写进 `detail`（本函数**不得**让 tick 崩）。
   - 复用 `autopilot.contract_guard`（`read_freeze`/`build_freeze`/`write_freeze`/`freeze_path`）与既有 AC/VC 抽取；
     **不得**自己再写一份 sha 抽取逻辑。
2. **显式 CLI（`mw.py`）**
   - `mw autopilot contract-freeze --project <dir> --key <k> [--block ac|vc|all] [--force] [--json]`
     （默认 `--block all`；`--key` 必填——不得批量写全项目）。
   - 行为：缺块 ⇒ 补齐；已存在且**未变更**的块 ⇒ 默认**跳过**并在输出里说明；已**变更**的块 ⇒ 默认拒绝（exit 1，打印被替换的 id 列表），
     仅 `--force` 重冻（`--force` 时打印"被替换 id"与新旧 sha）。
   - `--json`：`{"key","freeze_rel","blocks":{"ac":{"status":"written|skipped|unchanged|refused","ids":[...]}, "vc":{...}}}`，稳定排序。
   - 写路径沿用 `write_freeze`（tmp+replace 原子）；**不要**加新锁（sidecar 是 per-key 文件，不共享队列）；
     但同一 key 的并发写必须在回执里说明（建议：写前重读一次，块非空则跳过 ⇒ 天然幂等）。
3. **事件词汇（`timeline.py`）**：`EVENT_TYPES` 加 `"contract-frozen"`（**只加这一个**）。TS 镜像与计数锁归 T-14，**别碰 TS**。
4. **测试（新文件 `test_autopilot_contract_freeze.py`）**：覆盖 VC-047 全部子句（见 spec AC-025 的反向用例 + 下面对照组）。

## 契约（不得重定义）

- **无锚 ⇒ 放行**（D-015 `[REVISED]`）：缺失/损坏 sidecar 一律 `no_anchor=True` ⇒ 不拒绝；只有"有锚 + 文本变更 + 无批准"才拒绝。**不要**把导语改成 fail-closed。
- `contract_guard.py` / `gates.py` / `mw_common.py` **不动**（T-04/T-10/T-11 的写面；`mw_common` 的 doctor 段已由 T-11 落地）。
- 不得改 `tick` 的既有语义顺序（尤其 L3 段与 done 事务段），只在选定位置**插入**一次调用。
- 不得写任何真实项目的 `.agenticdoc/**/contract-freeze.json`（一律 tmp 目录）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_contract_freeze.py -q -p no:randomly`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_closure.py test_autopilot_contract_guard.py test_mw_autopilot_cli.py -q -p no:randomly`
  （预期：仅剩 `== 12` 计数锁红，它是 T-14 的；**不得**升级成更多红）
- `cd packages/multi-workers && python -X utf8 mw.py autopilot contract-freeze --project <tmp 项目> --key <tmp key> --json`

## 非空洞对照（必须真跑贴红/绿，并逐字节还原）

- **A**：摘掉 `tick` 里那次 `_freeze_contract_first_sight` 调用 ⇒ VC-047 的"sidecar 出现"断言必须转红。
- **B**：把"既有块非空即跳过"改成无条件重写 ⇒ 第二次 tick 的 **sha 不变**断言必须转红。
- **C**：删掉 `contract-frozen` 事件 ⇒ 留痕断言必须转红。
- **D**：`--force` 门禁：把"已变更块默认拒绝"改成默认覆盖 ⇒ CLI 用例必须转红。
- **E（真活端到端）**：tmp key 推进到 design ⇒ tick ⇒ 仅 AC 块；推进到 plan ⇒ tick ⇒ VC 块且 AC 块字节不变；
  改写一条 AC 文本 ⇒ `contract_guard.evaluate(...).ok is False` 且 `changed_ids` 含该 id（证明 T-10 的 done 守卫能据此拒绝）。

## 风险与注意

- **`conductor.py` 是同文件热点**（T-01→T-07→T-10 已落地）：开工前 `git diff --stat -- packages/multi-workers/autopilot/conductor.py` 确认只有前几卡的改动，且你的新增**不碰**L3 段（`:1556-1940` 附近）与 done 事务段（`_done_transaction`）。
- `tick` 会高频运行：本步必须是 **O(已锚则零写)**——已锚 key 只读一次 `read_freeze`，不做任何写与解析；避免每 tick 重读大文本。
- 只读面约束：本卡**不新增 doctor 输出**（T-11 已完成）；doctor 路径不得创建文件。
- 并发：T-12 正在改 TS（`status-model.ts`/`gate-writer.ts`/`console.ts`），与你零重叠——但**不要**碰 `status-model.ts`（T-14 要补的事件名也在那儿）。
- 硬规则：不 commit / 不 `git add -A` / 不 `git stash` / 不 `git reset` / 不 `git clean`；不碰 `.agenticdoc/_workers*`；不 kill 进程；
  不跑 `npm run build`/`npm test`/全量 vitest/`npm run check`。运行时是旧副本，终态回读不可信——只信自己跑出的输出。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/mwg-t23-g3-anchor/report.md`（含 `[VERIFY]` 命令原文与输出、五组对照的实际红/绿、`文件:行号` 坐标），写完**立刻**复制到 `evidence/runs/t-23-g3-anchor-report.md`。
