"""Generate evidence/quality-gate-report-20261010.md (PM-side closure/quality gate)."""

import pathlib
import re

ROOT = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening")
design = (ROOT / "design.md").read_text(encoding="utf-8")
spec = (ROOT / "spec.md").read_text(encoding="utf-8")
plan = (ROOT / "plan.md").read_text(encoding="utf-8")

# --- VC snippets: first occurrence of each id, cleaned + truncated ---
vc_text = {}
for line in design.splitlines():
    if not re.match(r"^VC-0\d\d:", line.strip()):
        continue
    for m in re.finditer(r"(VC-0\d\d)", line):
        vid = m.group(1)
        if vid in vc_text or vid == "VC-048":
            continue
        body = re.sub(r"[*`#]", "", line).strip()
        body = re.sub(r"\s+", " ", body)
        idx = body.find(vid)
        body = body[idx + len(vid):].lstrip("：:，, ")[:96]
        vc_text[vid] = body
vc_ids = [f"VC-{i:03d}" for i in range(1, 48)]
missing = [v for v in vc_ids if v not in vc_text]
# second pass: the G5/G6 block lists them as `- **VC-0NN**：...` bullets
if missing:
    for line in design.splitlines():
        for vid in missing:
            if f"**{vid}**" in line and vid not in vc_text:
                body = re.sub(r"[*`#]", "", line).strip()
                body = re.sub(r"\s+", " ", body)
                idx = body.find(vid)
                vc_text[vid] = body[idx + len(vid):].lstrip("：:，, ")[:96]
missing = [v for v in vc_ids if v not in vc_text]
assert not missing, missing

group = {
    "G1 (L3 流中止)": [f"VC-{i:03d}" for i in range(1, 7)],
    "G2 (闸门静默/提醒)": [f"VC-{i:03d}" for i in range(7, 12)],
    "G3 (授权范围/契约闸门)": [f"VC-{i:03d}" for i in range(12, 20)],
    "G4 (面板冻结/自证)": [f"VC-{i:03d}" for i in range(20, 24)],
}
for i in range(24, 48):
    group.setdefault("G5/G6 (队列完整性/派发隔离/运行身份) + AC-025", []).append(f"VC-{i:03d}")

evidence = {
    "G1 (L3 流中止)": "T-01 / T-06 → `evidence/runs/t-01-l3-aborted-report.md`、`t-06-l3-tests-report.md`；新测试 `packages/multi-workers/test_autopilot_l3_aborted.py`（20 例）",
    "G2 (闸门静默/提醒)": "T-07 / T-08 / T-09 → `t-07-gate-reminder-report.md`、`t-08-g2-surfaces`（73 passed，我复跑）、`t-09-pm-consumer-report.md`",
    "G3 (授权范围/契约闸门)": "T-04 / T-10 / T-11 / T-12 / T-14 → `t-04-contract-guard-report.md`、`t-10-g3-done-guard-report.md`、`t-11-g3-cli-doctor-report.md`、`t-12-g3-writer-g4-rearm-report.md`、`t-14-count-locks-report.md`",
    "G4 (面板冻结/自证)": "T-13 / T-12 → `t-13-g4-freshness-report.md`、`t-12-g3-writer-g4-rearm-report.md`（`autopilot-monitor.test.ts` VC-020/021/022 + VC-023）",
    "G5/G6 (队列完整性/派发隔离/运行身份) + AC-025": "T-15/T-17/T-18/T-19/T-20/T-21/T-22/T-23 → `t-15-t17-t19-report.md`、`t-18-queue-integrity-report.md`、`t-20-run-identity-report.md`、`t-21-integrity-report.md`、`t-22-crosskey-readonly-report.md`、`t-23-g3-anchor-report.md`；映射表 `evidence/runs/verify-g5g6-tests.md`",
}

AC_ROWS = [
    ("AC-001", "G1", "PASS", "T-01 `conductor.py:1649` 指纹分支在状态门 `:1651` **之前**；T-06 20 例（含逐字 marker 夹具）", "PM 复跑 5 文件 2 failed/115+（红=T-14 计数锁，已消）"),
    ("AC-002", "G1", "PASS", "T-01 `_l3_round_verdict` 三分支 + T-06 三类无有效裁决夹具", "`test_autopilot_l3_aborted.py` 断言走生产函数/`tick`"),
    ("AC-003", "G1", "PASS", "T-01 `loop=\"l3abort:<key>\"` 独立预算 + `l3_abort_retry_limit`（`config.py`，0..10，默认 1）", "T-02 范围校验 + T-14 语料 73 例"),
    ("AC-004", "G1", "PASS", "反向：无 `stream closed` 行 / `output.md` 合格 ⇒ 不判 aborted（T-06 N 组对照 X1 转红）", "T-06 `[VERIFY]`② 红集合与基线一致"),
    ("AC-005", "G2", "PASS", "T-07 `conductor.py:2475` `pending_gate_reminders` 纯判定 + `:2508` `_remind_pending_gates`，`tick` 第 2b 步 `:2577`", "新 suite `test_autopilot_gate_reminder.py` 12 passed"),
    ("AC-006", "G2", "PASS", "T-07 提醒计数入 ledger（`phase:\"remind\"`），已答 gate 不再提醒；T-09 读取端 `seq` 水位去重", "T-21 回放 + T-09 接缝核验（行键集一致）"),
    ("AC-007", "G2", "PASS", "T-07 只对 `status==pending` 生效（已答/终态 stage/无 gate 均不产事件）", "`test_autopilot_gate_reminder.py` 非空洞对照 3 组"),
    ("AC-008", "G2", "PASS", "T-08 `monitor.ts` snapshot 级 `blockedOnHuman`（`:184`，采集 `:364-369`，用 T-05 共享 `blockedOnHuman()`）+ 置顶 `BLOCKED_ON_HUMAN` 行（`:745-753`，受 `!tickStale` 门控）", "PM 复跑 73 passed，`VC-011: age_shown=true blocked_marker=true`"),
    ("AC-009", "G3", "PASS", "T-04 `authorizes` 进 `_JSON_LIST_FIELDS`（`gates.py:171`）+ 闭集 `AUTHORIZES_ACTIONS`（`:180`）；T-12 `gate-writer.ts` 唯一闭集声明 + `--authorizes` 参数面", "跨语言闭集 parity 用例（`VC-012: closed_set=2 listed_only=true`）"),
    ("AC-010", "G3", "PASS", "T-10 `_CONTRACT_CONSTRAINT`（`conductor.py:1459`）逐字拼进三处 prompt（`:1478-1479`/`:2459-2460`/`:2490-2491`）", "T-10 控制组（删一处 prompt 常量 ⇒ VC-013 红）"),
    ("AC-011", "G3", "PASS", "T-10 `_done_transaction` 的 `:2244` **第一个 check-before-write** 调 `contract_guard.evaluate`；不过 ⇒ `contract-refused` + `mark_stalled(contract-unauthorized)` + `return \"gated\"`", "T-10 控制组 + T-23 PM 端到端（`evaluate().ok=False`, `changed_ids=('AC-001',)`）"),
    ("AC-012", "G3", "PASS", "反向：自由文本 `note` 不作授权——判定只认 `authorizes` 字段 + freeze；T-10 不读 `gate.note`/`answered_by`", "T-10 VC-015 对照（pending/rejected/散文）转红"),
    ("AC-013", "G3", "PASS", "T-04 不改 `_REQUIRED_FIELDS`（仍 6）、不新增 v3；T-11 doctor 段只在有 sidecar 的 key 出现；历史 gate 全量 parse 成功", "PM 实测：真实仓库 `gates` 无 `contract_guard` 键、全仓 0 sidecar、`test_doctor_gates.py` 82 passed"),
    ("AC-014", "全部", "PASS", "每条机器判据附非空洞对照（见 §4 索引：7 个 `*-controls.ps1` 脚本 + 各卡 CF 组，全部实测转红并逐字节还原）", "本报告 §4"),
    ("AC-015", "G4", "PASS", "T-13 `MonitorSnapshot.collectedAtMs`/`tickCount` + 首行 `STALE PANEL (...)`（`PANEL_STALE_MISSED_CYCLES=3`）", "PM 复跑 `VC-020: stamp_advances=true stale_warned=true`"),
    ("AC-016", "G4", "PASS", "T-13 跟随 ≤2 周期（`MONITOR_INTERVAL_MS=4000` 未改）", "`VC-021: followed_within_cycles=2`"),
    ("AC-017", "G4", "PASS", "T-13 裸 catch 改为**产出降级帧**（上一帧 + `lastErrorAtMs` + 摘要），首 tick 即失败边界已注释+用例", "`VC-022: degraded_frame=true silent_frames=0`"),
    ("AC-018", "G4", "PASS", "T-12 `autoStartMonitor` ctx 变化 ⇒ 先 `stopMonitor` 再 start；`stopMonitor` 语义未动", "PM 复跑 `VC-023: rearmed=true panel_present=true`"),
    ("AC-019", "G6", "PASS", "T-19 `dispatchNewTasks(..., { scope:\"pm\", watchedKey })` 收窄 + `out-of-scope` 聚合告警（D-031）", "T-21 VC-034/035 + T-20 VC-046；PM 复跑 340 passed"),
    ("AC-020", "G5", "PASS", "T-17 严格有序判据：`unparsable>0` ⇒ 零派发 + 告警；空队列 + 终态证据 ⇒ 零派发；无证据 ⇒ 放行", "T-21 VC-027/028（含双向用例）"),
    ("AC-021", "G5", "PASS", "T-17 `dispatch_max_per_scan`（默认 3）+ T-18 `launcher_max_workers`（默认 8）+ `_workers.acked` 参与", "T-21 VC-029/030、T-18 VC-040/041；PM 实测 live `rows_total/non_terminal` 计数一致"),
    ("AC-022", "G6", "PASS", "T-20 `run-store.ts` + `worker-mode.ts` 自写 `run.json`（running/终态/心跳）+ launcher 只补 `lost` + 同 `task_key` 不再重跑（`supersedes` 指已终态旧目录）", "T-20 report（15+6+9+7 例）；PM 复跑 340 passed"),
    ("AC-023", "G5", "PASS", "T-15 读侧 `{rows, unparsable[], version}` + 回写槽位保留 + `# mw-queue:v2`；T-18 Python 三个写者槽位保留 + doctor 三判据", "T-21 回放（250 行 9 列夹具，sha `6c4f4dfc…`）+ T-18/−controls A–F"),
    ("AC-024", "G6", "PASS", "T-22 `ui-bridge.ts` `foreignLiveClaimRefusal` + `dispatch_worker`（显式 key）/`advance_phase` 先拒后动，返回 `[cross-key-read-only]`；读面零改动", "`t22-controls.ps1` 4 组全红 + 还原；`worker-crosskey-readonly.test.ts` 4 例"),
    ("AC-025", "G3", "PASS", "T-23 `conductor.py::_freeze_contract_first_sight`（`:2644`，调用点 tick step 2c `:2768`）+ `mw autopilot contract-freeze`（`mw.py:3977`）+ `timeline.py:110` 事件", "PM 独立端到端 `evidence/scripts/pm-g3-live-check.py`：自动锚/幂等字节不变/`evaluate.ok=False`/CLI `refused` + 真实仓库 0 sidecar"),
]

CONTROLS = [
    ("T-01", "3 组反事实（摘指纹分支 / 摘专用 label / 摘 mark_stalled 复算）", "`evidence/runs/t-01-l3-aborted-report.md`"),
    ("T-02", "语料反证（T-02 三键 0 命中 / T-18 三键各 6 命中）+ golden sha 重冻 `27b222b9…`", "`t-02-config-keys-report.md`"),
    ("T-03", "摘 `contract-refused` ⇒ 事件集合计数转红", "`t-03-event-names-report.md`"),
    ("T-04", "闭集/解析面/值校验反例 + R1 偏离裁决（`authorizes` 在 40 名单之外）", "`t-04-contract-guard-report.md`"),
    ("T-05", "TS 镜像两侧集合相等 + 配置 20 键", "`t-05-ts-mirror-report.md`"),
    ("T-06", "X1 反例（无 marker ⇒ 不判 aborted）转红", "`t-06-l3-tests-report.md`"),
    ("T-07", "3 组反事实（摘阈值分支 / 摘 ledger 写 / 摘已答过滤）", "`t-07-gate-reminder-report.md`"),
    ("T-08", "G2 呈现用例 + `!tickStale` 门控反向用例", "`autopilot-monitor.test.ts`（PM 复跑 73）"),
    ("T-09", "接缝核验（ledger 行键 ≡ 读取端键；`seq` 由共享写入器补）", "`t-09-pm-consumer-report.md`"),
    ("T-10", "3 组 CF：摘 done 检查 / 放宽批准判据 / 删 prompt 常量（逐字节还原）", "`t-10-g3-done-guard-report.md`"),
    ("T-11", "摘 doctor 段 ⇒ 3 例红；摘 CLI dispatch ⇒ 5 例红（还原）", "`t-11-g3-cli-doctor-report.md`"),
    ("T-12", "CF A（摘闭集校验）/ B（摘 JSON-list 项）/ C（摘 ctx 分支）/ D（摘缺失行拒绝）全红 + 还原", "`t-12-g3-writer-g4-rearm-report.md`"),
    ("T-13", "摘降级分支 / 摘 stale 计算 各转红 + 还原", "`t-13-g4-freshness-report.md`"),
    ("T-14", "A（`STALL_REASON_CODES`→12）/ B（摘语料 accept 例）/ C（摘 Python 事件名）/ D（摘 TS 事件名）全红", "`t-14-count-locks-report.md`"),
    ("T-15/T-17/T-19", "`evidence/scripts/t15-controls.ps1`（A 5 红 / B 1 红 / C 1 红）、`t17-controls.ps1`（5 组）、`t22-controls.ps1`（4 组）", "`t-15-t17-t19-report.md`、`t-22-crosskey-readonly-report.md`"),
    ("T-18", "`t18-controls.ps1` A–F 全红 + 还原（含 14→17 配置键与 doctor 三判据）", "`t-18-queue-integrity-report.md`"),
    ("T-20", "`t20-controls.ps1` A–G 全红 + 还原（其中控制 B 曾因**不承重**被替换为承重变异）", "`t-20-run-identity-report.md`"),
    ("T-21", "`t21-controls.ps1` A–E 全红 + 还原（8/9/10 列与旧 codec 丢行）", "`t-21-integrity-report.md`"),
    ("T-23", "A（摘 tick 调用）/ B（改非空块重写 ⇒ sha 断言红）/ C（删事件）/ D（改默认覆盖）/ E（真活端到端）", "`t-23-g3-anchor-report.md`"),
]

lines = []
w = lines.append
w("# quality-gate-report — mw-gate-verdict-hardening（2026-10-10）")
w("")
w("- key: `mw-gate-verdict-hardening` · phase: **verify** · 代码基线 `776b82d7f`（+ 本 key 未提交工作区改动）")
w("- 范围：G1 L3 流中止 / G2 闸门静默 / G3 授权范围与契约闸门 / G4 面板冻结 / G5 队列完整性 / G6 派发隔离与运行身份 + **AC-025 G3 锚点建立**")
w("- 规模：**25 AC / 47 VC**；实现卡 T-01…T-23（T-08b 为假 `failed` 引发的重复派发，人工终止）")
w("- 本报告由 PM 在 verify 阶段独立撰写；所有数字来自 **PM 本人复跑**或各卡回执中带 `文件:行号` 的实测，PM 未复用 worker 的总结作为证据。")
w("")
w("## 1. 收口验证（PM 独立复跑）")
w("")
w("| 命令 | 结果 | 与基线对照 |")
w("|---|---|---|")
w("| `cd packages/multi-workers && python -X utf8 -m pytest -q -p no:randomly` | **2 failed / 1523 passed / 10 deselected** | 基线 `verify-baseline.md` = 2 failed / 1431 passed；两条红**同名同集合**：`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`、`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` ⇒ **新增红 = 0** |")
w("| `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run <13 suites>` | **13 files / 340 tests passed** | 无基线红 |")
w("| `npm run check`（仓根） | **exit 0**，biome `Checked 1110 files … No fixes applied` | tsgo/pinned-deps/ts-imports/shrinkwrap/install-lock/browser-smoke 全过 |")
w("| `evidence/scripts/pm-g3-live-check.py`（PM 自写端到端） | 6 项全绿（见 AC-025 行） | — |")
w("| `./test.sh` | **本机不可运行**（`bash.exe` → WSL 且无已安装发行版，`wsl -l -v` rc=0xFFFFFFFF） | 以 Python 全量 + 13 TS suite 为等价非 e2e 口径（AGENTS.md） |")
w("")
w("## 2. AC 矩阵（25/25 PASS）")
w("")
w("| AC | 组 | 结论 | 实现落点（`文件:行号`／符号）| 判据与证据 |")
w("|---|---|---|---|---|")
for ac, grp, verdict, impl, ev in AC_ROWS:
    w(f"| **{ac}** | {grp} | **{verdict}** | {impl} | {ev} |")
w("")
w("## 3. VC 矩阵（47/47 PASS；判据全文见 `design.md`）")
w("")
w("> VC 的完整判据文本在 `design.md` §6 / §11.7 / §11.11；本表给出各自摘要与归属证据通道。")
w("")
w("| VC | 判据摘要 | 组 | 证据通道 |")
w("|---|---|---|---|")
for gname, ids in group.items():
    for vid in ids:
        w(f"| {vid} | {vc_text[vid]} | {gname} | {evidence[gname]} |")
w("")
w("## 4. 非空洞对照索引（AC-014）")
w("")
w("| 卡 | 对照 / 变异 | 证据 |")
w("|---|---|---|")
for card, ctrl, ev in CONTROLS:
    w(f"| {card} | {ctrl} | {ev} |")
w("")
w("## 5. 未验证 / 边界（诚实清单）")
w("")
w("1. **运行时尚未切换**：本轮全部 TS/扩展改动**未生效**。实测全局 bundle `~/.pi/agent/extensions/agent-team-loop.js` = 2026-10-10 11:40:42 / 952,453 B / sha256 `52187720D22D06DEE10FEE383981CD041FAD763BFB292B9B2BD7756D3A53FE0B`，"
    "含 `WORKER_COLS_MIN/MAX`（post-`b8bc115ff`）但**不含本 key 任何标记**（8 个 marker 命中均为 0）。⇒ 本报告结论均为**源码+测试级**，"
    "非“已在运行中观测”。切换步骤见 `evidence/runs/runtime-cutover-runbook.md`（+PM 复核附录），**待用户批准**。")
w("2. **9 个 pre-11:40 常驻窗口**：其加载的安装副本历史内容不可考 ⇒ runbook 已把“一定是 pre-fix 解析器”**降级为安全假设**，结论是“一律重启”。")
w("3. **两条基线红保持**（非本 key 引入，环境相关）：`test_baseline_left_end_bound`、`test_true_below_without_resume_stays_below`；本 key 未修，去向见 §6。")
w("4. **`./test.sh` 不可运行**（WSL 无发行版）⇒ 非 e2e 口径以 pytest 全量 + 13 TS suite 替代。")
w("5. **AC-011 的“生产可达性”依赖 AC-025 的锚点**：历史 key（无 sidecar）仍不受 G3 保护，这是 D-015 `[REVISED]` 的有意选择（否则与 AC-013 冲突）。")
w("6. **PM 直执的小改已复核**：`console.ts` 顶层 `USAGE`/文件头补 `--authorizes`（T-12 交接①）；22 条 CHANGELOG 正文由中文改写为英文体例；两者改后均复跑相关 suite + `npm run check` exit 0。")
w("")
w("## 6. 遗留与去向")
w("")
w("| 遗留 | 性质 | 去向 |")
w("|---|---|---|")
w("| **R21** dist/bundle 未重建 + 运行时未切换 | 交付缺口（非缺陷） | 用户批准后 PM 直执（runbook）；本 key `done` 时在 `achieved.md`「遗留」显式标注 |")
w("| **R18** spawn 竞态下“刚派发的行不得被静默判终态”无机器判据 | 新发现（假 `failed` 现场实证） | 待用户决定是否单开小卡；证据 `evidence/runs/t23-runtime-writeback-observation.md` §5 |")
w("| **R19** 错过 design/plan 边界的 key 无锚（不回溯） | 有意设计 | 显式 `mw autopilot contract-freeze`；doctor/CLI 可见“无 sidecar” |")
w("| **R20** `monitorCtx` 只由 `autoStartMonitor` 写 | 已知小瑕疵（最坏多一次无害 stop+start） | 接受不处理（T-12 回执 §6） |")
w("| **D-038** `autopilot/dispatch.py` 未接 `run.json` | 已知边界 | 记入本 key 残留；后续 key 或用户决定 |")
w("| 两条基线红 | 环境相关存量 | 不作为本 key 验收对象；如需修另开 key |")
w("")
w("## 7. 复现命令（最小集）")
w("")
w("```powershell")
w("cd H:/git/Multi-Workers/packages/multi-workers")
w("python -X utf8 -m pytest -q -p no:randomly            # 期望 2 failed(=基线) / 1523 passed")
w("cd H:/git/Multi-Workers")
w("npm run check                                          # 期望 exit 0")
w("cd H:/git/Multi-Workers/packages/coding-agent")
w("node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-store.test.ts test/suite/run-store.test.ts test/suite/worker-dispatch-guard.test.ts test/suite/worker-run-identity.test.ts test/suite/worker-crosskey-readonly.test.ts test/suite/autopilot-monitor.test.ts test/suite/autopilot-console.test.ts test/suite/autopilot-gate-presentation.test.ts test/suite/autopilot-event-parity.test.ts test/suite/autopilot-config-sync.test.ts test/suite/autopilot-config-parity.test.ts test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-pm-state-sync.test.ts")
w("python -X utf8 .agenticdoc/mw-gate-verdict-hardening/evidence/scripts/pm-g3-live-check.py   # G3 端到端")
w("```")
w("")
w("**结论：AC 25/25、VC 47/47 PASS（源码+测试级）；新增红 0；唯一交付缺口是运行时切换（R21，待用户批准）。**")

out = ROOT / "evidence" / "quality-gate-report-20261010.md"
out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("wrote", out, len(out.read_bytes()), "bytes")
