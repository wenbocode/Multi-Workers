# T-14 验证收口与证据账本

- key: mw-vision-role · 波 4 · 独占写面：`evidence/runs/`（新建证据文档）
- ac_refs: AC-012 · vc_refs: VC-012
- 依赖: T-01…T-13 全部 · 预估: 60-90min

## 目标

按 `evidence-requirement.md` 逐 AC/VC 取原始证据，并核销两条无法机械判定的项。

## 步骤

1. 跑触达面全量（输出**完整留存**，不 tail、不裁剪）：
   ```bash
   cd packages/multi-workers
   python -m pytest test_dispatch_models.py test_autopilot_l0.py test_autopilot_dispatch.py test_mwpp_collection_parity.py test_serve_doctor.py test_rag_phase.py test_autopilot_readcap_injection.py test_common.py -q -s 2>&1 | tee /tmp/mw-vision-py.log
   cd ../../packages/coding-agent
   node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-vision-gate.test.ts test/extensions/agent-team-loop-vision-autoroute.test.ts test/extensions/agent-team-loop-image-cap.test.ts 2>&1 | tee /tmp/mw-vision-ts.log
   ```
2. 静态检查（**不跑**全仓 `npm run check`，P-017 会 `--write` 他人文件）：
   ```bash
   npx biome check --error-on-warnings packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test
   npx tsgo --noEmit
   ```
3. 基线对照：只允许既有红（`test_autopilot_readcap_injection.py::test_baseline_left_end_bound` 等）；若跑全量，判据 `failed <= 76` 且 `agent-team-loop*`/`worker-mode*`/`dispatch-models*` 零失败。
4. **人工 L2-1**（真进程兜底，**零 token**：`process.exit(1)` 发生在首轮前）：
   - 建临时工程 `$T=…/Temp/l2a`，在其中创建 `.agenticdoc/l2k/workers/l2t/task.md`，frontmatter 含 `type: coding`、`phase: 1`、**`images: yes`**，正文任意一行（工作区可写区，不要动本仓库 `.agenticdoc/`）。
   - 用纯文本模型真跑一次 pi 的 worker 模式（扩展是 bundled，任意目录都加载；`PI_WORKER_TASK` 一设即进 worker 模式）：
     ```bash
     cd "$T"
     PI_WORKER_TASK="$T/.agenticdoc/l2k/workers/l2t/task.md" \
       bash H:/git/Multi-Workers/pi-test.sh --model timi/deepseek-v4.1-flash -p "say ok"; echo "rc=$?"
     ```
   - 期望：输出/日志出现 `[IMAGE-CAP] model=timi/deepseek-v4.1-flash provider=… task=l2t declared=images:yes`，进程 **非零退出**，且同目录 `worker.log` / `trace.log` / `output.md` 均写入。证据 = 原始输出 + `worker.log` 原文 + `rc`。
5. **人工 L2-2**（真实视觉）：生成一张**内容确定**的小 png（如纯红方块，或红底 + 蓝方块；用 Python stdlib `struct`+`zlib` 手写 PNG，别引三方依赖），然后：
   ```bash
   cd H:/git/Multi-Workers
   bash pi-test.sh --model timi/deepseek-v4-flash-vision-exp -p "Read the image <abs path> with the read tool. Reply exactly two words: <颜色> <形状>."
   ```
   - 期望 ①（行为）：回答里出现正确的颜色/形状（说明模型真看到了像素，而不是在猜）；
   - 期望 ②（机制）：该次会话的 session JSONL（`~/.pi/agent/sessions/**` 最新一个）里能 grep 到**图片内容块**（`"type":"image"` / base64 `data:image/png` 一类），而**不是** `[Current model does not support images` 降级行。证据 = JSONL grep 到的行（base64 截断）+ 回答原文。
   - 若 timi 侧报错/无凭证/模型不可用 ⇒ **如实记为验证阻塞并上报**（禁止改用其他 provider 凑数、禁止编造）。
6. 写 `evidence/runs/verify-mw-vision-role-20260926.md`：逐 AC 贴 `[VERIFY]` 原始行 + 上述两条人工证据 + 基线对照结论 + 已知遗留。
7. 非空洞对照抽查：至少对 VC-006 / VC-008 / VC-009 / VC-011 各做一次"还原缺陷 ⇒ 变红"复现并记录。

## 验收命令

见步骤 1/2（命令原文与输出即为证据）。

## 证据格式

`[VERIFY] VC-012: scoped_tests=green check=green`

## 交付

`evidence/runs/verify-mw-vision-role-20260926.md`（含全部原始输出与两条人工证据）。若任一 AC 无法核销，写清缺失项与判定（禁止空断言通过，P-016）。

## PM 已备上下文

- E-10（真实仓库端到端）：`mw model show` 5 行均带 `images=`；`mw doctor --json` 的 `dispatch.images` 全角色齐全 + `healthy=true` + `rc=0`。
- E-11 + T-15：doctor 的 image suggestion 已收窄到 `vision` 角色（真实仓库实测由 4 条 → `[]`）。
- 触达面基线（E-08）：`164 passed / 2 failed`（两红均为基线噪声）；T-12 后 `test_dispatch_models.py + test_serve_doctor.py` = 80 passed。
