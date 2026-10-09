# Baseline（PASS 基线）：mw-vision-role

**生成**: 2026-09-26T18:45Z（QG 阶段补建，`workflow-quality-gate.md` Step 1 前置门禁要求 `evidence/baseline/` 非空）
**说明**: 本仓库当时有**多个 key 并发修改共享文件**（不得 stash / reset / 切分支），因此**无法**回到"本 key 改动之前的纯净工作区"重取基线。本文如实记录**实际用作归因依据的滚动基线**及其**已定位的成因**，而不是伪造一个"pristine baseline"。

## B-1 Python 套件（cwd `packages/multi-workers/`）

| 时点 | 命令范围 | 结果 | 用途 |
|------|---------|------|------|
| T-11 完成时（本 key 中段，E-08） | `test_dispatch_models.py test_common.py test_autopilot_dispatch.py test_mwpp_collection_parity.py test_autopilot_readcap_injection.py test_rag_phase.py` | **164 passed, 2 failed** | 确认已验证任务无交叉回归 |
| T-19 收口 | 上述 + `test_autopilot_l0.py test_serve_doctor.py`（8 文件） | **203 passed, 2 failed** | 本 key 最终判定 |

两红（两次均同）——**均与本 key 无关，且已定位**：

| 红项 | 成因 | 证据 |
|------|------|------|
| `test_autopilot_readcap_injection.py::test_baseline_left_end_bound`（E-04） | 该断言把冻结副本 sha256 与 `HEAD:packages/multi-workers/autopilot/dispatch.py` 比对；工作区里 `dispatch.py` 正被本 key（T-08 的 `render_task_md(images=...)`）**与其他会话**同时修改 ⇒ `219ed809…` ≠ `06d84b52…`。属"冻结副本 vs 脏工作区"的既有断言设计，对 HEAD 提交后成立。 | T-19 附录 §A.2.1；E-04 |
| `test_autopilot_readcap_injection.py::test_existing_regression_files_untouched`（E-06） | live 文件与 HEAD 逐字节比对；差异对象 = `test_autopilot_config.py`（**另一 key `mw-autopilot-slot-capacity` 在改**）与 `test_autopilot_dispatch.py`（**本 key T-03 授权重冻**）。提交后消失。 | T-19 附录 §A.2.1；E-06；T-03 卡 |

Windows 环境已知基线：`packages/agent` + `packages/coding-agent` 共 **89** 例环境性失败（13 + 76，Windows shell/path/watch 语义），见仓库 `AGENTS.md`。本 key 未跑全量 vitest，故不适用。

## B-2 TypeScript 套件（cwd `packages/coding-agent/`）

| 时点 | 范围 | 结果 |
|------|------|------|
| T-13 完成 | `agent-team-loop.test.ts` / `-vision-gate` / `-vision-autoroute` | 177 / 8 / 11 passed |
| T-19 收口 | 上述 + `-image-cap` | **201 passed, 0 failed** |
| T-16 独立复核 | 5 个文件（含 T-17 后新增） | **210 passed, 0 failed** |

## B-3 静态门禁

| 命令 | 收口时结果 |
|------|-----------|
| `npx tsgo --noEmit`（仓库根） | rc=0，零输出（T-17 修复前为 4×TS2741，见 T-14 §2.2） |
| `npx biome check --error-on-warnings <改动面>` | rc=0（scoped 9 文件 / 宽面 317 文件） |
| `npm run check`（字面） | **未按字面执行**：其首步 `biome check --write .` 会改写并发会话在飞文件 ⇒ 只读组件逐条跑绿（见 QG 报告 N-1） |

## B-4 真实进程基线（L2）

| 场景 | 基线观察 | 时点 |
|------|---------|------|
| worker `images: yes` + 纯文本模型（源 builtin，`-ne`） | `[IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes`、`rc=1`、`trace.log` 有 `[ERROR]` 行 | T-14 §5.3 |
| 同上，但走全局陈旧 bundle | **不触发**（`rc=0`）—— `bundle.stale=true`，生产/活窗口路径待 `/mw build` 后复验 | T-14 §5.2（B2 遗留） |
| 真实视觉 round-trip（`timi/deepseek-v4-flash-vision-exp`） | 64×64 纯红 PNG ⇒ 回答 `red square`；session JSONL 含 `"type":"image"` + base64 | T-14 §6（L2-2） |
| 本仓库真实 `mw model show` / `mw doctor --json` | 5 条角色行带 `images=`；`dispatch.images` 全角色；`images=no` suggestion `[]`；`healthy=true`；rc=0 | E-10 / E-11 / T-19 §A.5 |
