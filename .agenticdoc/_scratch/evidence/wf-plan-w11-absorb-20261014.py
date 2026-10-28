"""Record plan.md section 7.6 = W-11 absorption + the two PM-direct test
expectation fixes this key caused + the PM containment probe measurement."""

import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\plan.md")

ADD = """
### 7.6 W-11 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核**：`write-face-runtime.test.ts` + `mwds-t03-bash-write-scope.test.ts` = **81 passed**（18 + 63；`mwds-t03` 由 `4 failed / 59 passed` 变 **0 failed / 63 passed**，旧口径断言是**重写加严**而非删除）；回归 `dispatch-card-envelope` + `mwds-t12-regression` + `mwds-t21-write-intent-soundness` = **57 passed**。
- **D-115 落地形状**：`parseTaskMd` 经 `shared/write-face.ts::parseWriteFace` 解析权威 `write_face:`（含 D-113 块列表）；`[WRITE_FACE]` 审计行只在**两载体同时存在**时产生（单载体 0 行，避免噪声）；安装条件 `hasWriteTools || isShellRole`（`roadmap-writer` 由零闸门变有 `write`/`edit` 闸、不装 bash 子判定）；writeless 逐字不变。
- **PM 独自查出并直接修掉的两条本 key 造成的红**（W-11 只报了一条同类，另一条它标为"既有红"但**实为 W-10 引入的旧口径断言**）：`test/suite/autopilot-read-scope.test.ts` 的 `expect(interceptorCount()).toBe(1)` 两处（`:752`/`:809`，`type: coding` + `read_scope`）——coding 现在同时注册读面与写面两个 `tool_call` 处理器，故为 2。按行号精确改（另一处 `:466` 是 research 型任务、仍应为 1；`:648` 为 0，均未动）并加注释说明第二个处理器的来源，复跑 **28 passed**。同一文件未被其它会话占用（`git status` 干净）。
- **PM 误拦探针（本卡最关键的风险自测，卡面未要求）**：临时 vitest 驱动（用完已删）以 `write_face: packages/coding-agent/src/**` 声明面直调 `checkBashWriteScopeTarget`（verbatim=true）：
  - 面内文件 `src/a.ts`、`src/sub/a.ts` → **allow**；**面内目录目标 `src/gen`（`rm -rf`/`find -delete` 家族）→ allow**；面根 `src` → allow。
  - 面外一层 `packages/coding-agent`、面外文件 `outside.ts`、`..` 逃逸 → 拦 `rule=write-scope detail=outside-declared-write-face`；仓外绝对路径 → 拦 `rule=scope`；glob 目标 `packages/coding-agent/*.ts` → fail-closed 拦。
  - 结论：**没有面内合法写被误拦**（尤其目录目标），方向正确；本 key 的"声明面真的拦得住"现在对 writable 角色成立。
- **残留（记，未开卡）**：
  1. 包含判定是**重叠**语义（单个具体目标时等于成员判定，正确）；glob 型目标只要求"有交集"而非"子集"，理论上可 fail-open，但生产路径上 glob 目标走 `allow-unknown`（只审计不拦），暴露面被限住——未来卡可显式裁定 subset vs overlap。
  2. `write_face:` 存在但被拒（present-but-refused）时运行期 fail-closed（非沙箱目标全拦），未单独加测试（派发层本会先拒该卡，运行期是兜底）。
  3. junction/cwd 与 base 的 realpath 归一未做（保持最小改动）；`mw-worktree-junction-guard` key 覆盖该族。
  4. `dist/**` 未重建（现场仍跑旧逻辑），B4/发布前需重建两侧。
- **本 key 造成的测试红已全部清零的账**：`mwds-t03` 4 条（W-11 重写）、`dispatch-card-injection` 1 条（PM 直接修）、`autopilot-read-scope` 2 条（PM 直接修）。其余红均为无关既有基线：`worker-file-tool` 2 条（`trace.log` 污染）、`mwds-t02` 1 条（别 key task book 语料漂移）、`mwds-t23` 1 条（别 session 的 dist bundle sha）、`test/extensions/agent-team-loop.test.ts` 1 条（T-17 anchor 指 `mw-guard-form-hardening`）。
"""

text = PLAN.read_text(encoding="utf-8")
if "### 7.6 W-11 终态吸收" not in text:
    PLAN.write_text(text.rstrip() + "\n" + ADD, encoding="utf-8")
    print("plan: appended 7.6")
else:
    print("plan: already has 7.6")
print(f"plan.md lines={len(PLAN.read_text(encoding='utf-8').splitlines())}")
