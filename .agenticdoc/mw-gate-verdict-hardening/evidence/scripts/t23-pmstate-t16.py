"""pm-state D-060 (T-16 done + closure verification + PM corrections) + process log."""

import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/pm-state.md")
lines = p.read_text(encoding="utf-8").splitlines()

d59 = next(i for i, l in enumerate(lines) if l.startswith("- D-059（2026-10-10 19:12）"))
lines.insert(
    d59 + 1,
    "- D-060（2026-10-10 19:25）：**T-16 完成 ⇒ 本 key 全部实现卡收口；PM 独立收口验证通过**。"
    "T-16 交付：`packages/multi-workers/CHANGELOG.md` +15、`packages/coding-agent/CHANGELOG.md` +13（**只进 `## [Unreleased]` 既有小节**，"
    "经 PM 核对两条 `### Fixed` 段确在 Unreleased 内、未触已发布小节）、`packages/multi-workers/README.md` +10（6 新配置键表 + G3 两个子命令小节，CRLF 保持）、"
    "`evidence/runs/verify-closure.md`、`evidence/runs/runtime-cutover-runbook.md`（234 行、30 条可复制命令、**只写不执行**）。"
    "**PM 独立复跑**（不复用 worker 输出）：Python 全量 = **2 failed / 1523 passed / 10 deselected**（两条红 = 基线同名同集合，"
    "`test_baseline_left_end_bound` / `test_true_below_without_resume_stays_below`，**新增红 = 0**；基线为 2 failed / 1431 passed）；"
    "TS 13 suite = **340 passed**；`npm run check` = **exit 0**（biome `No fixes applied`）。"
    "**PM 更正三处（写进 runbook 附录）**：① 全局 bundle 实为 **2026-10-10 11:40:42**、952,453 B、sha256 `52187720…`（非我先前记的 10:53:02）；"
    "② 实测该 bundle **含 `WORKER_COLS_MIN`/`WORKER_COLS_MAX`** ⇒ 它是 **post-`b8bc115ff`** 构建（有 7..9 容忍），但**不含本 key 任何标记**（8 个 marker 命中全 0）⇒ “本 key 改动全部未生效”的结论不变，表述已改准；"
    "③ `dist/extensions/agent-team-loop/` 是**目录**（`dist/extensions/agent-team-loop.js` 单文件确实不存在）——切换产物是安装副本 `~/.pi/agent/extensions/agent-team-loop.js`。"
    "另把 runbook §0.1 的“9 个窗口一定是 pre-fix 解析器”**降级为安全假设**（窗口启动后加载的安装副本历史内容不可考 ⇒ 一律重启，不据推断冒险）。"
    "**PM 直执文档整改**：本 key 的 22 条 CHANGELOG 条目原为中文正文，与两文件既有英文体例不一致 ⇒ 全部改写为英文（保留 `(mw-gate-verdict-hardening)` 归属与 `key: value` 事实），并去掉正文里的 `G4/G5/G6/IN-3` 内部编号。"
    "`./test.sh` 本机不可运行（bash → 无发行版 WSL，`wsl -l -v` rc=0xFFFFFFFF）⇒ 以 Python 全量 + 13 TS suite 为等价非 e2e 口径（已在 verify-closure.md 记录）。",
)

i = next(idx for idx, l in enumerate(lines) if l.startswith("- 10-10 19:15：**T-14 done + acked**"))
lines.insert(
    i + 1,
    "- 10-10 19:25：**T-16 done + acked ⇒ 实现卡全部收口**（CHANGELOG×2 / README / verify-closure / runtime-cutover-runbook；"
    "PM 独立复跑 Python 全量 2 failed(基线)/1523 passed、TS 340 passed、check exit 0；PM 更正 bundle 事实三处 + 把 22 条 CHANGELOG 正文改为英文体例）。"
    "记 D-060。下一步 = `advance_phase(verify)` + 质量门与 `achieved.md`；运行时切换仍待用户批准（runbook 已就绪）。",
)

na = next(i for i, l in enumerate(lines) if l.startswith("- Next Action:"))
lines[na] = (
    "- Next Action: **本 key 全部实现卡（T-01~T-23）已 done + acked，PM 独立收口验证通过**（Python 全量 2 failed/1523 passed，两条红=基线；"
    "TS 13 suite 340 passed；`npm run check` exit 0）。**下一动作**：① `advance_phase(verify)`（soft gate）；"
    "② 质量门复核（AC/VC 逐条核销：AC-014 的坐标与非空洞对照 + `verify-g5g6-tests.md` 映射表 + 各卡 `[VERIFY]`）；"
    "③ 写 `achieved.md`（含 `## 系统行为变化` 等 done 门要求的段落）后 `advance_phase(done)`。"
    "**唯一阻塞生效的待决项**：运行时切换（runbook `evidence/runs/runtime-cutover-runbook.md`，含 bundle sha256/9 个窗口 PID/回滚）——"
    "批准后 PM 直执 `mw build --install --allow-dirty` + 重启 launcher/serve + 一律重启 9 个 pre-11:40 窗口。"
    "**次待决**：R18 是否单独开卡；T-23 的 `--force` 语义是否认可。"
    "**已知残留**：R18（spawn 竞态不得静默判终态）、R19（错过 design/plan 边界的 key 无锚）、R20（`monitorCtx` 只由 `autoStartMonitor` 写）、"
    "R21（dist/bundle 未重建 ⇒ 本轮改动尚未生效）、D-038（`autopilot/dispatch.py` 未接 `run.json`）。"
)
upd = next(i for i, l in enumerate(lines) if l.startswith("- Updated:"))
lines[upd] = "- Updated: 2026-10-10 19:25"

p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("ok")
