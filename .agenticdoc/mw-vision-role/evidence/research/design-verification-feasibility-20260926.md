# 设计阶段验证可行性清单（RQ-D5 / mw-vision-role）

## TL;DR
- 17 条有效 AC 均可在现有设施内机械判定，**无需真实 LLM**：L0=2（AC-005/014）、L1=13、L2 真进程=1（AC-011）、流程证据 1（AC-012）。
- AC-006/007/008/016/017 的"真实派发路径"在 TS 侧只需 `dispatch_worker` 工具级用例（`agent-team-loop.test.ts` 的 `setupTool`/`setupCommand` + `fakeRegistry`）：它走生产 `planDispatchFrontmatter` 并真实写 `_workers.parallel`，**不需要 spawn worker 进程** → 归 L1，不是 L2。
- 三条硬约束（已实测）：TS `[VERIFY]` 必须 `process.stdout.write`（`console.log` 被 `silent:"passed-only"` 吞掉）；Python 必须 `-s` 或 `capsys.disabled()`；`npm run check` 是全仓 `--write`，共享工作区禁全量跑（P-017）。
- 唯一降级：AC-011 的"真进程退出码非零"与模型真实视觉能力无现成设施 → L1 判定 + 1 次人工真实派发（Q7）。

## 决策问题
- 每条 AC 的测试入口 / 命令 / 机读输出（`[VERIFY] key=value`）通道。
- 哪些 AC 只能 L1、哪些必须 L2；不可机械判定项的替身。
- Windows 89 基线噪声如何隔离与对比。

## 调研方法与出处
- 只读静态阅读 + 单文件最小验证（未跑全量、无真实 LLM、未改源码）。
- 实测：`python -m pytest test_mwpp_collection_parity.py -q -s` → `[VERIFY] VC-008 ... keys=10`；`vitest --run test/extensions/agent-team-loop-worker-progress.test.ts` → `[VERIFY] VC-001/VC-002` 可见；同法跑 `agent-team-loop-output.test.ts`（源用 `console.log`）→ **无** `[VERIFY]` 行（P-006 实证）。
- 出处：`AGENTS.md:35`、`test.sh`、`packages/coding-agent/vitest.config.ts`、`packages/multi-workers/pytest.ini`、`.agenticdoc/mw-worker-tree-kill/evidence/baseline/known-windows-env-baseline-2026-09-19.md`、既有测试源码（行号见下）。

## 发现

### Q1 测试入口与确切命令
- Python 根是 **`packages/multi-workers/`（不是 `test/`；`test/` 下仅 `test_target_baseline.py`）**，`pytest.ini` 定义 `addopts = -m "not e2e_real and not e2e_l2"`。
  - `cd packages/multi-workers; python -m pytest test_dispatch_models.py -q -s`
  - `cd packages/multi-workers; python -m pytest test/test_target_baseline.py -q -s`
  - L2（被 addopts 排除）：`python -m pytest test_autopilot_e2e.py -m e2e_l2 -q -s` 或 `python test_autopilot_e2e.py`
- TS 单文件（包根，AGENTS.md 规则）：
  - `cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts`
  - `cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/regressions/<name>.test.ts`
  - 新增回归落 `test/suite/regressions/<issue>-<slug>.test.ts`（需 issue 号）；本 key 无号 → 放 `test/extensions/` 或 `test/suite/` 主目录，勿造号。

### Q2 TS 机读通道与最小骨架
- 通道先例：`verify(line){process.stdout.write(line+"\n")}` → `agent-team-loop-checkpoint-wiring.test.ts:44-45,206`、`agent-team-loop-worker-progress.test.ts:27-28,122`、`agent-team-loop-pm-state-sync.test.ts:45-46,221`；直接写见 `agent-team-loop-phase-docs-gate.test.ts:167`。
- `console.log` 先例 `agent-team-loop-output.test.ts:117`：断言仍 `expect(...)`，但 passed-only 下不复现，不能当复验锚。
- 派发面最小骨架（扩 `agent-team-loop.test.ts:5041 fakeRegistry` / `:5062 setupTool`）：
```ts
function fakeRegistry(es: Array<{provider:string;id:string;input?:("text"|"image")[]}>): ModelRegistry {
  const ms = es as unknown as Model<any>[];
  return { getAll:()=>ms, find:(p:string,i:string)=>ms.find(m=>m.provider===p&&m.id===i) } as unknown as ModelRegistry;
}
// tool.execute("id", params, undefined, undefined, { ...fakeCmdCtx().ctx, modelRegistry: fakeRegistry([...]) })
```
- 真管线/faux：`createHarness({ models:[{id:"m",input:["text"]}], modelsJson:{...} })`（`test/suite/harness.ts`）；registry 来自 `createInMemoryModelRegistry`/`createModelRegistry`，`ExtensionContext.modelRegistry` 见 `core/extensions/types.ts:319`；faux `input` 见 `packages/ai/src/providers/faux.ts:44,482`。

### Q3 Python 机读通道与 fake 外部进程
- `print(f"[VERIFY] {tag}: ...", flush=True)` + `-s`：`test_autopilot_l0.py:71`、`test_autopilot_config_parity.py:321`；pytest 捕获内仍要出行用 `with capsys.disabled(): print(...)`（`test_autopilot_audit.py:151-153`）。运行说明先例 `test_mwpp_collection_parity.py:18`（`-q -s`）。
- fake 外部进程：`test_serve_doctor.py:74 _FakeProc` + `monkeypatch.setattr(mw.subprocess,"Popen",...)`（`:220`）；`shutil.which` 桩 `:96`；真 CLI 子进程 `test_mw_autopilot_cli.py:92 _run_cli`、`test_serve_doctor.py:403 _run_doctor`。
- P-006 既有规避范式即上述两条（`capsys.disabled()` / `process.stdout.write`）：复验 grep 原始 stdout，不看退出码。

### Q4 逐条 AC 可判定性与层次
口径：L0=源码/常量 grep；L1=函数/工具级进程内（不 spawn 真 worker）；L2=真实派发路径 + 真实进程。
- AC-001 L1：`cmd_model` 直调 + `load_dispatch_config`（范式 `test_dispatch_models.py:430`）。
- AC-002 L1-CLI：argparse `choices`（`mw.py:5129`）；子进程 `mw model set visionx ...` 断 stderr 恰列 5 角色（`_run_cli` 范式）。
- AC-003 L1：`resolve_dispatch_model` 直调（`test_dispatch_models.py:230` 范式）。
- AC-004 L1：`resolveDispatchType`/`roleForTaskType`（`agent-team-loop.test.ts:5273-5278`）+ Python `TASK_TYPE_TO_ROLE` 字面量（`test_dispatch_models.py:142-155`）；**必须补 TS 半边 `roleForTaskType("vision")==="vision"`**（否则单边漂移无人发现）。
- AC-005 L0：`test_autopilot_l0.py:233`（逐元素同序）+ 重冻 `test_mwpp_collection_parity.py:34-62`。
- AC-006 L1：`setupTool`+`fakeRegistry(input:["text"])`：拒绝文案含 `images`/`mw model set vision`/`images: no`，任务目录未建、`_workers.parallel` 行数不变。
- AC-007 L1：同 `input:["image"]`：+1 行、task.md `^images: yes$`、头部 `type<phase<images<model` 严格顺序。
- AC-008 L1：`setupTool` 传 `undefined` / `codex_cli/` / `cli!=="pi"`：ok +1（对照 `agent-team-loop.test.ts:5232-5233`）。
- AC-009 L1：TS `planDispatchFrontmatter` 输出 `"type: coding\n"`；Python `render_task_md(images=None/'')` 与 git-HEAD 冻结渲染器逐字节；7 处 golden（`test_rag_phase.py:36-62` 等）保持绿。
- AC-010 L1(+CLI)：`_doctor_dispatch`/`format_doctor_text` 三态（issue/ok/skip、退出码 0）；probe 需模块级可 `monkeypatch.setattr`（同 `test_serve_doctor.py:96`），CLI 面 `_run_doctor`。
- AC-011 **L1 行为 + 人工 L2**：`workerModeActivate(fakePi)`，捕获其在 `session_start`（现 `worker-mode.ts:734`）注册的 handler，用 `ctx.model={id,input:["text"]}` 触发，`vi.spyOn(process,"exit")`；断 `worker.log` 含 `[IMAGE-CAP]`+模型 id、`output.md` 存在、`exit(1)`；控制组未声明 `images:` 正常。真进程退出码无设施 → 人工。
- AC-012 流程证据：非测试；保存 Q5 命令的原始输出。
- AC-013 L1：`cmd_model` 直调 + probe 桩（拒绝/通过/skip/`--force`）；`dispatch.yml` 前后 `read_bytes()` 逐字节比对。
- AC-014 L0：grep 四处文本 + **token 集合解析**（== `DISPATCHABLE_TYPES ∪ {"codex"}`），解析范式 `test_autopilot_l0.py:215`；`DISPATCHABLE_TYPES` 追加末尾（`:5143-5145` 子串约束）。
- AC-015 L1：Python show 逐角色行 + `mw_common` doctor 行；TS `formatDoctorReport` dispatch-row 用例；三态 `images=yes|no|unknown` 且退出码 0。
- AC-016 L1：`setupTool`：`vision` 已配置 + registry `input:["image"]` → task.md `model:` == vision 值 + `model-source: auto-route`；未配置/不支持 → 走 AC-006 拒绝；显式 `model:` 不改写。
- AC-017 L1：同 AC-016 参数化 `vision`/`review`，断言同构。
- AC-019 L1：`autopilot.dispatch.dispatch(task_type="vision",...)` + `REGISTRY["vision"].conductor_dispatchable is True` + 未知类型仍 `unknown-type`（`test_autopilot_dispatch.py:32` 键集）。
- AC-018 不适用（OBSOLETE）。

### Q5 Windows 基线噪声
- 无文件级清单：权威 `AGENTS.md:35`（89 = agent 13 + coding-agent 76，2026-09-10 分类）；分类明细（23 个失败文件类别）在 `.agenticdoc/mw-worker-tree-kill/evidence/baseline/known-windows-env-baseline-2026-09-19.md`。`test.sh`/CI 无此清单，CI 只在 ubuntu 跑。
- 隔离原则：先跑"本 key 触达面"，全绿即绿；必须全量时只比 **failed ≤ 76** 且失败文件不得落 `agent-team-loop*`/`shared/dispatch-models*`/`worker-mode*`。
  - `cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-checkpoint-wiring.test.ts test/suite/rag-required.test.ts 2>&1 | tee /tmp/mw-vision-ts.log`
  - `cd packages/multi-workers; python -m pytest test_dispatch_models.py test_autopilot_dispatch.py test_autopilot_l0.py test_mwpp_collection_parity.py test_serve_doctor.py -q -s 2>&1 | tee /tmp/mw-vision-py.log`

### Q6 `npm run check`
- 定义（`package.json:18`）：`biome check --write --error-on-warnings .`（**全仓写**）+ pinned-deps + ts-imports + shrinkwrap + install-lock + `tsgo --noEmit` + browser-smoke。
- 本 key 实际面：`biome.json files.includes` 只含 `packages/*/src|test/**/*.ts`（+session-backends/examples），**不含 `packages/multi-workers` 的 .py 与根 .ts**；tsgo include 同上 → Python 全不在 `npm run check` 内。
- 安全姿势（P-017，多 session 共享工作区）：`npx biome check --error-on-warnings packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test`（无 `--write`，已实测）→ `npx tsgo --noEmit` → `node scripts/check-ts-relative-imports.mjs`；全绿后再考虑全量 `npm run check`（会写他人文件时禁跑）。

### Q7 不可机械判定项与替身
- **AC-011 真实进程退出码**：无"真 pi 跑 worker-mode"基建（`rag-e2e-slow.test.ts` 是进程内 fake host）。替身：L1 exit 桩 + 1 次人工真实派发（存 `worker.log` 原文与退出码）。
- **模型真实视觉能力**：`pi --list-models` 只是 registry 元数据（`input` 列），不等于真能读图。`timi/deepseek-v4-flash-vision-exp` 的端到端视觉**不可机械判定**。替身：L1 用捕获表格 fixture 测解析 + 1 次人工同图派发。
- **AC-012 "测试实际跑过"**：流程证据，保留命令+输出。
- **AC-019 "重冻有据"**：机械只判相等，"有据"需人工 review diff。

## 结论 → 决策映射（建议 VC Layer 分配表）
| AC | Layer | 测试入口 | 命令 |
|---|---|---|---|
| AC-001 | L1 | `test_dispatch_models.py` | `python -m pytest test_dispatch_models.py -q -s` |
| AC-002 | L1-CLI | 扩 `test_dispatch_models.py`（借 `_run_cli` 范式） | `python -m pytest test_dispatch_models.py -q -s` |
| AC-003 | L1 | `test_dispatch_models.py` | `python -m pytest test_dispatch_models.py -q -s` |
| AC-004 | L1 | `test_dispatch_models.py` + `agent-team-loop.test.ts` | pytest + `vitest --run test/extensions/agent-team-loop.test.ts` |
| AC-005 | L0 | `test_autopilot_l0.py` + 重冻 `test_mwpp_collection_parity.py` | `python -m pytest test_autopilot_l0.py test_mwpp_collection_parity.py -q -s` |
| AC-006/007/008/016/017 | L1 | `test/extensions/agent-team-loop.test.ts` | `vitest --run test/extensions/agent-team-loop.test.ts` |
| AC-009 | L1 | 上述 + `test_rag_phase.py` + `agent-team-loop-baseline.test.ts` | pytest + vitest |
| AC-010/013/015 | L1(+CLI) | `test_serve_doctor.py` / `test_dispatch_models.py` / `agent-team-loop.test.ts` | pytest + vitest |
| AC-011 | L1 + 人工 L2 | 新建 `test/extensions/agent-team-loop-image-cap.test.ts` | `vitest --run test/extensions/agent-team-loop-image-cap.test.ts` |
| AC-014 | L0 | `test_autopilot_l0.py`（新 token-set 解析） | `python -m pytest test_autopilot_l0.py -q -s` |
| AC-019 | L1 | `test_autopilot_dispatch.py` | `python -m pytest test_autopilot_dispatch.py -q -s` |
| AC-012 | 证据 | — | 保存 Q5 命令原文输出 |

## [VERIFY] 行
[VERIFY] Q1-commands: pytest test_mwpp_collection_parity.py -q -s 与 vitest --run test/extensions/agent-team-loop-worker-progress.test.ts 实测通过
[VERIFY] Q2-channel: process.stdout.write 出 [VERIFY]（worker-progress），console.log 被 silent:"passed-only" 吞（output.test 无 [VERIFY]）
[VERIFY] Q3-channel: Python -s + flush=True 出行；pytest 捕获内用 capsys.disabled()
[VERIFY] Q6-check: biome includes 不含 packages/multi-workers；npx biome check --error-on-warnings <path> 无 --write 实测可用
[VERIFY] Q7-gap: AC-011 无真进程测试基建，需 L1 exit 桩 + 1 次人工真实派发