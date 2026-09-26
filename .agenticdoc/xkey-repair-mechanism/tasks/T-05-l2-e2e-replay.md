# T-05 L2/e2e 全链重放（W5 单写者，必须在 T-01+T-03 落地后）

key: `xkey-repair-mechanism` · 依赖: **T-01（xkey.py）+ T-03（挂载）+ T-06（apply/verify/close）均已落地** · 覆盖: VC-009,010

## 目标

两件事：① 合成 fixture 全链重放（VC-009）；② FM 语料 fixture 重放（VC-010，AC-010 用户裁定选路 **(b)**：前态由**逐字语料构造**，pre-fix 隔离副本仅作后备）。

## (1) 合成 fixture 全链（VC-009）

在 `packages/multi-workers/test_autopilot_e2e.py` 追加变体（不改既有用例语义）：

- 构造一棵最小 fixture 项目（`tmp_path`），含一个"冻结常量 + 断言"测试文件与一个"实测值 ≠ 冻结值"的红；
- **提案文件由测试直接注入**（T-08 的自动派发侧另卡并行，不作为本卡前提；测试不依赖真实派发）；
- 走链路：L3 below（带**完整机器行登记**）→ 账本建行 + 工单 → 抬 `xkey-authorize` gate → **stub 人工追认**（直接改 gate 文件为 approved，即可，因为 AC-004 的拦截在 TS 层，Python 侧不受影响）→ 提案 + 边界校验 → 应用 → 验证 subprocess（用 fixture 自己的 `pytest` 命令，落 `xkey_verify_cmd`）→ 证据包 → 闭合；
- 断言：fixture 冻结断言红数 **1→0**；工单状态序列覆盖 `detected → ticketed → approved → applied → verified → closed`；账本该行 `status == closed`（VC-007 顺带覆盖）。

## (2) FM 语料 fixture 重放（VC-010）

- **FM 工作树只读**：`E:\CLI_workspace\FeatureMigrator` 任何文件不得改动（只读引用语料）。
- 逐字语料锚点（引用时注明 file:line，注意**行号漂移**：`repair-r1-out-20260925-r3.txt` 是混合换行，Python 报 `:220`、PowerShell 报 `:209`——所以**锚字节 sha，不锚行号**，design D-011）：
  - `[VERIFY] REPAIR-R1-F1: cross_key_test=… owner=… handoff=registered not_fixed_by_this_key=True`（r3 `:220`）
  - `cli-run-state-and-events/l3-report.md:17/:58`（B 侧判定源形状：散文 F-1 + `owner=`，无 `(file,test_id)`）
  - `ap-cli-hitl-channel-l3-a1/report.md:68`（A 侧 K-1：只有 `PG-2 断言`，无 test_id/key 名）
  - `tests/test_hitl_channel.py:243-244`（`TOP_LEVEL_GROUPS`）+ `:268`（断言）
- 在 `tmp_path` 里重建：`TOP_LEVEL_GROUPS` 冻结 12 项、实测 13 项（`cli_groups=13`）⇒ 该断言红；冻结块定位走 `locate_frozen_block`（AST 路径，实测可解）；人工追认后应用 R1（**更新冻结期望块，不改断言逻辑**）⇒ `pytest tests/test_hitl_channel.py -q` 由 1 failed 转全绿、全量红数 1→0。
- 证据包必须含：old/new sha256、`relaxed_assertion=False`（"是否放宽断言=否"）、定向复跑命令与原始 stdout。
- 断言散文字形（K-1 型：无 test_id/owner）⇒ **只升级、零工单**（VC-002 的 L2 侧呼应）。

## 验收

- `cd packages/multi-workers && python -m pytest -q test_autopilot_e2e.py -s`：新用例全绿，既有用例不回归。
- 报告须含：改动的测试函数名清单、两条链路的真实输出（含 `[VERIFY]` 行或等价断言输出）、FM 工作树零改动的证明（`git -C E:\CLI_workspace\FeatureMigrator status --porcelain` 或等价只读核验）。

## 纪律

- **只写 `test_autopilot_e2e.py` +（必要时）`test_autopilot_conductor_exec.py`**（+ 报告）。不改实现、不改 conductor、不改 TS。
- 不跑全量套件（PM 在 T-06 负责）；不 commit；不写 FM 树。
