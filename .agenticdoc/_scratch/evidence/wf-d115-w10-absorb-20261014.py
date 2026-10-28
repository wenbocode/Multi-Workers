"""Record design.md ruling D-115 (carrier convergence, AC-011) + plan.md section 7.5
(W-10 absorption) for the mw-write-face-guard key."""

import pathlib

DESIGN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\design.md")
PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\plan.md")

DESIGN_ADD = """
- **D-115（载体收敛：`write_face:` 为唯一权威 allow 载体，PM 裁定，AC-011）**：B2 落地后实测出集成漏洞——PM 通道渲染的是 `write_face:`，而运行期闸门只读 `write_scope:`，于是 writable 角色的声明面在运行期**完全失效**（只剩默认面 + deny 红线）。裁定：
  1. **`write_face:`（task.md 头，由卡 envelope 的「写入允许面」经同一渲染器生成）是唯一权威的 allow 载体**；两条派发通道共用它。
  2. **`write_scope:`（W1）= legacy 载体**：只对 **writeless 角色**（research）仍作声明面，逐字保持既有行为；writable 角色在**存在** `write_face:` 时以 `write_face:` 为准。
  3. 两者**同时存在且不等**时取**交集**（fail-closed，D-006 家族）并写一条审计行——交集使 legacy 载体只能收窄、不能放宽，也不允许出现两个载体给出两个不同允许集而无痕。
  4. writable 角色**没有** `write_face:`（存量卡未迁移）时回落到 `write_scope:`（只读兼容）；`write_face:` 的**生产端不再新增**（PM/conductor 渲染器已是唯一生产端，legacy 载体自然排空）。
  5. **不得新增第五个载体**。W2 gate v2 的 `write_scope`（异语义 `blast_radius`）与 W4 `mw-write-surface` marker 各自保持既有行为并**标注为异语义/仅标记**，不参与 allow 判定。
  6. **闸门安装条件补洞**：守卫必须覆盖"有 `write`/`edit` 工具"的角色（`hasWriteTools || isShellRole`），而不是只覆盖 shell 角色——`roadmap-writer` 这类 writable 但无 bash 的角色今天完全没有运行期闸门（W-10 残留 R3）；bash 子判定仍只在角色确有 bash 时启用。
  7. 书面口径变化（W-10 残留 R2）：`mwds-t03` 的 VC-024「coding/repair/vision 不装闸」与「summary 只给 writeless 角色」是 D-007 明确反转的**旧口径断言**，必须按新语义重写（"有闸且不误拦合法写"/"每个 shell 角色各一行 summary"），**不得删除或放宽**。
"""

PLAN_ADD = """
### 7.5 W-10 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核**：`test/suite/write-face-runtime.test.ts` = **9 passed**；`mwds-t12-regression` + `dispatch-card-envelope` + `mwds-t21-write-intent-soundness` = **57 passed**（11 + 33 + 13，无回归）；`mwds-t03` = **4 failed / 59 passed**，4 条红经我逐条核对**全部是旧口径断言**（3× `VC-024: <coding|repair|vision> registers no write-scope guard`、1× `the summary is written once at recordEnd and only for the writeless guard role`）——D-007 明确反转该口径，属**预期内**，已裁定由 `wfg-i11-carrier-convergence` 重写（D-115 第 7 条）。
- **PM 自核「记账面未动」**：`git diff -U0 worker-mode.ts | rg 'tool_execution_start|tool_execution_end|READ_TOOLS|WRITE_TOOLS|pendingBashWrites|appendWriteFileEvent|appendToolError'` 只命中一行**新增注释** ⇒ 断言成立。
- **PM 自核的关键设计缺口（R1，本次最重要的发现）**：B1 渲染 `write_face:`（PM 侧 `ui-bridge.ts:2092` 渲染、`:2273` 调用），而 B2 运行期货仍只读 `meta.writeScope`（`worker-mode.ts:434-441` 被本卡列为"复用/不改"）⇒ **真实 writable 卡的声明面在运行期失效**（落默认面 = 工作树根，越出 `write_face:` 不会被拦）。PM 裁定 D-115（载体收敛）并派 `wfg-i11-carrier-convergence` 收口。
- **R3（writable 无 bash 角色零闸门）**：`roadmap-writer` 无 bash ⇒ `isShellRole` 为假 ⇒ 不装闸。已并入 D-115 第 6 条（安装条件改 `hasWriteTools || isShellRole`）与本卡。
- **R4/R5/R6 接受**：P1「miss 优先于误拦」的有意漏面（`-` 头重定向目标、here-string 宽松闭合、`allow-unknown` 放行）已由新测试锁定；`mwds-t02` 1 条 red 是别 key 的 task book 引起的语料漂移（`wjg-qg-evidence-closure` 指向 `mw-worktree-junction-guard` 的证据文件）；`worker-file-tool` 2 条为既有 `trace.log` 基线。
- **R7/R8 未验证（记录）**：`dist/**` 未重建（现场仍跑旧逻辑）；无真实 provider 端到端（判定经 handler 直调 + 纯函数复算）。
"""

for path, add, marker in (
    (DESIGN, DESIGN_ADD, "D-115（载体收敛"),
    (PLAN, PLAN_ADD, "### 7.5 W-10 终态吸收"),
):
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        path.write_text(text.rstrip() + "\n" + add, encoding="utf-8")
        print(f"{path.name}: appended")
    else:
        print(f"{path.name}: already recorded")
