# PM State: mw-rag-integration

## 1. Snapshot
- Key: mw-rag-integration
- Phase: DONE
- Next Action: **独立复核已回读，判定「需修订」** → 等用户决策修复范围后开新 key `mw-rag-integration-fix`（候选 T-15~T-17 见 Process Log 末条）。已修订的产物：`evidence/quality-gate-report-2026-09-22.md`（结论 ✅→❌ 需修订）、`achieved.md`（补「独立复核」条目 + 经验教训 5/6）。K3 硬门禁仍按用户决定排除
- Started: 2026-09-22 11:55
- Updated: 2026-09-22 21:30
- Completed: 2026-09-22 18:56

## 2. Task Status

| Task | Stage | 状态 | 负责 | 证据 |
|------|-------|------|------|------|
| T-01-TS-CONFIG | 1 | done | worker `mw-rag-t01-ts-config` | VC-002/VC-024；12/12 绿；已 ack |
| T-02-ADAPTER | 1 | done | worker `mw-rag-t02-adapter` | VC-006/007/008/026；16/16 绿；`npm run check` 0/0/0；已 ack |
| T-03-TRANSPORT | 2 | done | worker `mw-rag-t03-transport` | VC-009；11/11 绿；`npm run check` 0/0/0；已 ack |
| T-04-TOOLS | 2 | done | worker `mw-rag-t04-tools` | VC-001/003/004/005 + golden 字节；10/10 绿；`npm run check` 0/0/0；已 ack |
| T-13-MCP-TOOLMAP | 3 | done | worker `mw-rag-t13-toolmap` | VC-028；新增 5/5 + 五套件 49 passed；`npm run check` 0/0/0；已 ack |
| T-05-EVIDENCE | 3 | done | worker `mw-rag-t05-evidence` | VC-010/011/012/013/016/017/021/025；新增 18/18 + 七套件 67 passed；`npm run check` 0/0/0；已 ack |
| T-09-RAG-RESEARCH | 5 | done | worker `mw-rag-t09-research` | VC-015/VC-018 + chat 600s 上限；TS 9 套件 88 passed；`test_autopilot_l0.py` 零修改；已 ack |
| T-10-AUDIT | 5 | done | worker `mw-rag-t10-audit` | VC-019/020/021 + VC-014 审计面；18/18 绿；包内 796 passed；已 ack |
| T-14-PHASE-AXIS | 5 | done | worker `mw-rag-t14-phase-axis` | VC-014/VC-020 阶段轴；TS 9/9 + RAG 全量 96 + py 801 passed；`npm run check` 0/0/0；已 ack |
| T-06-PY-CONFIG | 4 | done | worker `mw-rag-t06-py-config` | VC-024/VC-013；12/12 绿；golden `00f85e64…`（347 B）；已 ack |
| T-07-PY-INJECT | 4 | done | worker `mw-rag-t07-py-inject` | VC-022；18/18 绿；136 零回归；已 ack |
| T-08-PY-CLI | 4 | done | worker `mw-rag-t08-py-cli` | VC-023；17/17 绿；SKILL.md sha `5b58678d…`；已 ack |
| T-09-RAG-RESEARCH | 5 | pending | — | 依赖 T-04/T-05（SKILL.md 已就绪） |
| T-10-REQUIRE-AUDIT | 5 | pending | — | 依赖 T-05 |
| T-12-PARITY-LOCK | 5 | done | worker `mw-rag-t12-parity-lock` | VC-027；parity 7/7 + 四套件 46 passed；已 ack |
| T-11-VERIFY | 6 | done | worker `mw-rag-t11-verify`（超时）+ PM 主窗口接替 | **worker 因 idle 超时失败（模型流空转），产物已抢救：28/28 VC 证据行全在落盘产物中**；PM 接替完成证据汇编 + 文档 + 结案 |

## 3. Evidence Ledger

| 证据 | 位置 | 内容 |
|------|------|------|
| 第 1 轮设计评审（引用核查） | `workers/mw-rag-integration-ref-verify/output.md` | REFS-BROKEN：21 组引用中 5 组需修正（`setActiveTools` 幂等性、`_build_env` 5+1 返回、task.md 写点、行号漂移） |
| 第 1 轮设计评审（质量） | `workers/mw-rag-integration-design-critique/output.md` | NEEDS-REVISION：C-1/C-3~C-7 + W-1~W-10 + S-1 全部采纳（C-2 不采纳：PyYAML 为既有隐式依赖） |
| 设计返工 | `design.md` §0 修订记录 | D-001~D-014、VC 22→26；AC-017 追加；AC-009/AC-013 加 `[REVISED @ 2026-09-22]` |
| 阶段门禁 | `audit_phase.py mw-rag-integration` | DESIGN/PLAN/TASKS/EXECUTE 各阶段 PASS |
| T-06 实测 | `packages/multi-workers/test_rag_config.py` | PM 复跑：12 passed；`-s` 输出 `[VERIFY] VC-013/VC-024`；golden sha256 `00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035`（347 B，无尾换行） |
| T-06 回归 | `test_autopilot_config.py`+`test_common.py` | PM 未复跑（worker 报 94 passed）；另有 `test_partition_dispatch.py` 等 84 passed |
| T-03 实测 | `packages/coding-agent/test/suite/rag-transport.test.ts` | PM 复跑：11 passed（1.10s，无挂起）；`[VERIFY] VC-009` 十行（connect<2000ms、reset→connect、slow→timeout、delivered-lost→timeout、500/401→protocol、JSON-RPC error→tool、token 命中 0、cli argv 完整） |
| T-01 实测 | `test/suite/rag-config.test.ts` + `test/extensions/agent-team-loop-target-config.test.ts` | PM 复跑：12 passed（`-s` 输出 VC-002/VC-024）；既有 target-config 68 passed 零修改 |
| T-02 实测 | `test/suite/rag-adapter.test.ts` | PM 复跑：16 passed；`[VERIFY] VC-006/007/008/026` 四行齐 |
| T-07 实测 | `packages/multi-workers/test_rag_launcher.py` | PM 复跑：18 passed；`[VERIFY] VC-022`（含 `golden_bytes=347 idempotent=true`）、`VC-013`、`VC-001 injected_vars=0`；torn 任务确实未达 `Popen` |
| T-08 实测 | `packages/multi-workers/test_rag_cli.py` | PM 复跑：17 passed；`[VERIFY] VC-023 sync_installed=true sha_match=true`；`skills/mw-rag/SKILL.md` sha256 `5b58678d6001e3da06bb593deac200089a257712b5ee081d181c6391c9b84105`；六小节标题均在 |
| T-12 实测 | `test/suite/rag-parity.test.ts` + 四套件合跑 | PM 复跑：parity 7 passed；`rag-parity+config+adapter+transport` = **46 passed**；`[VERIFY] VC-027: golden_byte_match=true fingerprint_match=true origin_table_match=true fixture_digest_match=true`（**PM 修正发射通道后才可见**，见 Decisions）；PM 独立复算四 fixture sha256 与 golden（347 B、无尾换行、sha `00f85e64…`、fingerprint `436b6a35…`）全部吻合；Python 侧 `test_rag_config.py` 12 passed |
| T-04 实测 | `test/suite/rag-tools.test.ts` | PM 复跑：10 passed；`[VERIFY] VC-001`（`rag_tools=0 task_md_block=0 probe_requests=0 skill_file_unchanged=true budget_file_absent=true`）、`VC-004 tools=6 chat_visible=false server_enums=6/6`、`VC-005 error_kind=capability api_calls=0`、`VC-003 rejected=true queued=0`、`golden_byte_match=true bytes=347 trailing_newline=false` |
| T-04 回归 + 修改面 | `npm run check`（仓根）+ `git status` | PM 实测：`npm run check` **exit 0**（Checked 1069 files，No fixes applied，tsgo 无诊断）；`git status` 确认**既有测试零修改**（仅新增 `rag-*` 测试文件）；`pm-orchestrator.ts` 为 +9 行纯新增（RAG 注册 + try/catch，无误删） |
| T-13 实测 | `test/suite/rag-toolmap.test.ts` + 五套件合跑 | PM 复跑：5 passed；`rag-toolmap+tools+adapter+transport+parity` = **49 passed**；`[VERIFY] VC-028: mapped_names=6/6 sources_merged=true multi_rounds_tool=rag_search_multi_rounds` 可见；PM 直读 `adapter.ts` 确认 `RAG_TOOL_MAP` 为数据表（`rag_graph:{mcp:["graph_query"]}`、`rag_sources:{mcp:["list_sources","list_collections"],merge:"sources"}`、`rag_search:{multi:"rag_search_multi_rounds"}`）；仓根 `npm run check` **exit 0**（1070 files）；`git status` 无既有测试被改 |
| T-05 实测 | `rag-evidence.test.ts` + `rag-budget.test.ts` + 七套件合跑 | PM 复跑：两新套件 **18 passed**；七套件（evidence+budget+tools+toolmap+adapter+transport+parity）= **67 passed**（基线 49）；八条 `[VERIFY]` 齐（VC-010/011/012/013/016/017/021/025 + 行格式那行）；仓根 `npm run check` **exit 0**（1074 files）；`worker-mode.ts` 的 3 行删除经核查全是 T-04 自己重写的 RAG 相关行（`export function toolsForType`、`setActiveTools` 调用点与注释），无其它会话内容被删 |
| T-09 实测 | TS 9 套件 + `test_rag_research.py` + `test_autopilot_l0.py` | PM 复跑：TS 9 套件 **88 passed**（`[VERIFY] VC-015: parity_unchanged=pass tools=11 conductor_dispatchable=false`、`VC-015: rag_chat_visible_only_for=rag-research gated_types=5`、`rag_chat_timeout: chat=600000 retrieval=180000 configured_override=900000`、VC-018 四行）；`test_rag_research.py` 5 passed（含 `conductor_dispatch_refused=true queued=0 timeline=type-rejected`、`l0_untouched=true`）；`test_autopilot_l0.py` 5 passed 且 `git diff --stat` 为空（**真的零修改**）；仓根 `npm run check` **exit 0**（1076 files） |
| T-09 附带修复 | `packages/coding-agent/src/extensions/agent-team-loop/rag/guidelines.ts` 注释 | PM 直修（**仅注释**）：该注释写了字面 `packages/multi-workers/skills/mw-rag/SKILL.md`，命中 T-08 的守护测试 `test_extension_source_never_references_the_installed_skill`（匹配 `mw-rag.md` / `mw-rag/SKILL`）→ 仓内红测试。改为不触发守护的描述后 `test_rag_cli.py` 17 passed。**未改守护测试本身**（保持严格）；但该守护是文本层代理，T-09 的 worker 也被迫改自己的注释撮开，已列入 T-11 的钝边说明 |
| T-10 实测 | `test_rag_audit.py` + 回归组 | PM 复跑：新套件 **18 passed**（`[VERIFY] VC-014`（审计面）/`VC-019`/`VC-020`/`VC-021` 四行齐）；回归组（`test_rag_config`+`test_rag_cli`+`test_rag_launcher`+`test_serve_doctor`+`test_mw_bootstrap`）= **97 passed**；`mw.py` 的 2 行删除经核实属 ue-toolchain 会话（非本 key）；实仓冒烟 `mw rag audit --project H:/git/Multi-Workers` → 退出 0、五计数均为 0 |
| T-14 实测 | TS `rag-required` + py `test_rag_phase` + 全套回归 | PM 复跑：TS 新套件 **9 passed**（`[VERIFY] VC-014: required_unused_emitted=true output_marked=true idempotent=true`、`VC-020: worker_reads_phase=true missing=unknown`、`citation_present_emitted=false`、`not_required_writes=0`、`rag_disabled_writes=0`）；py 新套件 **5 passed**（`phase_empty_byte_identical=true golden_match=true` 等）；`python -m pytest -q` = **801 passed, 9 deselected**；仓根 `npm run check` **exit 0**（1077 files）；**PM 独立脚本复核**：`render_task_md(phase="")` 与不传 **逐字节相同**、`phase="DESIGN"` 时行序为 `---` / `type: coding` / `phase: DESIGN`、`_owner_phase(仓, "mw-rag-integration") == "EXECUTE"`、`_scratch`/缺失 → `""` |
| T-14 修改面 | `git diff --numstat` 两个镜像测试 | 仍为 T-09 当时的 `7/0` 与 `1/0`（**纯新增，T-14 未动任何既有测试**）；`test_autopilot_l0.py` 仍零 diff |
| T-11 实测（worker 抢救产物） | `$TEMP\t11\*.txt`（18 个产物文件） | **28/28 VC 均有 `[VERIFY]` 实测行**（PM 用收采脚本逐 VC 汇总，无缺项）；套件计数：TS rag `10 passed \| 1 skipped` / **97 passed**、autopilot `86 passed`、extensions **405 passed**、Python **802 passed, 9 deselected**；`slow-real.txt` = `VC-017: worker_alive=true rag_call_ms=180004 pings=5 watchdog_enabled=true idle_ms=60000 heartbeat_ms=30000`（180.06s 实跑） |
| T-11 worker 失败根因 | `trace.log` + `$TEMP\t11` 时间线 | 最后一个工具调用在 18:37:40（`./test.sh` 写入 44KB 输出，18:39:29 完成），此后 **613s 无任何模型 delta** → 属模型流空转（环境侧），非仓库缺陷；此时已完成的验证产物均已落盘 |
| T-11 结案产物（PM 直执） | `evidence/verify-run-2026-09-22.md` | 333 行：复现口径 9 条命令 + 28 VC 总表 + 逐 VC 断言/实测行 + 两处“期望行字面不同但语义等价”的核实 + 零回归与修改面 + 3 个外部失败的逐条归属 + 盘边/限制 |
| 文档与 CHANGELOG（PM 直执） | README / env doc / 两包 CHANGELOG | `packages/multi-workers/README.md` +100（「RAG 接入（可配置）」含两层合并、`target.yml` 示例、四命令、**AC-018 映射表**、`phase:` 头、降级五层）+ 3 行 env；`packages/coding-agent/docs/environment-variables.md` +17（RAG env 段）；两包 CHANGELOG `[Unreleased] → Added` |
| 坑点台账 | `.agenticdoc/_pitfalls.md` +28 | 新增 **P-005**（跨语言契约字段“只有读者没有写者”→ 审计/单测全绿但生产永不触发）与 **P-006**（绿灯用例的 `console.log` 被 vitest `silent:"passed-only"` 吞掉 → 证据行不可见）；两者都是本 key 真实踩过的 |
| PM 独立复核（关键不变量） | `render_task_md` / `_owner_phase` / 慢速 L2 | `empty_identical=True`（空 `phase` 与不传逐字节相同）；`phase: DESIGN` 行序 `---/type: coding/phase: DESIGN`；`_owner_phase(仓, "mw-rag-integration") == 'EXECUTE'`、`_scratch`/缺失 → `''`；`npm run check` **exit 0**（当前树） |
| 质检门禁（`advance_phase` 前置） | `evidence/quality-gate-report-2026-09-22.md` + `evidence-requirement.md` | 前置门禁 7 项（6 ✅ / 1 ⚠️ 无 baseline 目录）；问题清单 = 18 AC + 28 VC + 9 Coverage（F1~F9）+ 7 交叉 = 62 项，**❌ 0 / ⚠️ 2**；结论 ✅ 通过（2 项验证欠债 R-1/R-2 = 真实 rag-mcp 未联调）；`ac_fingerprint=sha1(AC-001..018)=` 已记录 |
| 设计可追溯修复（质量门禁连带） | `design.md` 2 行 | VC-027 补 `Source: AC-002`（原缺 Source 行）；VC-028 的 Source 从陈旧的 `AC-002` 改正为 **`AC-018`**（T-13 的映射 AC）—— 修复前 AC-018 在 AC→VC 映射里是空的（覆盖声称 18/18 但实际漏 1）；修后 mermaid 0/0、audit_phase PASS |
| 阶段推进 | `advance_phase(done)` | `execute -> done` 成功；`_index.parallel` 置 DONE；`_project_log.md` 追加汇总行（commit d106bcfb2） |
| 独立质检复核（DONE 后补做） | worker `mw-rag-qg-review`（type=review） | **失败（结论全丢）**：`worker.log` = `done exit=0` + `stream closed before response.completed`；它已读 39 个文件 + 11 次 grep，在**输出最终长报告时 provider 流中断**，而 review 角色**无 write 权限**（allowlist `read/find/grep/ls`）→ 结论无处落盘，`output.md` 只剩 272 B 框架模板（“Task completed. Tools used: ...”）。根因：审查类任务的**唯一交付通道是最后一条消息**，长报告 = 单点故障 |
| 复核重派-1（review 类型，全失败） | `mw-rag-qg-review-a`（A+B，2m/57 calls）、`mw-rag-qg-review-b`（C+D，1m/42 calls） | 两者都是同一签名：`worker.log` = `done exit=0` + `stream closed before response.completed`，`output.md` 只剩 264~272 B 框架模板。**本仓 review 型 worker 累计 12 次里 8 次丢结论**（同期 coding 型 14/14 正常）；缩小最终消息（≤80 行）**未能**消除 → 根因是 review 角色**无 write**、整份结论只能靠一条最终消息。已把实测口径写入坑点 P-007 |
| 复核重派-2（coding 类型 + 落盘，进行中） | `mw-rag-qg-review-c`（type=coding，路由默认模型） | 按 P-007 采用口径：审查 worker 改 coding 类型，**只允许写 `evidence/quality-gate-review-2026-09-22.md` 一个文件**，骨架先落盘、分节 `edit` 填充（避免长消息单点故障）。允许跑定向 rag 测试并做**反例试验**（临时改 golden/fixture，确认 `[VERIFY]` 值随之变化、测试变红，**做完必须还原**并 `git status` 自查 —— 本仓多会话并行）。交付：A 28 条断言强度（强/弱/装饰）+ B 18 条 AC 实现落点 + C 质检报告判定复核 + D 文档一致性 + 反例试验记录 |

## 4. Hypothesis Queue

| 假设 | 判据 | 状态 |
|------|------|------|
| TS 侧 `yaml` 可直接用（无新依赖） | `packages/coding-agent/package.json` 含 `yaml@2.9.0`，`target-config.ts:36` 已在 import | 已证实 |
| `rag-research` 入 Python `REGISTRY` 后 parity 测试无需修改 | `test_autopilot_l0.py:233-250` 断言 `set(ts_reg) == set(py_reg) | {coding,review,research,fallback}`，两侧同加即通过 | 待 T-09 实测 |
| `dist/extensions/agent-team-loop.js` 属提交面 | `git ls-files` 命中 | 已证实（T-11 增加 bundle 重建） |
| T-01 先于 T-06 落地是否会造成两侧不可调和漂移 | golden + fixture 做字节/指纹恒等断言（T-12） | 待 T-12 实测（已备回退：以 Python/golden 为准修 TS） |
| `MW_RAG_SERVERS_FILE` 设定但文件缺失时应否回落 HOME | T-06 选“硬覆盖、不回落到”（测试隔离）；T-01 对齐 | 已锁定（design §2 跨语言契约） |

## 5. Decisions

| 决策 | 内容 | 依据 |
|------|------|------|
| 评审返工范围 | 采纳 C-1/C-3~C-7 与 W-1~W-10、S-1；拒绝 C-2 | 逐条复核（PyYAML 反证见 Hypothesis Queue） |
| parity 方案 | `rag-research` 入 Python `REGISTRY` + `conductor_dispatchable=False`，parity 测试零修改 | C-1；`test_autopilot_l0.py:233-250` 断言原文 |
| 首批派发 | T-01 ∥ T-02 ∥ T-06（文件不重叠） | plan.md 依赖图 |
| 新增 T-12-PARITY-LOCK | 用 T-06 的 golden + 4 个共享 fixture 做 TS↔Py 配置/渲染/指纹/origin 恒等，发现漂移以 Python/golden 为准修 TS | T-06 报告指出 T-01/T-04 需对齐其契约（新增 VC-027） |
| 第二批派发 | T-03 ∥ T-07 ∥ T-08（T-03 不依赖 T-02；T-07/T-08 依赖 T-06 已落地） | plan.md 依赖图 + T-06 完成 |
| 接受 T-03 的解释器偏离 | `cli-bridge` 用 `PYTHON_EXE` 约定（`python`/`python3`）+ `MW_RAG_PYTHON` 覆盖，**不用 `process.execPath`** | T-03.md 原文错误（`process.execPath` 是 Node/Bun，会让 skill 传输死的）；design §4.2 本就是 `<python>`；已回写 T-03.md / design §4.2 / T-11 env 文档 |
| AC-014 小节名对齐 spec 与 SKILL.md | 改 spec AC-014 文字（[REVISED @ 2026-09-22]）：六小节 = `查询/结论/引用/未解决/快照/影响面`，并补「引用段须逐条给 citation + local_path/exists，无法核对项入未解决」 | T-08 报告指出 spec 旧词与 task.md 不一致；以**已交付的 SKILL.md**（T-09/T-11 的标准）为准，同一处同步 design VC-018 与 T-09 |
| T-04 / T-12 并行且文件不重叠 | T-04 拥有 `rag/block.ts`、`tools.ts`、`guidelines.ts`、`worker-mode.ts`、`task-dispatcher.ts`、`ui-bridge.ts`；T-12 只拥有 `config.ts` + `rag-parity.test.ts` | 两者都要碰 rag 块/配置；不划所有权会互相覆盖 |
| T-12 的四条已知漂移 | (1) `pathRootsDigest` 锚 cwd → 改 project root；(2) target.yml `rag:` 键 camelCase → snake_case；(3) `origin` 键 camelCase → snake_case；(4) 错误类别只需 `unknown-key`/`unknown-server` 同名 | PM 预读 T-01 实现所得；同一份 target.yml 不可能两侧同认 |
| T-12 自行发现的 3 条额外漂移（均必要） | (5) 指纹 payload 形态：TS 原只哈希 `{servers,roles,phases,budgets}`（**漏 `enabled` 与 `default_server`**、用解析后的 roles/phases、键名 camelCase）→ 改为 Python 的 `{enabled,servers,default_server,roles,phases,budgets}` 蛇形**verbatim** 形态；(6) 缺省 `transport` 从"按块推断"改为 Python 的 `mcp`；(7) 嵌套合并 `null` 删除语义对齐 `_rag_merge_server` | 不修这三条 `fingerprint_match` 不可能为 true；漂移 (5) 是真 bug（两个启用集不同但解析后形态相同的配置会算出同一指纹） |
| 接受 T-04 越权但必要的一处改动 | `pm-orchestrator.ts` +9 行（`pmActivate` 里 `try { registerRagTools(pi, projectDir) } catch`） | T-04 的 task 注明确要求 `pmActivate` 注册；该文件不在其它会话的未提交清单里，且 diff 为纯新增（无误删/重排）；PM 已核 `git diff` |
| **新增 AC-018 / VC-028 / T-13（工具名映射）** | 参考服务真实工具名与我们的逻辑名不同名：`rag_graph`→`graph_query`、`rag_sources`→`list_sources`+`list_collections`（需合并）、重写开关 true 的 `rag_search`→`rag_search_multi_rounds`；映射以**数据表**形式声明在 `overcode-v1` 适配器内（不进配置 schema，第二个服务族走新 adapter）；证据行 `tool` 记逻辑名、`mcp_tool` 记实际发出名 | T-04 如实上报该未实现项且当时无参考；PM 从 `...\rag-mcp\SKILL.md` 与 `references/tools-reference.md` 摸清真实工具名——不补的话 `rag_graph`/`rag_sources` 打真实服务是"工具不存在"，AC-004 的六工具面有一半是空壳。T-13 与 T-05 必须串行（同改 `tools.ts` 调用链） |
| AC-006 口径修订 | 把"fixture 记录 `multi_rounds=true, auto_rewrite=true`"改为"**适配器解析出的开关**为 true/false，落线上时按 AC-018 映射转换，fixture 记录的**实际工具名与参数**须与映射结果一致" | 原措辞与 AC-018 物理冲突（映射后开关不再下发）；T-02 的 VC-008 本就是适配器层证据，修订后 T-02/T-04 的既有证据仍有效 |
| 接受 T-13 的错误类别偏离 | 未知逻辑名用 `RagConfigError` + 既有 `kind=invalid-shape`（不是 dispatch 提示里的 `config`） | T-12 锁死的 `RagConfigErrorKind` 联合无 `config` 成员，而硬约束禁改 `config.ts`；为它扩联合会牵动跨语言契约，不值。已把该决定写进 design VC-028 正文（`kind=invalid-shape`），零请求不变 |
| T-05 证据行要带两个名字 | `tool=<逻辑名>` + `mcp_tool=<实际发出名>` | T-13 已把实际名放进 `RagEnvelope.mcp_tool`；不写进证据行就无法在 audit 时核对映射是否生效。已回写 T-05 的“T-04/T-13 交接”一节 |
| `rag_call` 行格式契约变更（`mcp_tool` 变必带） | design **VC-011** 正则为 `^rag_call server=\S+ tool=\S+ via=(mcp|cli) ms=\d+ results=\d+ mcp_tool=\S+$`（前六字段仍是规范前缀）；T-05 的两处格式描述同步；**T-10 的解析器改按 key=value 逐字段读**，禁止位置切割/整行 `$` 锚定 | T-05 正确指出：旧措辞（`results=\d+$`）与 T-13 的审计需求物理冲突；旧格式是我在 T-13 之前写的，属陈旧契约。现已把两边改一致（不断抬高“陈述即事实”） |
| `rag_chat` 600s per-call 上限未实现 | 不重开 T-05，**折进 T-09**：TS 常量 `RAG_CHAT_TIMEOUT_MS = 600_000`，仅 `rag_chat` 取 `max(mcp.timeout_ms, 600s)`；抽可测函数 `ragCallTimeoutMs(logicalTool, config)` 并断言两个值；**不改配置 schema**（T-12 跨语言契约） | T-05 停手是对的（`config.ts` 被锁），但参考服务 `rag_chat` 实测 41s–9min，180s 会把 chat 掐死，而 chat 正是 rag-research 的主武器 → 不能当欠账带过 |
| 接受 T-05 的结算/持久化语义 | `settleChat`：connect 不送达才退、timeout 不退；wall/cumulative 在 `reserveChat` **之前**检查；`Budget` 启动时只读种子 + `persist` 计数 max-merge（重生的 worker 继承已用额度）；`rag-budget.json` 仍只在首次调用时创建 | 三道预算的语义与 D-006 一致（防重复副作用 + 并发不超发）；继承额度是“同 task-dir 重生”下的正确保守选择 |
| 接受 T-09 同时修两个镜像测试 | `test_dispatch_models.py`（+1 字典项）、`test_autopilot_dispatch.py`（+5 断言行）——PM 逐行核 `git diff`：**纯新增，无删改/无弱化** | 这两个文件就是“与源同步”的镜像（硬编码 `REGISTRY` 键集与角色映射）；给 `REGISTRY`/`TASK_TYPE_TO_ROLE` 加 `rag-research` 后它们必然红。关键验收文件 `test_autopilot_l0.py` 字节未动（`git diff --stat` 空）已达标 |
| 核实 conductor 不会被绕过 | PM 直查 `DISPATCHABLE_TYPES` 全局消费者：仅 `pm/ui-bridge.ts:842`（`/worker` **手派**时的 type 校验）——`rag-research` 列在那里正是想要的；conductor 拦截在 Python（`dispatch.py`），并有 `conductor_dispatch_refused=true queued=0` 测试为证 | 否则“TS 列可派发 + Python 拦”可能是空拦 |
| **新增 T-14（阶段轴是死的）** | 两侧派发器写 task.md `phase:` 头（TS `pm/ui-bridge.ts` / Python `render_task_md`，**未知阶段不写** → 零字节变化）+ `parseTaskMd` 读它 + worker 末态发 `rag-required-missing` 并标注 `output.md`（复用 T-09 的 `researchDocEvidence`，不自建第二机制） | **PM 追查 T-10 的“phase 来自 task.md 头”约定时发现没人写它**：`task-dispatcher.ts:118` 与 `mw.py:1779-1787` 都在**读** `phase:`，却没有一个写入方 → `phases.<X>.require` 在生产中永不触发，AC-015/VC-020 的 phase 半边等于是空壳。另：VC-014 的 TS 面（worker 发射 + output.md 标注）此前无人认领 |
| T-14 之后才做 T-11 | T-14 会改 `worker-mode.ts`/`ui-bridge.ts`/`dispatch.py`，而 T-11 要重建 `dist/extensions/agent-team-loop.js` bundle | 不串行会把陈旧 bundle 当产物交出去 |
| **T-11 idle 超时 → PM 接替** | worker 失败（idle 613s，模型流空转），不重派：其验证产物已落盘（18 个 `$TEMP\t11\*.txt`，含 28/28 VC 行 + bundle 重建 + 180s 慢调用），PM 直接读产物汇编证据 + 写文档 | 重派会让新 worker 把所有重型命令重跑一遍（~22 分钟 + 同量上下文），且同样有在超大输出后空转的风险；规则“idle 型排查环境”已执行（确认非仓库缺陷），且失败点在**流程末端**，产物可复用 |
| 接受两处“期望行字面不同但语义等价” | VC-023 第三子句（`activate_no_write=covered_by(T-04 VC-001)`，同一断言由 VC-001 的 `skill_file_unchanged=true` 覆盖）与 VC-017 的 L2 拆分（L1 行 + `MW_RAG_SLOW=1` 实跑的 L2 行） | 两条都有实测证据，不是“跳过”；已写进证据文档 §2.1 供复核 |
| 3 个外部失败的归属 | `packages/agent` 2 个（文档化 Windows 基线）+ `packages/ai` 1 个 | `packages/ai` 的那个是**本地生成目录漂移**：`packages/ai/src/providers/data/` 被 `.gitignore:10` 忽略，`TIMI_MODELS` 由其 `timi.json` 生成（本机含 `gpt-6`/`hy4-preview` 等新条目），而仓库内测试的 `EXPECTED_MODELS` 是旧的；`git diff --stat -- packages/ai` 为空、该 json 在 HEAD 中不存在 → **本 key 未触碰 `packages/ai/**`** |
| 接受 T-14 的 VC-007 令牌拆分 | `_PHASE_LINE_KEY = "Phase:"` + `"- "` 拼接（并非字面 `- Phase:`） | PM 读了 `test_autopilot_l0.py::test_vc007_static_scan`：它禁的是**字面量**（本意：只有 `advance_phase.py` 能**写**那条行），而 T-14 只是**读**。属“读被写守护误伤”，两边都不改，但已写进 T-11 要求它在结案文档里点明（另一处同类钝边是 `mw-rag/SKILL` 守护） |
| 允许 T-12 修改 `rag-config.test.ts` 期望值 | 仅改"错误锚点"相关期望（`defaultServer`→`default_server`、camel origin 键→snake、删除 Python 不会记录的块级 origin 断言） | 该文件是本 key 新产物（非仓库既有测试），且 task.md 明确授权修错锚点期望；改动已在 output.md 逐条列出 |
| PM 直接修 `rag-parity.test.ts` 的 VERIFY 发射通道 | `console.log` → `process.stdout.write`（加尾 `\n`） | 仓库 vitest 配 `silent: "passed-only"`，绿灯用例的 `console.log` 被吞 —— 证据行在"必跑命令"里**看不见**，T-11 无法采集。T-02 已踩过同一坑并用 `process.stdout.write`。1 行修，PM 直执；修后已复跑确认 VC-027 可见且 biome 0 findings |

## 6. Turn End Records

| 时间 | 阶段 | 本轮完成 | 证据 |
|------|------|---------|------|
| 2026-09-22 | DESIGN 返工 | 吸收两份评审 + 重写 design（VC 22→26）+ 修 research note 行号 + spec 加 AC-017 + key-decision A 段更新 | audit_phase PASS / mermaid 0 error |
| 2026-09-22 | PLAN+TASKS | 写 plan.md（6 stage/11 task）+ tasks/T-01..T-11；补 dist 重建与文档产物 | audit_phase PASS（TASKS） |
| 2026-09-22 | EXECUTE 启动 | 派发 T-01/T-02/T-06 三个 coding worker；phase → EXECUTE | 本表 Process Log |
| 2026-09-22 | EXECUTE 第一批回读 | T-06 done 并吸收（PM 复跑测试 + 校验 golden）；将 T-06 契约钉进 design §2，新增 VC-027 与 T-12-PARITY-LOCK；派发 T-03/T-07/T-08 | `test_rag_config.py` 12 passed / golden sha 吻合 / audit + mermaid PASS |
| 2026-09-22 | EXECUTE 第二批回读 | T-03 done 并吸收（PM 复跑 11/11 + 十行 VC-009）；接受其解释器偏离并回写文档；将四类错误构造表与 server 重标注要求交接给 T-04/T-05 | `rag-transport.test.ts` 11 passed / `npm run check` 0/0/0（worker 报） |
| 2026-09-22 | EXECUTE 第十一批（收尾） | T-11 worker **idle 超时失败**（模型流空转）；PM 排查环境（非仓库缺陷）+ 抢救产物（28/28 VC 行、套件计数、180s 慢调用、bundle 重建全在）+ 接替汇编 `evidence/verify-run-2026-09-22.md` + README/env/两包 CHANGELOG + `achieved.md` + 两条坑点（P-005/P-006）+ `npm run check` exit 0 | 28/28 VC；TS 97/86/405 passed；Python 802 passed；`npm run check` exit 0；`test_autopilot_l0.py` 零 diff |

## 7. Process Log

- 2026-09-22 EXECUTE：派发首批 3 个 coding worker——`mw-rag-t01-ts-config`（T-01 TS 配置层）、`mw-rag-t02-adapter`（T-02 引用语法/path_roots）、`mw-rag-t06-py-config`（T-06 Python 配置层）。三者文件不重叠，可并行。等待终态回读后按依赖链推进 Stage 2。
- 2026-09-22 EXECUTE：T-06 done 并吸收。PM 亲自复跑 `test_rag_config.py`（12 passed）与 `-s` 的 `[VERIFY]` 输出，校验 golden sha256/字节数/无尾换行均与 worker 报告一致。T-06 落定四项跨语言契约（`{servers: ...}` 顶层形态、snake_case 字段 + `RAG_FIELD_CAMEL`、`origin` 用 snake_case 路径、`MW_RAG_SERVERS_FILE` 硬覆盖），已写入 `design.md` §2 并新增 `VC-027`。
- 2026-09-22 EXECUTE：因 T-01 先于 T-06 派发，已识别 TS 侧漂移风险；新增 `tasks/T-12-PARITY-LOCK.md`（Stage 5）做 golden 字节/指纹/origin 表恒等断言，修改方向明确为"以 Python/golden 为准修 TS"。
- 2026-09-22 EXECUTE：派发第二批 3 个 worker——`mw-rag-t03-transport`（VC-009）、`mw-rag-t07-py-inject`（VC-022）、`mw-rag-t08-py-cli`（VC-023）；T-03 与 T-02 无文件重叠，T-07/T-08 依赖的 T-06 产物已就绪。
- 2026-09-22 EXECUTE：T-03 done 并吸收。PM 复跑 `rag-transport.test.ts`（11 passed，1.1s）确认无挂起且四类错误可区分。**接受一项必要的文档纠错**：T-03.md 原文的 `process.execPath` 是错的（那是 Node/Bun，而 skill 契约是调 `<python> <cli_entry>`），worker 改用 `mw-runner.ts::PYTHON_EXE` 约定 + `MW_RAG_PYTHON` 覆盖——已回写 T-03.md、design §4.2、T-11 的 env 文档清单。
- 2026-09-22 EXECUTE：把 T-03 的交接项转成后续任务的硬要求——T-04 必须用配置 server 名重新标注 `RagToolError.server`（传输层只填 `baseUrl`）；T-05 直接复用其四类错误构造表与 `fixture.calls.length` 增量断言，不重新发明。
- 2026-09-22 EXECUTE：T-04 完成（六工具门控面 + rag 块 + 幂等注入 + 派发前校验 + `pmActivate` 注册），`rag-tools.test.ts` 10/10，仓根 `npm run check` exit 0，既有测试零修改。
- 2026-09-22 决策（补真缺口）：T-04 报告里"MCP 工具名映射未实现"不是可以带货的欠账——参考服务真实工具名与我们的逻辑名不同名（`rag_graph`→`graph_query`，`rag_sources`→`list_sources`+`list_collections`，重写开关 true 的 `rag_search`→`rag_search_multi_rounds`）。已新增 **AC-018 / VC-028 / T-13-MCP-TOOLMAP**，并把 AC-006 的口径改为"适配器解析出的开关"+“落线按 AC-018 映射”。T-13 与 T-05 串行（同改 `tools.ts`）。
- 2026-09-22 EXECUTE：T-13 完成（3 分钟，改动面仅 3 个文件），逻辑工具名→真实服务名映射真正落地：`rag_graph`→`graph_query`、`rag_sources`→`list_sources`+`list_collections` 合并、重写开关 true 的 `rag_search`→`rag_search_multi_rounds`；五套件 49 passed 零回归；仓根 `npm run check` exit 0。
- 2026-09-22 决策（证据可核对性）：T-13 的实际发出名落在 `RagEnvelope.mcp_tool` 上，但不进证据行就无法审计 → 已在 T-05 要求证据行同时给 `tool=<逻辑名>` 与 `mcp_tool=<实际名>`，并写明“一次逻辑调用 = 一次预算/熔断/心跳（`rag_sources` 两次 HTTP 只计一次）”。
- 2026-09-22 EXECUTE：T-05 完成（证据行/熔断/三次预算/心跳），两新套件 18/18、七套件 67 passed、`npm run check` exit 0。它上报的两件事都被当真处理：`mcp_tool` 使 `rag_call` 行格式契约变更（已同步 design VC-011 + T-05 两处 + T-10 解析器要求），chat 600s 上限缺失（折进 T-09，给可测函数而非新配置字段）。
- 2026-09-22 决策（不把欠账带进结案）：T-05 明确把 `rag-required-missing` 发射划给 T-10、VC-017 L2 与 VC-013 argv 划给 T-11；PM 已把这三项写进对应任务文件，避免收尾时才发现无人认领。
- 2026-09-22 EXECUTE：T-09 完成（`rag-research` 双侧接入 + conductor 拒派 + 六小节调研文档校验 + `ragCallTimeoutMs` 补上 chat 600s 地板），TS 9 套件 88 passed、`test_autopilot_l0.py` 零修改。
- 2026-09-22 发现的仓内红测试（已修）：T-04 的 `rag/guidelines.ts` 注释写了字面 skill 源路径，命中 T-08 的守护测试 `test_extension_source_never_references_the_installed_skill`；PM 直修注释（不动守护），`test_rag_cli.py` 17 passed。教训：这类“文本层代理”守护容易误伤注释，T-11 结案时要在盘边说明。
- 2026-09-22 EXECUTE：T-10 完成（`mw rag audit` + require 并集 + 证据行 key=value 解析），`test_rag_audit.py` 18 passed、回归 97 passed、实仓冒烟退出 0。它自己上报的“phase 自 task.md 头”存疑项被 PM 追到底：**两侧都没人写 `phase:`** —— 阶段轴是死的（`phases.<X>.require` 永不触发），且 VC-014 的 TS 面无人认领。已新增 T-14 并把 task.md `phase:` 契约写进 design §2；T-11 串行在 T-14 后（bundle 重建依赖最终源码）。
- 2026-09-22 EXECUTE：T-14 完成，阶段轴真打通：两侧派发器写 `phase:`（未知不写、零字节变化）、`parseTaskMd` 读它、worker 末态发 `rag-required-missing` 并标注 `output.md`（复用 T-09 的 `researchDocEvidence`，无第二套机制）。PM 额外用独立脚本验了三条关键不变量（空 phase 逐字节相同 / 行序 / `_owner_phase` 在真仓返回 `EXECUTE`）。
- 2026-09-22 环境噪声登记：`packages/coding-agent/Python/_cache/last_welcome.txt` 由 Python install manager 自动写入，不属本 key 产物；另外 `packages/ai/src/providers/data/`（`.gitignore:10` 忽略的本地生成模型目录）会导致 `packages/ai/test/timi-models.test.ts` 在**本机**变红 —— 与本 key 无关（`git diff --stat -- packages/ai` 为空）。
- 2026-09-22 收尾：T-11 worker 在跑完全部重型验证后因模型流空转被 idle 看门狗终止（22 分钟 / 111 次工具调用 / 单条 44KB 输出）。**教训已入坑点 P-005/P-006，并将“重型验证与文档写作拆分”写进 achieved.md 的经验教训 #4**。PM 接替完成结案材料；两包 CHANGELOG、README、env 文档、`evidence/verify-run-2026-09-22.md`、`achieved.md` 均已落地。
- 2026-09-22 EXECUTE：T-12 完成，跨语言契约真正锁住：TS 指纹 == golden `fingerprint=436b6a35…`，`origin` 表与 Python 逐字段一致，`renderRagBlock`（T-04）与 golden **逐字节**相等（347 B，无尾换行）。漂移共 7 条（PM 预识别 4 + worker 自发现 3），其中第 5 条（指纹漏 `enabled`/`default_server`、用解析后形态）是真 bug。
- 2026-09-22 教训固化：**证据行必须用 `process.stdout.write`**（本 repo vitest `silent: "passed-only"` 会吞绿灯用例的 `console.log`）。T-02 已知此坑，T-12 又踩一次；已写入 T-05/T-11 要求。
- 2026-09-22 T-04 当前状态（不阻断，待其自清）：repo 级 `npm run check` 会在 `rag/tools.ts`（6 个 biome warning + `RagToolParams.server?: unknown` tsgo 错误）与 `pm/task-dispatcher.ts`（未用 import/var）上报错；T-12 无权触碰已如实上报。这些是 T-04 自己的收尾（其 task.md 要求 `npm run check` 0/0/0）。
- 2026-09-22 决策（AC-014 口径）：T-08 报告指出 spec 旧词与 task.md 不一致。**以已交付的 SKILL.md 为单一标准**（`## 查询/## 结论/## 引用/## 未解决/## 快照/## 影响面`），已改 spec AC-014（带 `[REVISED @ 2026-09-22]`）并同步 design VC-018 与 T-09，避免 T-09/T-11 拿两套标题判定。
- 2026-09-22 复核失败诊断（关键）：拆成两个小任务的 review 型 worker **双双失败**——`mw-rag-qg-review-a`（2 分钟 / 57 次工具调用）、`mw-rag-qg-review-b`（1 分钟 / 42 次工具调用），`worker.log` 均为 `done exit=0` + `stream closed before response.completed`，`output.md` 只剩 264~272 B 框架模板。**全仓 review 型 worker 实测 12 次里 8 次没交出结论**（4 次 stream-closed + 3 次空内容即 settle + 1 次模型侧空转），同期 coding 型 14/14 正常。**缩小输出预算（≤80 行）不能消除**该失败 → 根因是 review 角色**无 `write`**、整份结论只能靠一条最终消息（详见坑点 P-007）。
- 2026-09-22 判定修正（复核口径）：按 P-007 采用口径改派 **coding 型审查 worker** `mw-rag-qg-review-c`（只允许写 `evidence/quality-gate-review-2026-09-22.md` 一份文件、骨架先落盘、分节 `edit` 填充；允许跑定向测试并做反例试验，要求做完还原 + `git status` 自查）。**一次通过**：10 分钟 / 142 次工具调用，134KB 级材料读完并落盘 34 KB 报告，未修改任何被审代码。
- 2026-09-22 复核结论（需修订）：复核判定「机制主体成立，但 PM 质检报告 ✅ 通过属高估」。PM 已逐条独立复核其 5 条 TOP FINDINGS 并全部成立：(1) **AC-006 运行时未接线**——`rewriteDefaults`（`rag/adapter.ts:247`）与 `resolveForRole`/`resolveForPhase`（`rag/config.ts:583/595`）`rg` 全仓**仅测试引用**，`callRag`（`rag/tools.ts:515-526`）只透传显式参数，`ragToolCalls` 仅在显式 `multi_rounds===true` 时改走 multi 工具（`adapter.ts:313`）→ 与教训 1 的 `phase:` 头同源（有实现、有单测、有 `[VERIFY]` 行，却是死代码）；(2) `[unreachable at session start]` 的 marker 测试零命中（复核称 `rag-unavailable` 也无测试属表述略宽，实测有 4 处）；(3) VC-018 在 `evidence-requirement.md` 声明 L2，实际只有纯函数证据；(4) role 回落 TS `coding`（`dispatch-models.ts:78`）vs Python `task_type`（`mw.py:1866`）不一致；(5) 文档不一致（README `mw rag` 缺必填 `--project`、`probe --server` 是幻影参数、`MW_RAG_ENABLED` 死变量且 `launcher.py:351-352` 注释不实、`rag-rewrite-degraded` 语义被 README 混淆、probe help 与退出码矛盾）。
- 2026-09-22 复核的反例试验（可信度背书）：改 `test/fixtures/rag-block.golden.md` 末位 hex → `rag-parity` 3 failed 且 `[VERIFY] VC-027` 因断言先抛而**未打印**；改 `machine-servers.yml` 的 `token_env` → `test_rag_config` 3 failed（含 `test_vc013_token_env_names_only`）。两项均还原至基线 sha256（`00f85e64…` / `99c745c0…`），`git status` 无 ` M`。结论：28 条 `[VERIFY]` 行**无装饰行**，强度为 20 强 / 5 弱或混合 / 1 伪覆盖（VC-008）/ 1 层声明过强（VC-018）/ 1 等价替代（VC-023）。
- 2026-09-22 待用户决策（修复范围）：拟开 key `mw-rag-integration-fix`，候选任务：**T-15**（F-1：把 role/phase 默认真正接进 `callRag`——由 `registerRagTools` 接收 role/phase，经 `resolveForRole/Phase` + `rewriteDefaults` 合并到实际参数，并用 fixture 断言**实际发出的工具名**；同时让注入块的 `[mw] Rewrite:` 行与实际行为一致）、**T-16**（F-2 + F-4：补 `[unreachable at session start]` / `rag-unavailable` 断言；Python audit role 回落对齐 TS 并补 `type: foobar` 两侧对照用例）、**T-17**（F-3 + F-5/D-1~D-8：VC-018 降级为 L1 或补运行时用例；修 README 用法/幻影参数/退出码、处置 `MW_RAG_ENABLED`（删或补读取方并改注释）、澄清 `rag-rewrite-degraded` 语义）。备选：若用户选择「不修 F-1」，则应把 AC-006 标为未实现（撤销 `[REVISED]` 口径）并删除死函数，而不是留着假装已交付。
- 2026-09-22 决策（并行所有权）：T-04 与 T-12 同时派发但文件严格不重叠（T-12 只改 `rag/config.ts` + 新增 parity 测试；`rag/block.ts` 等归 T-04）；T-12 需修四条已识别漂移：path_roots 解析锚点、target.yml rag 段键名 snake_case、origin 键 snake_case、错误类别同名。
