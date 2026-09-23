# Task T-6: 独立验证（逐 VC + 变异反例）

## 元信息
- Stage: 4（T-3/T-4/T-5 全部落地后）
- 依赖: T-1、T-2、T-3、T-4、T-5
- 风险: 中（会临时改动源文件再逐字节复原；必须串行、必须在无其他写者时执行）
- Agent: coding worker（工具面 `read/write/edit/bash/find/grep/ls`；**只允许写本任务自己的证据文件**，见约束）
- ac_refs: [AC-001..AC-011]
- vc_refs: [VC-001..VC-011]

## 目标

不信任何实现者/PM 的结论，独立重跑证据，并对三条核心守卫做**变异反例**（mutant 必须让对应测试变红），证明测试真的在测该行为。

## 交付物

`evidence/verify-independent-2026-09-23.md`（唯一允许写入的文件），必须包含：

1. **VC 逐条表**：VC-001~VC-011，每行给「判定命令原文 + 命令输出关键行（原文复制）+ PASS/FAIL/降级」。
   - VC-001/002/003/004/007：`node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-checkpoint-wiring.test.ts test/extensions/agent-team-loop-worker-progress.test.ts`（在 `packages/coding-agent`）。
   - VC-005/006：`node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-file-tool.test.ts`，并核对测试是否真的断言了 `rejects.toThrow`，以及是否存在「12 项反例里的每一项」的独立 case（逐项列出实际存在的 name）。
   - VC-008：`cd packages/multi-workers && python -m pytest -q -s test_autopilot_l0.py test_autopilot_dispatch.py test_rag_research.py test_mwpp_collection_parity.py`。
   - VC-009：`npm run check`（全量输出，不要 tail）+ 受影响测试与基线对比（89 项 = agent 13 + coding-agent 76；说明本 key 触达文件是否在基线清单内）。
   - VC-010：`rg -n 'progress\.md' packages/coding-agent/src packages/multi-workers --glob '!node_modules' --glob '!dist' --glob '!.agenticdoc'`，逐处判定「陈述是否仍成立」，并核对两包 CHANGELOG `[Unreleased]` 条目。
   - VC-011：读 T-5 的 `evidence/verify-run-2026-09-23.md`，核对其断言原文是否为本 key 真实产出的证据（不接受转述），并给出你自己的判定。
2. **变异反例（必须逐条做，每条给 sha256 前后一致证明）**：
   - M-1 放宽白名单：把 `worker-file-tool.ts` 的 `WORKER_FILE_NAME_RE` 改为 `/^.+\.md$/` → `agent-team-loop-worker-file-tool.test.ts` 必须红。记录失败用例名。
   - M-2 去掉角色判据：把 `worker-mode.ts` 中 `hasWriteTools` 的门禁去掉（无条件写机器行）→ `agent-team-loop-checkpoint-wiring.test.ts` 的 `type: coding` 用例必须红。记录失败用例名。
   - M-3 破坏 parity：把 `WORKER_FILE_TOOL` 加进 `TOOL_ALLOWLISTS` 的 `review` 条目（或加进 `WRITE_TOOLS`）→ Python parity（`test_autopilot_l0.py` 或 `test_mwpp_collection_parity.py`）必须红。记录失败用例名。
   - 每条：改前 `sha256`、改后跑命令的输出、复原后 `sha256` 与改前**逐字节相等**。**M-3 复原后必须再跑一遍 parity 证明回绿**。
   - 若某条变异**没能**让测试变红 → 判该 VC「证据不足」，写进报告的 `## 缺口` 段，不得改写为 PASS。
3. **缺口与残留**：列出你发现的任何「测试通过但行为可疑」处（如：窄工具不计 `writes` 导致只读角色 `risk` 偏高；`report.<slug>.md` 与 `report-<slug>.md` 双形式的必要性；机器行与自评行的交错顺序）。

## 约束

- **只允许写** `evidence/verify-independent-2026-09-23.md`；对源文件的修改只允许为上述变异的**临时**改动，且必须在同一任务内逐字节复原（报告里给 sha256 证据）。禁止提交、禁止 `git checkout`/`git stash`/`git restore`（会牵连其他会话的改动——复原请用手工反向 `edit`，或用 `git diff -- <file>` 核对后反向改回）。
- 禁止改测试文件来「适配」实现（若你认为测试断言错误，写进报告，不改）。
- 不改 `dist/**`、不改 Python、不重启 `mw serve`、不跑 `mw build`。
- 不运行 `./test.sh`（全量 vitest 含 e2e；用定向命令）。
- 不接受「实现者的 `[VERIFY]` 行」作为证据——必须自己重跑并给命令输出。

## 报告要求

最终消息第一行给单行判定（PASS / PASS-with-gaps / FAIL）；随后给 VC 逐条结论计数、三条变异各自的「红/未红」结论与失败用例名、复原 sha256 证据、以及缺口清单。
