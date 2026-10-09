# T-19 证据刷新（T-17/T-18 修复后复验，回写 VC-012 判定）

- key: mw-vision-role · 波 5 · 独占写面：`.agenticdoc/mw-vision-role/evidence/runs/verify-mw-vision-role-20260926.md`（**只追加附录**）
- ac_refs: AC-012（并复核 AC-003/AC-007/AC-010/AC-015） · vc_refs: VC-003、VC-007、VC-012
- 依赖: T-17（tsgo 修复）、T-18（VC-003/007 证据）· 预估: 30-45min

## 背景

T-14 的证据文档里 `[VERIFY] VC-012: scoped_tests=green(baseline_red=2) check=FAILED` 是**当时未放行**的正确判定。之后两条阻塞已修：

| T-14 阻塞 | 处置 | 现状 |
|-----------|------|------|
| B1 `tsgo` 4×TS2741（`rag-required.test.ts`，`description` 必填） | **T-17** 修（`description?:` + `input.description ?? ""`） | PM 复验 `tsgo rc=0` |
| B2 全局 bundle 陈旧（`IMAGE-CAP` grep=0，遮蔽源 builtin） | **部署问题**，非代码缺陷；源 builtin `-ne` 真进程已验证 `[IMAGE-CAP]` → `rc=1` | 待用户决定 `/mw build` |
| 证据缺口 VC-003 / VC-007 | **T-18** 补（`test_dispatch_models.py` + `agent-team-loop-vision-gate.test.ts`） | PM 复验两条 `[VERIFY]` 行已在 |

## 要做的

**只追加**新章节到 `verify-mw-vision-role-20260926.md`（**不得**改写 T-14 的原文：那条 `check=FAILED` 是历史记录，保留并在附录里显式标注「已被 T-19 复验取代」），章节标题：

```
## 附录 A — T-17/T-18 修复后复验（2026-09-26，T-19）
```

内容要求（全部为**当次真实执行**的原始输出，禁止引用 worker 自述）：

1. `npx tsgo --noEmit`（仓库根）完整尾段 + 退出码（期望 rc=0、零输出）。
2. 触达面全量两套（输出**完整**，不 tail）：
   - `python -m pytest test_dispatch_models.py test_autopilot_l0.py test_autopilot_dispatch.py test_mwpp_collection_parity.py test_serve_doctor.py test_rag_phase.py test_autopilot_readcap_injection.py test_common.py -q -s`
   - `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-vision-gate.test.ts test/extensions/agent-team-loop-vision-autoroute.test.ts test/extensions/agent-team-loop-image-cap.test.ts`
   - 逐个红/绿判定：哪些是既有基线（E-04 `test_baseline_left_end_bound`、E-06 `test_existing_regression_files_untouched`）、哪些是本 key 引入（应为零）。`test_autopilot_dispatch.py` 的差异属 T-03 授权重冻（提交后消失），必须**明确标注**为「非本 key 的未提交工作区现象」。
3. 逐字贴 `[VERIFY] VC-003: source=config:vision task_override=task` 与 `[VERIFY] VC-007: queue_delta=1 images_line=yes order_ok=true`（用 `-s` / `process.stdout.write` 让它们真的出现在 stdout 里）。
4. `npx biome check --error-on-warnings` 覆盖四个改动源码文件（`ui-bridge.ts`、`pm-orchestrator.ts`、`shared/mw-runner.ts`、`shared/dispatch-models.ts`）+ 相关测试文件；若报 `autopilot/*.ts` 等**其他会话在飞的**文件，须显式标注为本 key 复验范围外的跨会话噪声。
5. 真实仓库端到端复跑（幂等、无副作用，用于 AC-010 / AC-015 的当期证据）：
   - `python mw.py model show --project H:/git/Multi-Workers` ⇒ 5 条角色行均含 `images=`
   - `python mw.py doctor --project H:/git/Multi-Workers --json` ⇒ `dispatch.images` 字段 + `images=no` suggestion 列表（期望 `[]`）+ `healthy` + 退出码
6. 汇总表：18 条活跃 AC 逐条给出「证据位置（本文件章节/`[VERIFY]` 行/原始输出）」与判定 `PASS`；AC-018 标注 OBSOLETE、不计入。
7. 新判定行（放在附录末尾，作为**取代**关系显式声明）：
   ```
   [VERIFY] VC-012: scoped_tests=green check=green   （取代 T-14 的 check=FAILED；T-17 修复 tsgo）
   ```
8. 「遗留」小节（至少含）：
   - B2 部署陈旧：全局 bundle 早于 T-09、运行中窗口仍用旧代码 ⇒ 需 `/mw build` + `/mw restart`（用户待定）；源 builtin 真进程 L2-1 已通过，证据在 T-14 原文。
   - `vision` 角色尚未在本仓库 `.mw/dispatch.yml` 配置（`mw model show` 显示 `(unset) → … [window]`）⇒ 真实视觉派发需用户先 `mw model set vision timi/deepseek-v4-flash-vision-exp`（L2-2 已用 `--model` 直跑验证过模型可用）。
   - 既有基线红（E-04/E-06）与本 key 无关，未修。

## 硬约束

- **只追加**证据文档；不改任何源码/测试（本卡不改 `packages/**`）。
- 不 commit、不 `git add`；不跑全量 vitest；不跑 `npm run build`/`mw build`；biome 不加 `--write`。
- **禁止用 PowerShell `Get-Content/Set-Content` 改文件**（用 `edit`/`write`）。

## 验收

上述命令的原始输出即证据；交付物 = 追加后的证据文档 + 你的 output.md 里贴的同一批原始输出。
