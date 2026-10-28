# T-W-I15 · AC-006：`mw doctor` 写面拒绝可见面（计数 + 最近样本，0 不报错）

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 写面闸门的拒绝必须**可被运维看见**（不只是躺在 JSONL 里）：`spec.md` AC-006「`mw doctor`（或等价只读面）能列出写面重叠拒绝的计数与最近样本，无重叠时显示 0 而非报错」。
- **缺口（PM 实测，本卡唯一消费者）**：今天两条通道都已经在写审计——conductor `autopilot/dispatch.py:1089` 的 `_write_face_audit` 往 `.agenticdoc/_autopilot/timeline.jsonl` 追加 `write-face-rejected`/`write-face-overlap`/`write-face-undeclared` 事件；PM 侧 `pm/pm-orchestrator.ts:567` 的 `recordDispatchAlarm` 往 `.agenticdoc/_autopilot/auto-decisions.jsonl` 追加 `phase:"dispatch-alarm"`, `kind:"write-face-refusal"` 行。但**没有任何只读命令面把它们列出来**：`mw_common.doctor_report`（`mw_common.py:4039`）的 section 列表（`service`/`queue`/`gate s`/`dispatch`/`activation`…）里没有写面容；TS 侧 `readGateReminders` 只读 `phase === "remind"` 行（`autopilot/status-model.ts:1232`），`dispatch-alarm` 行**不被任何面消费**。⇒ 拒绝发生了，但操作者看不到计数与样本。
- **要抄的式样（同文件内既有扩展点）**：`mw.py:587` `cmd_doctor` 在拿到 `mw_common.doctor_report(...)` 之后按 section 追加——`mw.py:614` `report["conductor"] = _ap_conductor.conductor_status(project_dir)`、`mw.py:617` `report["rag"] = _doctor_rag(project_dir)`，人类可读行由 `mw.py:633-638` 自己打印（`print(_format_rag_doctor_line(rag))`），即**新增 section 只需改 `mw.py`，不必碰 `mw_common.py`**。`mw.py:2364` 的 `_doctor_rag` 是"section 形状 + 失败降级"的现成模板。
- **读时间线的现成入口**: `autopilot/timeline.py:422` `query_events(...)`（`timeline_path` 见 `:123`）已处理 `.1`/`.2` 轮转与缺失文件——**不要**自己 `open()` 那个路径。
- **裁定**: `design.md` D-008（拒绝形状：稳定 code + `overlap-with` + 样本）、`plan.md` §7.3/§7.7（两通道审计出口）。

## 写入允许面

- `packages/multi-workers/mw.py`
- `packages/multi-workers/test/test_write_face_doctor.py`（新建）

## 写入禁止面

其余一切路径，特别地：`packages/multi-workers/mw_common.py`（**另一个 session 正在追加写，绝对只读**，本卡的 section 必须在 `mw.py` 里按 `_doctor_rag` 的式样加）、`packages/multi-workers/autopilot/**`、`packages/multi-workers/dispatch.py`、`packages/coding-agent/**`、`packages/multi-workers/test/` 下的既有测试文件（只许新增本卡自己的文件）。**禁止 `npm run check`**；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **新增只读 section**：在 `mw.py::cmd_doctor` 里按既有式样加 `report["write_face"] = _doctor_write_face(project_dir)`，并用一个新的 `_format_write_face_doctor_line(section) -> str` 在非 `--json` 时打印一行（跟随 `mw.py:633-638` 的既有输出风格）。
2. **纯只读**：不写任何文件、不取任何锁、不修改 `report["summary"]`、**不把写面拒绝计入 `issues`**（拒绝是正常闸门行为；0 与 N 都不得让 `mw doctor` 变红）。
3. **两个来源都要**（AC-007 的口径是两通道同判定，运维面也不该只看一半）：
   - conductor：`autopilot.timeline.query_events` 读出的事件名以 `write-face-` 开头的那些；
   - PM：`.agenticdoc/_autopilot/auto-decisions.jsonl` 中 `phase == "dispatch-alarm"` 且 `kind == "write-face-refusal"` 的行；**逐行容错**（torn/坏行跳过，缺文件返回空，永不抛异常）。
4. **输出形状**（键名自定但必须自洽且稳定，并在测试里锁定）：
   `{"total": N, "by_code": {code: n}, "by_source": {"conductor": n, "pm": n}, "recent": [{"source", "ts", "task_key", "code", "overlap_with", "sample"} ...]}`，`recent` 上限 5 条（并集按时间取最近，顺序在测试里锁定）。**无任何拒绝时**必须是 `total=0` + 空 `recent`，且**不报错、不 unhealthy**。

   **两个来源的确切文本语法（PM 已读码核实，按此实现，别猜）**：
   - **conductor（timeline 事件）**：事件名就是 `write-face-rejected` / `write-face-overlap` / `write-face-undeclared`（常量在 `dispatch.py`，见 `WRITE_FACE_AUDIT_*`）；事件载荷有 `key`（owner key，`_scratch` 时为 `None`/`-`）与自由文本 `detail`（`_write_face_audit` 只传 `ev` 与 `detail`，**没有结构化字段**）。三种 `detail` 形态（`dispatch.py:1165`/`:1185`/`:1210` 一带）：
     1. rejected：`"<task_key>: <code> <operator detail>"`，例如 `"w-x: write-face-invalid-entry entry '!packages/x/**'"`；
     2. undeclared：`"<task_key>: write_face undeclared; <N> same-owner worker(s) in flight"`；
     3. overlap：`"<task_key>: overlap with <other_key> at <sample> (<rule> vs <other>)"` —— **注意这里不是 `overlap-with:` 形态**，`overlap_with` 要从 `overlap with X at Y` 里取，`sample` 取 `at` 之后的片段。
   - **PM（`auto-decisions.jsonl`）**：行形状恰为 `{seq, phase:"dispatch-alarm", kind, count, detail}`（`pm-orchestrator.ts:586` `recordDispatchAlarm`），**没有 `task_key` 字段**；写面拒绝的 `kind == "write-face-refusal"`，`detail` = `"<task_key>: <reason>"`，其中 `reason` 形如 `write-face-overlap: overlap-with:<key> sample=<s>` / `write-face-overlap: overlap-with:<key> unsupported=<n>` / `write-face-invalid-entry: entry '<raw>'` ⇒ `task_key` 取第一个 `": "` 之前的部分（`reason` 里还有冒号，别用 `split(":")`），`overlap_with` 取 `overlap-with:` 之后、空白之前。
   - 另有 `kind == "write-scope-risk"` 的行（`pm-orchestrator.ts` `recordWriteScopeResidualRisks`，`detail` = taskKey）——**它不是拒绝**：可以另行计数（可选），但不得混进写面拒绝的 `total`/`by_code`。
   - **不得因为解析不出附加字段而丢掉一行**：`code` 能从事件名 / `detail` 读出就计数，取不到的附加字段写 `null`（并有一条测试专门覆盖“detail 形态意外时仍计数”）。
5. **轮转覆盖**：`.agenticdoc/_autopilot/timeline.jsonl.1`（`.2` …）里的历史事件必须被计入——用 `query_events` 即自然满足，测试要有一条显式覆盖。
6. **测试（新建 `test/test_write_face_doctor.py`，无 skip/todo/xfail，全部真断言）**：
   - (a) 全新 tmp 项目（无 `.agenticdoc/_autopilot/`）⇒ `total == 0`、`recent == []`、无异常、`report["summary"]["healthy"]` 不受影响、`write_face` 不在 `issues` 里；
   - (b) 用 `autopilot.timeline.Timeline(...).append(...)` 写 2 条 overlap + 1 条 parse 拒绝 ⇒ `by_code` 计数正确、`by_source["conductor"] == 3`、`recent` 带出 `overlap_with`/`sample`；
   - (c) PM ledger 行（`phase:"dispatch-alarm"`, `kind:"write-face-refusal"`）⇒ `by_source["pm"]` 计数；**坏行 + 其它 `kind`/`phase` 行必须被忽略**；
   - (d) 轮转：把历史事件写进 `timeline.jsonl.1`（或先写 timeline 再轮转）⇒ 仍被计入；
   - (e) **只读证明**：调用前后对项目目录做快照 diff，断言**零新增/零改动文件**（照抄 `test/test_write_face_dispatch.py` 的零副作用纪律）；
   - (f) 若 `test/test_write_face_dispatch.py` 或既有 doctor 测试（`test_mwds_t08_doctor_blocked.py`）里有可直接复用的 CLI/报告装配器，优先复用而不是重造。
7. 既有套件不得回归：`test_write_face.py`、`test/test_write_face_dispatch.py`、`test/test_write_face_e2e.py` 必须保持全绿（本卡不应改到它们的被测代码）。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑原始命令 + 原始输出**：新建套件条数（并给 (a)~(e) 每条对应的用例名）、`python mw.py doctor --json` 在本仓库实跑后 `write_face` section 的原始 JSON 片段、以及本仓库 `mw doctor` 的退出码（**0**，证明"0 不报错"）。若出现 `## 路径形态（warn）`/`## Ledger Malformed` 段，说明它来自 `worker/output-writer.ts`，不影响判定。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest test/test_write_face_doctor.py -q
python -m pytest test_write_face.py test/test_write_face_dispatch.py test/test_write_face_e2e.py -q
python mw.py doctor --json
echo "doctor_exit=$LASTEXITCODE"
python mw.py doctor
```

## 改动历史

- 2026-10-14 本 key 已交付两条通道的写面闸门与审计写入（conductor `dispatch.py:1089` timeline 事件；PM `pm-orchestrator.ts:567` ledger 行），但**审计**与**可见面**之间的最后一跳缺失（AC-006）。本卡只加只读展示面，不改闸门判定、不改 `mw_common.py`。

## 硬约束

- `mw_common.py` 是别的 session 的活动写面，**只读**；section 必须在 `mw.py` 里按 `_doctor_rag` 式样加。
- 只读：零文件写入、零加锁、不改 `summary`/`issues`（0 与 N 都不得让 doctor 变红/退出非 0）。
- 不跑 `npm run check`（P-017）；不跑无文件参数的全量 vitest（P-032）；测试禁用 `skip`/`todo`/`xfail`。
