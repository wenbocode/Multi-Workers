"""Record plan.md sections 7.9 (W-14 absorption) and 7.10 (AC-006 gap + W-15)."""

import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\plan.md")

ADD = """
### 7.9 W-14 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑五条验收（全部与 worker 自报逐字一致）**：`write-face.test.ts` **113 passed**（基线 109）、`write-face-pm-gate.test.ts` **25 passed**（基线 22）、`write-face-e2e.test.ts` + `mwds-t03` **71 passed**、`npx tsgo --noEmit` exit 0、Python `test_write_face_e2e.py`+`test_write_face.py`+`test/test_write_face_dispatch.py` **166 passed**。
- **PM 读码核对（不采信自述）**：`pm/task-dispatcher.ts:442` `reason: parsed.detail === undefined ? parsed.code : \\`${parsed.code}: ${parsed.detail}\\``、`:438` detail 尾缀；算子 `shared/write-face.ts:54` `WRITE_FACE_EMPTY_DETAIL`、`:151` `readonly detail?: string`、`:629/:633` 拒绝时回填；两侧字面格式对得上（Python `write_face.py:654/668/674/685` 的 `f"entry {raw!r}"` / `f"deny entry {raw!r}"` vs TS 的 `entry '<raw>'` / `deny entry '<raw>'`，TS 注释显式引用了这两个 Python 行号）。⇒ AC-007 在 `reason` 字段上收口（空头 / 非法条目 / 逃逸三例两侧逐字节相等，`detail` 亦逐字节相等）。
- **两处有界差异（worker 主动报告 + 我确认其已被测试显式锁定，不是掩盖）**：
  1. **repr 引号风格**：条目原文含单引号、不含双引号时 Python `{raw!r}` 改用双引号包裹（`entry "x'y/**"`），TS 保持单引号（`entry 'x'y/**'`）；除 wrapper 外两串全同；测试 `write-face-pm-gate.test.ts:726` 用 `rawOf()` 断言**去掉 wrapper 后相等**。
  2. **D-112 单行引号逗号切分**：`write_face: 'a,b'` 时 TS `splitSingleLine` 先剥 wrapper 再按 `,` 切（raw=`a,b`）、Python 语法盲切（raw=`'a`）；`code` 两侧相同（`write-face-invalid-entry`）而 reason 的 raw 片段不同。这是**冻结的 D-112 解析语义的既有差异**，改它会变更判定（属另一 key 面），故只记录并断言（`:752`）。
  ⇒ PM 判定：两处都**接受**（不派卡）：字符串级边界，判据 `kind`/`code` 一致，且已显式锁在测试里；模拟 Python `repr` 的引号选择只会把展示层复杂度带进冻结语料算子（卡面明确禁止"对齐用格式转换"）。
- **新残留（PM 记录，不修）**：PM 审计行的前缀分隔符与 conductor 不同——conductor `_write_face_audit` 是 `"<task_key>: <code> <detail>"`（空格），PM `writeFaceRefusalDetail`（`pm-orchestrator.ts`，W-14 的禁止面）是 `"<task_key>: <reason>"` ⇒ `<task_key>: <code>: <detail>`。`reason` 本体已逐字节相等，且两条审计落在**不同文件/不同 schema**（timeline 事件 vs ledger 行），故接受为有界差异。
- **`it.skipIf(!pythonAvailable)` 的口径（PM 记录，接受）**：3 条跨通道对照是条件跳过（W-08 起既有惯例，该文件共 4 处这种守卫）；本机 Python 可用 ⇒ 25 passed **0 skipped**（实测）。PM 用**读码**独立佐证同一结论（两侧构造点字面一致），故 AC-007 的收口不依赖该守卫的运行时值。
- **未修**：`dist/**` 仍未重建（见 §7.8 B4 决定 2 与 `achieved.md` 遗留 1）。

### 7.10 PM 质量门前置扫描发现 AC-006 是真缺口 → 派 W-15（2026-10-14）

- **AC-014 复核通过**（PM 读码）：`autopilot/dispatch.py` 取锁 `:1435` → `task_dir.mkdir` `:1461` / `task_md.write_text` `:1462` → `upsert_worker_row` `:1478`，**全在锁内**；文件头注释 `:18-27` 明确记着"旧顺序在锁外写 task.md 会留下 check-then-act 孤儿"。⇒ AC-014 满足。
- **AC-006 是未实现的 AC（PM 实测）**：`mw_common.doctor_report`（`mw_common.py:4039-4091`）的 section 清单（service/proxy/queue/gates/dispatch/activation/worktree_links/conductor/rag/serve_code…）**没有写面容**；`_doctor_autopilot` 只读 timeline 的尾部水位；TS 侧唯一读 ledger 的 `readGateReminders`（`autopilot/status-model.ts:1212`）只接受 `phase === "remind"`（`:1232`）⇒ W-13 落的 `phase:"dispatch-alarm"`, `kind:"write-face-refusal"` 行**没有任何只读面消费**。反差点：`pm-orchestrator.ts:571` 的注释本来就写着这些行"对 humans、`mw doctor` 与后续消费者可见"——**设计意图在、实现没跟上**，这正是质量门要抓的那类缺口。
- **PM 已给出精确实现口径（读码核实，替 worker 消掉猜测空间）**：
  - conductor 事件名恰为 `write-face-rejected` / `write-face-overlap` / `write-face-undeclared`（`dispatch.py` 的 `WRITE_FACE_AUDIT_*`）；`_write_face_audit`（`:1089`）只传 `ev` + 自由文本 `detail`，**没有结构化字段**；三种 detail 形态：rejected = `"<task_key>: <code> <operator detail>"`、undeclared = `"<task_key>: write_face undeclared; <N> same-owner worker(s) in flight"`、overlap = `"<task_key>: overlap with <other_key> at <sample> (<rule> vs <other>)"`（**不是** `overlap-with:` 形态）。
  - PM ledger 行形状恰为 `{seq, phase:"dispatch-alarm", kind, count, detail}`（`pm-orchestrator.ts:586`），**无 `task_key` 字段**；`kind=="write-face-refusal"` 的 `detail` = `"<task_key>: <reason>"`（`reason` 内含冒号，禁 `split(":")`）；另有 `kind=="write-scope-risk"` 行，**不是拒绝**，不得混入计数。
  - 读时间线必须用 `autopilot/timeline.py:422` `query_events`（已处理 `.1/.2` 轮转）；section 只能在 `mw.py` 里按 `_doctor_rag`（`mw.py:2364`）式样加——**`mw_common.py` 是别的 session 的活动写面，本卡只读**。
- **卡**: `tasks/T-W-I15-doctor-refusal-surface.md`（写面 `packages/multi-workers/mw.py` + 新建 `packages/multi-workers/test/test_write_face_doctor.py`；七项要求含"纯只读零副作用"、"0 不报错不 unhealthy"、轮转覆盖、坏行容错、"解析不出附加字段仍计数"）。
"""

text = PLAN.read_text(encoding="utf-8")
if "### 7.9 W-14 终态吸收" not in text:
    PLAN.write_text(text.rstrip() + "\n" + ADD, encoding="utf-8")
    print("plan: appended 7.9 + 7.10")
else:
    print("plan: already has 7.9")
print(f"plan.md lines={len(PLAN.read_text(encoding='utf-8').splitlines())}")
