# Research: G3 授权字段与 done 前 AC/VC 变更检查的实现接线（DRQ-3）

> Key: mw-gate-verdict-hardening ｜ 角色: DRQ-3（design 阶段只读调研） ｜ 快照: 2026-10-09
> 决策问题：G3（`authorizes:` 显式授权字段 + worker 硬约束 + `advance *->done` 前 AC/VC 文本变更机械检查）该怎么落：字段形态与读写路径、提示词落点、done 前检查挂哪、AC/VC 文本身份锚是什么、批准记录怎么查、新 fail-closed issue 放哪、测试怎么非空洞。
> 前置：同目录 `spec-gate-authorization-scope-20261009.md`（RQ-3）已查清现状（字段允许集、提示词无约束、done 检查无 diff、批准记录=已应答 gate、issue 无常量）。本文只做**实现接线与机制选型**，不重复现状普查；所有事实带 `文件:行号`。工作树 = 2026-10-09，`HEAD=10446aefb`。

## 调研方法与出处

- 只读 grep/read：`packages/multi-workers/{mw.py,mw_common.py,autopilot/*.py}`、`packages/multi-workers/test_*.py`、`packages/coding-agent/src/extensions/agent-team-loop/**`、`packages/coding-agent/test/suite/**`、`.agents/skills/agentic-task/**`、`.claude/scripts/**`、`.tmp/**`。
- 只读跨项目：`H:\git\E2Feature\.agenticdoc\_autopilot\gates\gate-0014.md`、`.agenticdoc/feature-gui-time-mvp-board/{design.md,evidence/repair-a3-verdict-20260926.md}`。
- 实测：`python -X utf8 -c`（字段/事件集长度、grep 计数）、`Get-FileHash`（脚本副本哈希）、`git log -S`（锁行可否作为锚点）、`git check-ignore`（哪些路径是写面）。
- **关键边界发现（先看）**：本仓的 AgenticTask 框架是外部仓库——`.agentic-framework` 写 `repo=H:\git\Multi-Workers\.agents\skills\agentic-task / commit=d7004d0`；框架源码缓存 `packages/multi-workers/.tmp/agentic-task/`（`.gitignore:45-47`）、安装副本 `.agents/`（`.gitignore:55-57`）、`.claude/`（`.gitignore:21`）**全部 gitignored**，上游远端 `https://github.com/wenbocode/AgenticTask.git`（`mw.py:59-60`）。因此 `.agents/skills/agentic-task/scripts/advance_phase.py` 不是本 key 可提交的写面。

---

## F1 `authorizes:` 字段形态与读写路径（含最终两侧同步清单）

### F1.1 形态：走 `_JSON_LIST_FIELDS` 闭集数组（不升 v3，不走标量枚举）

- v2 是纯加性可选扩展、`_REQUIRED_FIELDS` 冻结 6 格（`gates.py:138-148`，import 期 assert），缺字段即未授权；`gate_schema` 是「文件形态版本标记」不是字段集哈希（`gates.py:79-82`）。⇒ 新增字段**不需要 v3**。
- 与授权/范围同族的 5 个 v2 字段里，`write_scope`/`out_of_band_actions` 已是 JSON list 形状（`gates.py:152-161`），且「散文自由文本 vs 机器字段」的既有分界就是「结构化 JSON vs 散文」。⇒ `authorizes:` 选 **`_JSON_LIST_FIELDS`（单行 JSON 数组）**，语义是「本次裁决显式授权的动作类型集合」。
- 闭集取值口径（推荐最小集 + 每个成员必须有机器消费者）：
  - `retry`：授权追加一轮/一次尝试。现存消费者 `_budget_bonus`（`conductor.py:2603-2613`）、`_resume_credits`（`conductor.py:2660-2680`）。
  - `contract-change`：授权改写 AC/VC 生效文本。**新消费者 = G3 的 done 前检查**。
  - `install`：授权安装/工具链变更。**当前无机器消费者**；按 `timeline.EVENT_TYPES` 的「先接词汇、后接生产者」先例（`timeline.py:86-92` 注释明写 pre-admitted 安全）可预登记，但必须在 design 里点明它没有消费者。
  - ⇒ design 需二选一：**只放 `{retry, contract-change}`**（每成员有消费者、最严）或 **`{retry, install, contract-change}`**（对齐 spec AC-009 示例、`install` 预登记）。本文推荐前者，理由：无消费者的成员会让「列了也不生效」变成新的语义空洞（P-014 家族）。
- 闭集校验要**解析期 + 写侧双护栏**（两个先例的组合）：
  - 解析期成员校验：仿 `gate_schema` 枚举 fail-closed（`gates.py:628-635`）——不在闭集 ⇒ `GateFormatError`。零扰动成立，因为历史文件 `authorizes` 字段命中 0（实测；非测试源码中仅 3 处英文 `authorizes`——`mw_common.py:2593`、`conductor.py:2136`、`shared/implementation-gate.ts:63`，均非 gate 字段名）。
  - 写侧护栏：仿 `REASON_CODES` 越界丢弃（`conductor.py:4925-4927` 定义、`:2523-2527` 丢弃并返回 dropped，调用方 `_log_dropped_gate_fields:2531-2551` 记 config 事件）。TS 写侧在 `answerGate()` 里直接拒绝并给可读错误（比静默丢更好，因为这是人写的值）。

### F1.2 谁在什么时候写：**推荐「conductor 建门时物化空行 + 人在应答时填值」**

三条候选与判定：

| 候选 | 可行性 | 结论 |
|---|---|---|
| A. 仅人在应答时写（扩展 `gate-writer.ts`） | `rewriteAnswerFields` **只重写已存在的行**，绝不新增行（`gate-writer.ts:101-133`；`assert rewritten.has("status")` 是唯一强约束）；`ANSWER_FIELDS` 恰 4 个（`gate-writer.ts:50`）。若字段行不存在，人**写不进去** | 单独不可行 |
| B. conductor 建门时盖章具体值 | conductor 无法预知人是否要授权 `contract-change`；若按 kind 自动盖章（如 stalled → `retry`），`contract-change` 永不可能被授权（任务描述里的「人无法授权」就是这个） | 不可作唯一路径 |
| **C（推荐）. conductor 建门盖章 `authorizes: []` + 人在应答时填值** | conductor 侧 `_stamp_gate_defaults`（`conductor.py:2499-2530`）+ `_gate_default_fields`（`:2553-2573`）已在用同一个 `_rewrite_gate_fields`（`:5967-5991`）盖 `expires_at`/`default_action`；加一行空 `authorizes: []` 零新机制。行存在后，TS 写者只需重写该行 | 可行、最小改动、fail-closed（空=未授权） |

- 「worker 永不能写」由既有守卫保证：`xkey-gate-guard.ts` 封锁 agent 工具对 `.agenticdoc/_autopilot/**`（除 `_autopilot/xkey/**`）的 write/edit/bash（规则 `:7-77`、注册 `:209-242`，每个模式都注册），worker 无法伪造 `authorizes:`。残余风险是同 uid 带外进程（守卫自述 `:31-36`）。
- 人填值的两条合法路径：审计路径 = 扩 `/autopilot gate <id> approve --authorizes contract-change`（`console.ts:455-495` → `gate-writer.ts:139-176`）；手工路径 = 直接编辑 gate 文件（`gates.py:11-13` 明写「manual file edits are equally legal answers」）。design 应两条都留，审计路径优先。

### F1.3 两侧同步清单（最终；RQ-3 F2 的 6+5+3 校正后）

Python（源，`packages/multi-workers/autopilot/gates.py`）：

1. `FRONTMATTER_FIELDS`（`gates.py:87-131`）——**追加到末尾（索引 40）**，绝不插中间（`:86` 注释「never reordered, never repurposed」）。
2. 形状集合 `_JSON_LIST_FIELDS`（`gates.py:152-160/161`）——加 `"authorizes"`。
3. `Gate` dataclass 字段（`gates.py:193-247`）——加 `authorizes: list[object] | None = None`。
4. `_to_gate()` 解析+成员校验（`gates.py:514-680`；JSON 数组走 `optional_json`，`gates.py:550-580`；枚举先例 `:628-635`）。
5. 闭集常量 `AUTHORIZES_ACTIONS`（建议放 `gates.py` 与 `GATE_KINDS` 同区），供 Python/写侧/测试共用。
6. `mw_common._gate_pending_entry` 投影（`mw_common.py:2443-2532`）——**只在字段存在时输出该键**，否则历史门 JSON 字节会被扰动（与 `_gate_node(... sentinel=True)` 的既有约定不同，需显式说明）。
7. `mw.py` 卡片投影（`mw.py:3648-3778`，`authorizes` 若上卡）——注意卡片是固定 **13 行/门**（`mw.py:3601` `_GATE_CARD_LINE_MAX=110`；TS 锁测试 `autopilot-gate-presentation.test.ts:286-306` 断言 `1+13*N`）。推荐不上新行，改追加到既有 `answer:` 行（`mw.py:3766-3771`）末尾、仅在非空时。

TypeScript（镜像，`.../agent-team-loop/autopilot/`）：

1. `GATE_FRONTMATTER_FIELDS`（`status-model.ts:599-643`）→ 41 项。
2. `GateRecord`（`status-model.ts:647-684`）——加 `authorizes: string[]`。
3. `GATE_JSON_LIST_FIELDS`（`status-model.ts:689-696`）——加 `"authorizes"`（`parseGateFile` 会强制 JSON 数组，`:872`）。
4. `parseGateFile()` 构造 + 成员校验（`status-model.ts:727-920`，JSON 强制在 `:872-873`）。
5. `gate-writer.ts`：`AnswerGateOptions`（`:24-48`）+ `ANSWER_FIELDS`（`:50`）+ `rewriteAnswerFields`（`:101-133`，重写该行；若空行已由 conductor 物化则无需新增行）+ `answerGate` 闭集校验（`:139-176`）+ `console.ts cmdGate` 的 `--authorizes` 参数面（`console.ts:455-495`）。

锁测试（3 个，必须同波更新）：

1. `packages/multi-workers/test_autopilot_gate_schema_v2.py:138-148`（`fields[12:38]==V2_FIELDS`、`fields[38:40]==CONSUMED_FIELDS`、`len==40`）——追加在末尾则切片不变，只改 `==40`→`==41` 与打印。
2. `packages/multi-workers/test_autopilot_gates.py:216-227`（`len(FRONTMATTER_FIELDS)==40` + `create()` 恰 13 键 = base12+gate_schema）——只改 `==40`→`==41`；**前提是 `create()` 本身不渲染新字段**（推荐：物化走 `_stamp_gate_defaults`，在 `create()` 之后，故 `gates.create()` 直测看不到新行）。
3. `packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts:205-241`（Python 子进程逐项比对 + `toHaveLength(40)`）→ `41`。

### F1.4 AC-009 / AC-012 如何满足

- AC-009：字段名 `authorizes`，闭集数组，解析期+写侧双护栏（F1.1）；「未被列出的动作类型不得被引用为授权源」由 F5 的判定「只读该字段、缺即 fail-closed」机械保证，且 `note`/`answered_by` 全程不读。
- AC-012：散文 note 天然不进授权判定（F5 伪代码不访问 `note`）；反向样本见 F5.4。非空洞对照由「删掉 `authorizes` 成员校验 ⇒ 用例转红」提供。

---

## F2 worker 提示词硬约束

### F2.1 现状逐行（三个可触及 spec/design 的构造点）

| 函数 | 行 | 现有约束原文（要点） | 是否保护 AC/VC |
|---|---|---|---|
| `_repair_prompt` | `conductor.py:1453-1468` | 「逐项修复并补充 [VERIFY]…；**只读约束**：`workers/*-l3-*/` 下的 `output.md` 与 `report.md` 属 reviewer 本轮产物…禁止改动…判定源」 | **否**（只保护 reviewer 产物，不保护 spec/design 条文） |
| `_phase_writer_prompt` | `conductor.py:2291-2297` | 「为 key {key} 生成 {phase} 阶段 artifact…产出到 `.agenticdoc/{key}/` 下对应文件…证据留底写入 `.agenticdoc/{key}/evidence/`」 | **否（最危险：直接授权写 spec/design）** |
| `_fix_writer_prompt` | `conductor.py:2312-2327` | 「生成/补齐证据文件使机械审计可闭合，**不改动无关 artifact**」 | 部分（只说「无关 artifact」，未点名 AC/VC 生效文本） |

派发点：phase-writer=`_advance_key`（`conductor.py:1162-1215`，缺 artifact 时 `:1179-1185`），fix-writer=`_advance_key:1203-1209`，repair=`_verify_loop`（`conductor.py:2026` 附近）。`_exec_prompt`（`:1313-1319`）已有「只碰任务书列出的文件」，属部分覆盖，本次可不改。

### F2.2 插入位置与确切措辞（对齐 `_xkey_proposal_prompt` 的「明令禁止」先例）

先例串：`conductor.py:3887`「除下方唯一写入目标外，不得修改任何其它文件」、`:3910-3911`「不得修改目标文件的断言主体/测试逻辑」「不得修改任何其它文件（含测试文件、其它 key 的产物、conductor/框架文件）」。⇒ G3 措辞应对齐该句式，插在三个构造点的**末尾一行**（保持现有行不动，纯追加，便于逐字锁测试）：

建议逐字（三条同一常量，避免漂移）：

```
- 硬约束：不得修改已锁定 AC/VC 的生效文本（spec.md §3 AC 表、design.md §7 VC 断言块）；
  确需变更必须走重开流程，并在 evidence/contract-change-<ts>.md 写明「变更清单 + 授权源 gate id」；
  未获授权的改写会被 advance done 前检查拒绝（fail-closed）。
```

- 建议做成一个模块常量（如 `_CONTRACT_CONSTRAINT`）拼进三个 prompt，测试对三处做「必须逐字包含」断言，避免 P-014「措辞差分叉」。
- 位置：`_repair_prompt` 追加在现有最后一行（`:1466-1467`）之后；`_phase_writer_prompt` 追加在 `:2296` 之后；`_fix_writer_prompt` 追加在 `:2326` 之后。
- `_phase_writer_prompt` 是 autopilot 模式下**唯一会生成 spec/design 的提示词**（`_advance_key` 缺 artifact 分支 `:1179-1185`），措辞里必须点名「已锁定」语义。

### F2.3 AC-010 的「变更清单」产物落点

- 命名惯例：本仓 `evidence/` 下产品/复算档为 `<purpose>-<date>.md`（例：`verify-run-2026-09-23.md`、`plan-postfix-regression-20260925.md`、`spec-dist-rebuild-performed-20260926.md`）；研究档才是 `evidence/research/{spec,design}-*.md`。⇒ 推荐 **`<key>/evidence/contract-change-<YYYYMMDD>.md`**（或带秒 `<YYYYMMDDTHHMMSS>`，与 QG 报告同风格：`_done_transaction` 已在用 `quality-gate-report-%Y%m%d-%H%M%S`，格式串在 `conductor.py:2122`）。
- 该文件是**人/PM 的手工产物**（授权链的载体），不是机器判据输入——机器判据只认 `authorizes:` 字段 + freeze（F5）。两者分开可避免「写了个 md 就当授权了」的新空洞（正是 E2 事故的形态）。

---

## F3 done 前检查的机制选型（本 RQ 核心）

### F3.1 关键修正：`mw autopilot advance` 不存在

- `mw autopilot` 只有两个子命令：`gates`（`mw.py:5422-5430`）与 `verify`（`mw.py:5431-5457`）；`mw.py` 全文 `autopilot advance` 命中 **0**。⇒ 任务描述的「`mw autopilot advance` → `advance.py`」调用链**不存在**。
- `packages/multi-workers/autopilot/advance.py`（192 行）是**纯 spawn-and-report 包装器**：模块 docstring `:1-21` 明写「The wrapper spawns and reports only — no business semantics」；`advance()` 在 `:164-192`，`subprocess.run([python, "-X","utf8", advance_phase.py, key, phase, ...])`（`:181-190`），**没有任何门禁实现**。（任务引用的 `:172-203` 有偏移，实际函数体 `:172-192`。）

### F3.2 实际存在的 `advance *->done` 入口（4 条，全部最终 spawn `advance_phase.py`）

| # | 入口 | 位置 | 覆盖场景 |
|---|---|---|---|
| 1 | conductor（autopilot 无人值守） | `conductor._done_transaction`（`conductor.py:2089-2233`）→ `advance.advance(key,"done")`（`:2171`）；另 `_advance_key:1206`、`execute_loop:1386` 只走非 done 边 | autopilot 项目（本项目无 `.agenticdoc/_autopilot/`，此路不生效） |
| 2 | extension 工具（PM 窗口的 sanctioned 路径） | `ui-bridge.ts registerAdvancePhaseTool`（`:1546-1635`）→ `runAgenticScript(projectDir,"advance_phase.py",...)`（`:1623`） | **本项目实际主路径** |
| 3 | PM/人 bash 兜底 | `python <framework>/scripts/advance_phase.py <key> done --summary ...`（`pm-state-guard.ts:26-33` 明示此路径） | 所有项目 |
| 4 | conductor 的 roadmap key-status 收口（非 phase 推进） | `_mark_key_done`（`conductor.py:2627-2660`）+ `_done_credentials_present`（`:1771-1814`） | autopilot 的 key-status，不是 `advance done` |

真正的**通用咽喉**是 `advance_phase.py` 自身：`GATES["done"]` 5 条规则（`:69-96`，`check_gate:191-289`）；全文无 diff 检查（实测 `git diff`/diff 判据 0）。手工改 `pm-state.md` 的 `- Phase:` 会被 `pm-state-guard.ts` 工具层封（`:137-145`），但 **bash 跑脚本不被拦**（该模块注释自述）。

### F3.3 三候选成本对比

| 候选 | 覆盖面 | 本仓可提交/可测 | 成本与风险 |
|---|---|---|---|
| (a) 改 `.agents/skills/agentic-task/scripts/advance_phase.py` | 覆盖 1/2/3/4 全部 | **否**（`.agents/`、`.claude/` 全 gitignored；上游是 `github.com/wenbocode/AgenticTask` `mw.py:59-60`） | 4 份安装副本（`.agents/skills/agentic-task/{scripts,core/scripts,claude/scripts}/` + `.claude/scripts/`，实测 sha 短值全等 `9427ABE2ECC0`）+ 3 份源码缓存（`packages/multi-workers/.tmp/agentic-task/...`，实测 hash **不同**：`4111BFF403BC4C8B`，为 2026-09-21 旧缓存，与安装副本已分叉）。改动无法被本仓 pytest/vitest 覆盖（P-023/AC-014 无证据），且 `mw init`/框架更新会覆盖；还需框架侧新增对 mw `.agenticdoc/_autopilot/gates` 的依赖（分层污染） |
| (b) 只改 conductor 侧 `advance.py` | 只覆盖 1 | 是（Python） | 前提错误（F3.1）；且会违反该模块「no business semantics」契约；对 PM 路径（2/3）零覆盖 |
| **(c) 新增 mw 侧 done 前检查** | 覆盖 1（直接）+ 2（经 `mw` CLI 钩子） | 是（Python 纯函数 + CLI；TS 只加一次调用） | 需新增一处 CLI/模块；bash 路径（3）仍为残余（与既有 pm-state hand-edit 兜底同级的已知残余） |

### F3.4 推荐：**(c) 主 + 把 (b) 折成「共享纯函数」+ 覆盖 PM 工具路（2）**；AC-011 的字面全覆盖留给 (a) 作为上游后续

推荐落法（全部在本仓写面内、可测）：

1. **纯逻辑模块** `packages/multi-workers/autopilot/contract_guard.py`：`extract_contract(text_spec, text_design) -> {id: sha}`、`freeze(key_dir, spec, design) -> path`、`evaluate(key_dir, gates_dir) -> (ok, changed_ids, carrier_gate, reasons)`。只读、无新常驻组件（GC-1 满足），依赖方向沿用 `conductor → closure` 的单向先例（`closure.py:1-20`）。
2. **conductor 挂点**：`_done_transaction` 顶部（`conductor.py:2089`，在任何写盘之前，符合其 docstring「Every step is check-before-write」）调用 `evaluate`；不通过则**不进入 QG/achieved 写入**，直接 append 机读 timeline 事件 + `mark_stalled(reason_code=...)`。这满足 AC-011 的「timeline 留痕」。
3. **PM 工具路（2）**：新增 `mw autopilot contract-guard --project <dir> --key <k>`（复用同一模块，退出码 0/1 + JSON），`ui-bridge.ts advance_phase` 工具在 `runAgenticScript` 之前调用它（一次额外 spawn；`runAgenticScript` 先例现成）。这样 sanctioned 工具路也被机械覆盖。
4. **freeze 生成**：conductor 在 `_advance_key` 的 `spec->design` 与 `design->plan` 边（`conductor.py:1206` 那条 advance 之前）写 freeze；非 autopilot 项目由 `mw autopilot contract-freeze` 或 PM 手工调用。design 需定「freeze 缺失时」的口径（见 F4.5）。
5. **若 AC-011 必须字面覆盖 bash 路径（3）**：只能走 (a)，且应作为**独立的 AgenticTask 上游变更**（单独提交 + 上游测试），不在本 key 的本仓写面内；本 key 负责把「判据语义 + freeze 格式 + 批准记录格式」定死，使其可被上游复用。

理由摘要：AC-011 要求的是「timeline 留痕 + 机读分类（P-009）」，而 timeline 是 conductor/`_autopilot` 的语义（`timeline.py`），框架脚本不写 timeline ⇒ 判据落在 mw 才自洽；同时 mw 才拥有 `authorizes`/gate 的批准语义，避免把 mw 私有协议塞进通用框架（分层）。

---

## F4 AC/VC 文本的身份锚与机械切分

### F4.1 现状：只有 id 级指纹，无文本身份

- AC 表唯一解析器 `audit_evidence.extract_ac_list`（`audit_evidence.py:108-125`）**只取 `AC-NNN` id**（正则 `:58`），不取描述；`_extract_decisions`（`:127-152`）完全不解析 VC 文本。全仓 VC 文本解析器 = 0（RQ-3 已证）。
- `evidence-requirement.md` 的 `ac_fingerprint` 是 `sha1("\n".join(ids)+"\n")[:12]`，只覆盖 id（生成器 `.tmp/msc-gen-evidence-req.py:101`，本仓 `.tmp/` 未跟踪）；`> 🔒 AC Locked at {ISO}` 行无脚本读（RQ-3 F4）。
- ⇒ 改 AC-001 正文不改任何指纹，现状对「条文文本」零身份。

### F4.2 三候选锚点对比

| 候选 | 可行性 | 结论 |
|---|---|---|
| (ii) 复用 gate `subject_sha256`/`observed_at` | **死路**：全仓无生产写者，仅 `gates.py:226-232/657-663` 声明解析 + 测试；`conductor.py` 只读 `goal_sha256`（`gate_facts:5481-5483`），`subject_sha256`/`observed_at`/`proposal_sha256` 在 conductor 0 命中 | 排除 |
| (iii) `git diff` spec/design | 可做但**不可靠**：`advance_phase.py` 有 git 先例（`_git_short_head:426-441`，只用于 project_log 的 commit 列）；本仓 `.agenticdoc/<key>/*.md` 确实被 git 跟踪（实测 `git ls-files` 命中）。但长跑 key 常**到交付才提交**（实测 `git log -S "AC Locked at" -- .agenticdoc/mw-crosskey-risk-escalation/spec.md` 返回的是交付 commit `ba40e75bd`，spec 与锁行同批加入），`advance done` 又发生在提交之前（`pm-state.md` 记录顺序：advance done → 提交）⇒ `git diff` 常为**空 ⇒ fail-open** | 不可作唯一锚 |
| **(i) 新增 sidecar `<key>/evidence/contract-freeze.json`（AC/VC 文本块 sha）** | 与 `closure.py` 的「内容寻址 marker」同族先例（`closure.BAD_DRAFT_MARKER_NAME`/sha256，`closure.py:27-31,110-137`）；不依赖 git、不依赖提交时机、可离线复算 | **推荐** |

### F4.3 推荐锚点：freeze sidecar（冻结=在阶段门接受时拍快照，之后任何文本差即「本轮 diff」）

- 「本轮 diff」不需要 git：**机械 diff = 冻结快照 vs 当前抽取文本**。这消除 F4.2(iii) 的提交时机问题。
- sidecar 形状（建议，与 `closure` marker 同风格：内容寻址 + 显式 schema）：
  ```json
  {"schema":1,"key":"<key>","frozen_at":"<ISO>",
   "spec":{"AC-001":"<sha256(canonical text)>", "...":"..."},
   "design":{"VC-001":"<sha256>", "...":"..."},
   "generator":"mw autopilot contract-freeze"}
  ```
- canonical 化口径（防假阳性、保确定性）：按 `splitlines()` 分词、行尾 CR 剥离、单元格 strip，再以 `id + "\x1f" + 文本` 求 `sha256`；**不做**全量空白折叠（避免正文换行改写被漏判），但也不把行尾空白算进身份（避免编辑器噪声）。AC 与 VC 分别成表（spec 与 design 各一）。
- 冻结时机：AC 块在 `spec->design` 接受时冻结（spec §3 在 spec 阶段定稿）；VC 块在 `design->plan` 接受时冻结（design §7 在 design 阶段定稿）。design 需明示：freeze 之后的任何 AC/VC 文本变化 ⇒ 命中 G3。

### F4.4 AC/VC 条文的机械切分口径（可复现正则）

- **AC 行**（spec §3 表）：复用 `audit_evidence` 的表行语义（`_structural_lines` 去 fenced code + `_split_table_row`，`audit_evidence.py:82-107`），把 `extract_ac_list` 从「只取 cells[0]」扩为「取 `cells[0]` 为 `AC-\d{3}` 时同时取 `cells[1]` 描述」：
  - 正则：`^\|\s*(AC-\d{3})\s*\|\s*(.*?)\s*\|\s*$`（实测本 key `spec.md:94` 起为 `| AC-001 | ... |`；spec.md 于 17:30 追加 G4 AC-015~AC-018 后的行号）。
- **VC 块**（design §7 围栏块）：生成器已有可复现正则（`.tmp/msc-gen-evidence-req.py:parse_vcs`，本仓实测可用）：
  ```
  VC-(\d{3}):\s*(.+?)\n\s*Layer:\s*(\S+)\s+Output:\s*(\[VERIFY\][^\n]*?)\s+Source:\s*([^\n]+)
  ```
  逐字段取 `assert/Layer/Output/Source`，身份 hash 覆盖五元组。实测 `.agenticdoc/mw-autopilot-slot-capacity/design.md:333-455`（§7）格式与正则一致。
- 可选加强：design §8 `| AC ID | AC 摘要 | 对应 VC | 路径 |` 映射表（`design.md:440-455`）也纳入冻结（改映射=改条文效力），但会扩大误伤面，建议 design 决断。
- 现有解析器不需要改语义：新增的是**独立抽取函数**（contract_guard 内），`audit_evidence.extract_ac_list` 保持只取 id（避免影响 L1 审计/既有测试）。

### F4.5 freeze 缺失时的口径（design 必须决断）

- 选项 1（fail-closed）：缺失 ⇒ 拒绝并给可执行提示（`mw autopilot contract-freeze --key ...`）。与 spec §2.3「缺记录/缺字段 ⇒ 视为未授权」一致，但会让历史/在飞 key 的 done 多一步。
- 选项 2（TOFU 缓释）：缺失 ⇒ 以当前文本冻结并记 `config` timeline 说明，不阻断。**是 fail-open**，不建议。
- 推荐选项 1，并把 freeze 写进 conductor 的正常阶段推进（F3.4 步骤 4）+ 提供 CLI，使正常流程不会撞上；在飞历史 key 一次性补 freeze 即可。
---

## F5 批准记录查找

### F5.1 载体：复用「已应答 gate」协议，不新造 ledger

- 现成协议：`_crosskey_machine_carriers`（`mw_common.py:2590-2612`，`kind=="xkey-authorize" and status!="pending"`，`:2593` docstring 明写「A pending gate is not a carrier」）+ `_gate_open`（`conductor.py:2575-2600`，按 `context_refs` 去重）。G3 沿用「答了才算、pending 不算」的 fail-closed 语义。
- **kind 选择**：E2 事故的真实载体是 `kind: stalled`（`H:\git\E2Feature\.agenticdoc\_autopilot\gates\gate-0014.md:3` `kind: stalled`、`:5` `key: feature-gui-time-mvp-board`、`:12` `status: approved`、`:15` note 含「放宽的是验证方式与文档同步，属可修范围」）。⇒ 判定**不绑定 kind**：任何 `status=="approved"` 且 `authorizes` 含 `contract-change` 的门都算（`xkey-authorize` 亦可，若人愿意用）。**不接受** `rejected`。这样既覆盖真实样本，又不用新增 `GATE_KINDS` 成员（`GATE_KINDS` 是冻结闭集 + TS 镜像 + 锁测试，改动面大于加字段）。
- 作用域：按 `gate.key == key` 精确匹配（gate-0014 满足）。stage 级门（`gate.key is None`）在 G3 里**不认**（fail-closed，避免跨 key 越权授权）；若 design 允许，需追加 roadmap 的 key∈stage 判定（额外耦合，需显式声明）。

### F5.2 机械判定伪代码（含 fail-closed 分支）

```python
CONTRACT_CHANGE = "contract-change"

def contract_change_authorization(gates_dir: pathlib.Path, key: str) -> tuple[bool, str | None, list[str]]:
    """(authorized, carrier_gate_id, reasons). NEVER reads note/answered_by/prose."""
    for gate in gates.enumerate(gates_dir):          # parse errors -> caller skips+tracks
        if gate.status == "pending":                 # fail-closed: answer required
            continue
        if gate.status != "approved":                # rejected is not an authorization
            continue
        if CONTRACT_CHANGE not in (gate.authorizes or []):
            continue
        if (gate.key or None) != key:                 # scope: this key only
            continue
        return True, gate.id, []
    return False, None, ["no answered gate authorizes contract-change for this key"]
```

- fail-closed 分支：`authorizes` 缺省/`[]`/越界（解析期已拒）/门 pending/门 rejected/门 key 不匹配/门文件损坏（`gates.enumerate` 抛错 ⇒ 调用方按 `GateFormatError` 跳过，绝不当作授权）——全部落到 `False`。
- 与现有 `_crosskey_machine_carriers` 的关系：两者同族但**不合并**；`xkey-authorize` 的 carrier 语义是「request_id ↔ gate」，G3 的语义是「动作类型 ↔ gate」。合并会把两套去重维度混在一个函数里（P-019 家族）。

### F5.3 AC-012 的机械保证

判定函数**不访问** `gate.note`、`answered_by`，也不解析 design.md 里的「授权链」散文（E2 `design.md:1048-1059` 的逐字引用不会被读）。⇒ 「仅凭 note 引用 ⇒ 未授权」是构造性成立，不需要额外检测。

### F5.4 反向样本 → 测试夹具

- 夹具输入（最小化，来源 E2 真实形状）：
  1. freeze sidecar 里 `AC-001` 的 hash 与当前 spec 不同（模拟条文被改）；
  2. gate 文件：`kind: stalled`、`key: <same key>`、`status: approved`、`answered_by: wenbozhou`、`note: '方案 A…放宽的是验证方式与文档同步，属可修范围'`，**无 `authorizes`**（可从 `gate-0014.md` 裁剪：id/kind/key/created_at/created_by/question/status/answered_at/answered_by/note 十行）；
  3. 无其它批准记录。
- 期望：`authorization == "none"` → 拒绝（fail-closed）。
- 非空洞对照：同一输入，只把 gate 加 `authorizes: ["contract-change"]` ⇒ 放行（P-016 反向对照），且断言 `carrier_gate == "gate-0001"`。
- 另加：pending 版（`status: pending` + `authorizes`）必须仍拒绝——证明「答了才算」。

---

## F6 新 fail-closed issue

### F6.1 issue 串风格与位置

- `_doctor_issues`（`mw_common.py:2780-2954`）全是自由文本 `append`，函数内实测 **28** 个 append；**没有机器 code 常量**（I1–I9 只是注释标签）。I9（T-24 散文授权）的 issue 串在 `:2879-2885`（`Select-String` 命中 `:2880`）。
- G3 新增 one issue（插在 I9 块之后、`roadmap_section` 之前，即 `mw_common.py:2886` 之前（I9 块 `:2879-2885` 之后）），口径对齐 I9 的「report but keep fail-closed」：
  ```
  f"key {key} contract text changed without authorization ({', '.join(changed_ids)}) "
  f"since the freeze ({freeze_rel}) - advance-to-done refused; answer a gate with "
  "authorizes: [\"contract-change\"] or revert the AC/VC text"
  ```
- 与 I9 的关系：**并列、不复用 VC-048 文案**（I9 文案点名 `cross-key repair request` 与 `xkey-authorize gate`，套在 G3 上会说错对象——RQ-3 F6 已证）。标签层面建议新开一条（如 `I10`/本 key 的 VC 号），仍沿用「issue = 机器可见、不放行」的机制。

### F6.2 `_gates_text_alerted`（`mw_common.py:2764-2778`）必须同步

- 该函数是 I7 零扰动门：`gates:` 文本行只在 I1–I6 或 I9 命中时出现（`format_doctor_text` 的 gates 行在 `mw_common.py:3108-3115`，prose 后缀 `:3103-3106`）。新条件必须加入，否则「JSON 有 issue、文本层无声」自相矛盾。
- 建议：新增一个 `gates["contract_guard"]` 节点（形态对齐 `crosskey_prose`，`_doctor_gates:2711`），`_gates_text_alerted` 加一条 `if (section.get("contract_guard") or {}).get("unauthorized"): return True`；`format_doctor_text` 加一个仅在非零时拼接的 `contract_suffix`（同 `prose_suffix` 写法 `:3103-3106`）。
- **P-018 零扰动论证**：`contract_guard` 段**只在存在 freeze sidecar 的 key 上产出**（无 freeze ⇒ 空/缺省）；历史门/历史 key 不含 freeze ⇒ 新条件恒 False ⇒ `gates:` 文本行逐字节不变、`--json` 也不新增该键。这满足 AC-013 的「缺字段时渲染逐字节相同」。

---

## F7 测试矩阵

### F7.1 夹具风格（本仓 Python）

沿用 `packages/multi-workers/test_autopilot_crosskey_prose.py` 的现成骨架：`_gate_text(...)`（手工拼 parser-valid v2 gate，`:94-135`）、`_write_gate`（`:138-143`）、`_make_service_running`（`:158-162`）、`_report`（`:165-166`）、`_doctor_args/_gates_args`（`:169-178`）、以及 `capsys.disabled()` 打 `[CONTROL]`/`[VERIFY]` 实测值的反空洞风格（`:365-454`，文件共 454 行）。G3 建议文件名 `packages/multi-workers/test_autopilot_contract_guard.py`（或并入 `test_doctor_gates.py` 的 doctor 侧断言）。

### F7.2 G3 用例表

| # | 输入 | 期望 |
|---|---|---|
| 1 | freeze 存在 + 当前 spec AC 文本 ≠ 冻结 + 无 `authorizes` 门 | `evaluate` 拒绝；reason 含 `changed_ids`；timeline 机读事件；`_done_transaction` 不写 QG/achieved |
| 2 | 同 #1，但存在 `status: approved` + `authorizes:["contract-change"]` + `key` 匹配的门 | 放行；`carrier_gate` = 该门 id |
| 3 | 同 #1 但只有 E2 形状散文 note（`gate-0014` 裁剪） | 拒绝（`authorization=="none"`） |
| 4 | 同 #2 但门 `status: pending` | 拒绝（pending 不是 carrier） |
| 5 | 同 #2 但门 `status: rejected` | 拒绝 |
| 6 | 同 #2 但门 `key` 不匹配（stage 级或别的 key） | 拒绝 |
| 7 | freeze 存在 + 文本未变 | 放行（零扰动；无 timeline 事件、无 doctor 行） |
| 8 | 无 freeze sidecar | 按 F4.5 选项 1：拒绝 + 提示 `contract-freeze` |
| 9 | 历史 v1 gate 文件（无 `authorizes`）+ 历史门队列 | 全部 `parse` 成功；`_REQUIRED_FIELDS` 恰 6；`gates:` 文本逐字节不变（AC-013） |
| 10 | 未知 `authorizes` 成员（如 `["contract_change"]` 下划线笔误） | 解析期 `GateFormatError`（fail-closed、报字段） |

### F7.3 AC-014 非空洞对照（≥2，实测值机器打印）

- 对照 A：`monkeypatch` 掉 hash 比较（或删 AC 抽取）⇒ 用例 #1 从「拒绝」转「放行」，证明**文本变更判据**是本条 fire 的原因（而非别的门/别的 issue）。
- 对照 B：把 `authorizes` 判定换成「只要门 approved 就授权」⇒ 用例 #3（散文 note，无字段）从「拒绝」转「放行」，证明**字段判定**非空洞。
- 对照 C（AC-013）：对历史 gate + 无 freeze 工程，跑 `mw doctor --json` 与 `mw autopilot gates`，断言与基线逐字节相等（`_gates_text_alerted` 新条件不 fire）。
- `[VERIFY]` 行数值必须来自夹具实测（如 `changed_ids=1 carrier=gate-0001 refused=true`），不得硬编码（P-023/P-025）。

### F7.4 需要同步的既有测试（回归面）

- `test_autopilot_auto_decision.py:300-339`：若 G3 引入新 stall reason_code，`len(STALL_REASON_CODES)==12`（`:301`）、`len(calls)==12`（`:333`）、`codes == set(STALL_REASON_CODES)`（`:338`）三处都要同步（12→13），并同步 `_recompute_l3_stall_code`（`conductor.py:5348`）。**这是本 key 最容易引爆的 P-021 面**，design 应显式认领。
- `timeline.py:67-95` + `status-model.ts:962-990` + `autopilot-event-parity.test.ts:73-84`：若新增 timeline 事件类型（如 `contract-refused`），两侧集合必须同步；**建议复用既有 `stalled`/`config` 事件**避免该同步（P-021）。
- `test_autopilot_gate_schema_v2.py:138-148`、`test_autopilot_gates.py:216-227`、`autopilot-gate-presentation.test.ts:205-241`：F1.3 的 3 个锁测试。
- `mw.py` 13 行卡片锁 `autopilot-gate-presentation.test.ts:286-306`：若 `authorizes` 上卡，必须保持 13 行/门（F1.3 #7）。
- AC-014 双语言镜像（P-021）：若 `authorizes` 进入 `GateRecord`/卡片，Python `_render_gate_cards`（`mw.py:3648`）与 TS `renderGateCards`（`console.ts:348`）都要跑。

---

## 结论 → 决策映射

1. **字段**：`authorizes` = `_JSON_LIST_FIELDS` 闭集数组（不升 v3、不上标量枚举）；闭集建议 `{retry, contract-change}`（`install` 预登记或砍掉，由 design 定）；解析期枚举 + 写侧护栏双 guard（`gates.py:87-131/152-160/514-680`、`conductor.py:2523-2527`）。
2. **写者**：conductor 建门物化 `authorizes: []`（`_stamp_gate_defaults:2499-2530`，`create()` 不动 ⇒ 不破坏 13 键锁测试）+ 人在应答时填值（扩 `gate-writer.ts:24-50/101-133/139-176` + `console.ts:455-495`）；worker 由 `xkey-gate-guard.ts:7-77` 保证不可写。
3. **两侧清单**：Python 7 处 + TS 5 处 + 锁测试 3 个（F1.3）。
4. **提示词**：`_repair_prompt:1453-1468` / `_phase_writer_prompt:2291-2297` / `_fix_writer_prompt:2312-2327` 末尾追加同一常量措辞，对齐 `_xkey_proposal_prompt` 的「不得修改」先例（`conductor.py:3887,3910-3911`）；AC-010 产物落 `evidence/contract-change-<ts>.md`。
5. **done 前检查**：推荐 **(c)**（新 mw 纯模块 + conductor `_done_transaction:2089` 顶部挂点 + `mw autopilot contract-guard` CLI 给 extension 工具路用）；**(b) 前提不成立**（无 `mw autopilot advance`；`advance.py` 无门禁语义）；**(a) 仅当 AC-011 必须字面覆盖 bash** 才走，且是上游 AgenticTask 独立变更（4 安装副本 + 3 缓存副本，其中缓存已分叉）。
6. **锚点**：新增 `<key>/evidence/contract-freeze.json`（AC/VC canonical 文本 sha，内容寻址，`closure` marker 同族）；不用 `subject_sha256`（无写者）；不用 git（提交时机不确定 ⇒ fail-open）。
7. **批准记录**：任何 `status=="approved"` 且 `authorizes` 含 `contract-change` 且 `gate.key==key` 的门；pending/rejected/散文 note 一律不认（伪代码见 F5.2）。
8. **issue**：`_doctor_issues` 新增一条 fail-closed issue（插 `mw_common.py:2887` 前），并同步 `_gates_text_alerted:2764-2778` + `format_doctor_text:3103-3115`；`contract_guard` 段仅在存在 freeze 时产出 ⇒ P-018 零扰动。
9. **测试**：`test_autopilot_contract_guard.py` 10 用例 + 3 个非空洞对照（F7.2/F7.3）；同步面 F7.4。

## 数据缺口

- `authorizes` 闭集最终成员（含 `install` 是否预登记）——design 决策。
- freeze 缺失口径（fail-closed 拒绝 vs TOFU）——design 决策（推荐 fail-closed）。
- design §8 AC→VC 映射表是否纳入冻结身份——design 决策。
- 新 stall reason_code 的名字与是否新增 timeline 事件类型——design 决策（牵连 F7.4 的三处 12→13 与事件 parity）。
- E2Feature 语料为只读快照（2026-10-09），其 `contract_sync.json`/`decisions.jsonl` 不进本仓。

`[VERIFY] DRQ-3: mw_autopilot_advance_cmd=0 autopilot_subcmds=2(gates,verify@mw.py:5422,5431) advance_advance_call_sites=3(conductor.py:1206,1386,2171) advance_py_lines=192 done_rules=5(advance_phase.py:69-96) check_types=8 diff_checks=0 ac_vc_text_parser=0 ac_fingerprint_scope=ids-only(.tmp/msc-gen-evidence-req.py:101) freeze_impl_hits=0 subject_sha256_writers=0 py_fields=40 required=6 json_list=6 event_types=23 stall_codes=12 mark_stalled_call_sites=12 authorizes_field_hits=0(comment-only) advance_phase_copies_equal=4(sha256=9427ABE2ECC0) framework_cache_copies=3(sha256=4111BFF403BC4C8B,stale) doctor_issue_appends=28 i9_issue_line=2880 gates_text_alerted=2764 project_autopilot_dir=false worktree=10446aefb`
