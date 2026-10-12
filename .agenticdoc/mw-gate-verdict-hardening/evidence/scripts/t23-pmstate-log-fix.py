"""Fix the pm-state Process Log: move a misplaced entry, relabel drifted clocks, add anchors."""

import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/pm-state.md")
lines = p.read_text(encoding="utf-8").splitlines()

# 1. remove the process-log line that landed inside the decisions section (D-052/D-053 area)
misplaced = [i for i, l in enumerate(lines) if l.startswith("- 10-10 18:33：**T-10 done + acked**")]
assert len(misplaced) == 1, misplaced
del lines[misplaced[0]]

# 2. relabel the drifted wall clocks (counter drift; anchored on worker dir mtimes)
relabel = {
    "- 10-10 20:05：**T-03 done + acked**": "- 10-10 18:10：**T-03 done + acked**",
    "- 10-10 20:15：**T-02 done + acked**": "- 10-10 18:12：**T-02 done + acked**",
    "- 10-10 20:25：**T-01 done + acked**": "- 10-10 18:15：**T-01 done + acked**（同时刻 T-05 也已 done：TS 镜像 43/43）",
    "- 10-10 20:35：**T-04 done + acked**": "- 10-10 18:17：**T-04 done + acked**",
    "- 10-10 20:45：**T-09 done + acked**": "- 10-10 18:20：**T-09 done + acked**",
    "- 10-10 18:24：**假 failed 事件**": "- 10-10 18:22：**假 failed 事件**",
}
for i, line in enumerate(lines):
    for old, new in relabel.items():
        if line.startswith(old):
            lines[i] = new + line[len(old):]
            break

# 3. append the three missing entries, chronologically after the 18:22 one
anchor = next(
    i for i, l in enumerate(lines) if l.startswith("- 10-10 18:22：**假 failed 事件**")
)
tail = lines[anchor].split("据此派 **T-13（G4 帧自证/降级帧）**；在跑 = T-10/T-13。")[0]
lines[anchor] = tail + "据此派 **T-13**。"

new_entries = [
    "- 10-10 18:26：**T-06 done + acked**（新 `test_autopilot_l3_aborted.py` 20 tests / 643 行 / 27 KB；PM 亲跑 **20 passed**，无外部绝对路径，断言走 `_l3_round_verdict`/`conductor.tick` 真实路径）。",
    "- 10-10 18:29：**T-07 done + acked**（`conductor.py` 累计 +276/-26；提醒块 `:2448-2560`；`tick` 第 2b 步调用 `:2577`（enabled/paused 之后、goal 检测之前）；新 suite **12 passed**；三组对照真跑转红。PM 追加核验：ledger 行键集与 T-09 读取端一致）。",
    "- 10-10 18:32：**T-10 + T-13 done + acked**（T-10：done 前守卫是 `_done_transaction` 第一检查 `:2244`、`contract-refused`+`contract-unauthorized`、`authorizes: []` 物化 `:2849`、三处 prompt 逐字；PM 亲跑 5 文件 = 2 failed/115 passed，两红 = T-14 计数锁。T-13：`collectedAtMs`/`tickCount`/`STALE PANEL`/降级帧（首 tick 即失败边界已覆盖），未新增写路径、未扩写 `worker-store.ts`；PM 亲跑 2 文件 = **64 passed**。**`npm run check` exit 0 且零 rewrite**）。**R3/D-009 门禁现场放行**（`mw.py` clean；`mw_common.py` 378+46 全属本 key）⇒ 派 **T-11**。记 D-053。",
]
lines[anchor + 1 : anchor + 1] = new_entries

# 4. footnote about the earlier clock drift, right under the Process Log header
hdr = next(i for i, l in enumerate(lines) if l.startswith("## 7. Process Log"))
note = (
    "> **时间标注更正（2026-10-10 18:35）**：本日志 10-10 部分早期条目（标注 17:30 / 18:30 / 19:30 / 19:45 / 20:05~20:45）"
    "是在一个**漂移的计时计数器**上写的，与真实墙钟不符，已在下方逐条更正为机器锚点时间。"
    "可用于校准的机器锚点：波 0 五卡派发 `_workers.parallel` 的 `dispatched_at` = `2026-10-10T10:09:08Z`（本地 **18:09:08**）；"
    "worker 目录 mtime：T-01 **18:15:21**、T-09 **18:19:58**、T-08 **18:22:21**、T-10 **18:31:47**、T-13 **18:32:28**。"
    "**T-20/T-21（标注 18:30 / 19:30）未逐一重标**，其真实时刻应从各自 worker 目录/证据文件 mtime 反查。"
)
lines.insert(hdr + 1, note)

p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("ok: moved 1 misplaced line, relabelled", len(relabel), "entries, added", len(new_entries), "entries")
for i, l in enumerate(lines):
    if l.startswith("- 10-10 18:2") or l.startswith("- 10-10 18:3") or l.startswith("- 10-10 18:1"):
        print(" ", l[:70])
