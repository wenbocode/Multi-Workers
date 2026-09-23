# PM State: mw-rag-window-parity

## 1. Snapshot
- Key: mw-rag-window-parity
- Phase: DONE
- Next Action: 质量门禁 worker（`mw-rwp-qg-review`）运行中；回读后写 achieved.md → 推进 DONE
- Started: 2026-09-23 12:11
- Updated: 2026-09-23 12:52
- Completed: 2026-09-23 12:52

## 2. Task Status

| Task | Stage | Status | Worker | 备注 |
|---|---|---|---|---|
| T-1-SKILL-DIR-PARITY | 1 | done（PM 自验✓） | `mw-rwp-t1-skill-dir-parity` | `rag/config.ts` 用 `optionalString`、`RagSkillEntry.dir: string\|null`、`tools.ts` 的 `resolveCliDir`；VC-301~305；PM 复跑 `rag-window`+`rag-parity`+`rag-config` = 32 passed |
| T-2-MW-RAG-CMD | 2 | done（PM 自验✓） | `mw-rwp-t2-mw-rag-cmd` | `mw-runner.ts` 的 `runMwCliRaw`/`ragMw`/`RAG_SUBCOMMANDS`；`ui-bridge.ts:1994` 的 `sub === "rag"` 分支 + `parseRagArgs`/`formatRagOutput`/`MW_COMMAND_DESCRIPTION`；VC-306~308/311 |
| T-3-DOCTOR-RAG-ROW | 2 | done（PM 自验✓） | `mw-rwp-t3-doctor-rag-row` | `DoctorJson.rag` + `formatRagDoctorLine`（逐字对齐 `mw.py:_format_rag_doctor_line`）；VC-309/310，三组 fixture TS==Python 实测；PM 复跑 `rag-window` = 14 passed |
| T-3B-DOCTOR-GATE（PM 直执） | 2 | done（PM 自验✓） | —（PM） | T-3 自报偏离：门控用 `report.rag` 存在性，而 Python 是 `mw.py:523` 的 `exists or enabled` ⇒ 无 RAG 配置的项目会多打一行。改为镜像门控（新导出谓词 `shouldShowRagDoctorRow`）+ 新增 VC-309b（两侧同门实测）；PM 复跑 `rag-window` = 16 passed |
| T-4-VERIFY | 3 | done（PASS，PM 回读✓） | `mw-rwp-t4-verify` | VC-301~312 全有实测行；零回归（`npm run check` exit 0、Python 839 passed/9 deselected）；反例 A/C/D 变红、E-4（二服务器排序 + `required_missing>0`）TS==Python 逐字相等；**3 项发现**：反例 B 不变红（`--project` 无真 spawn 用例）、D 的红点与预测不同、Python 对 5 个字段 `.strip()` 而 TS 不 strip |
| T-3C-TRIM+SPAWN（PM 直执） | 3 | done（PM 自验✓） | —（PM） | 修 T-4 发现 3：`rag/config.ts` 新增 `optionalTrimmedString` 用于 `mcp.url`/`mcp.token_env`/`skill.dir`/`skill.cli_entry`（镜像 Python `.strip()`）；新测试 `test/suite/rag-trim-parity.test.ts`（VC-305b，真子进程比对 + 空白值双侧拒绝）；`rag-window.test.ts` 新增 **VC-308b**（stub `MW_PY` 真 spawn 断言 argv 与 exit code）闭合 T-4 发现 1；`path_roots_file` 故意不 trim → 遗留 R-6 |
| T-5-VERIFY-DELTA | 3 | done（PASS，PM 回读✓） | `mw-rwp-t5-verify-delta` | 零回归：rag 14 文件 127 passed、`agent-team-loop*` 178 passed、Python 839 passed/9 deselected、`npm run check` exit 0、fixture/golden 零 diff；**四条反例全红**（A 2 red、B 由新增 VC-308b 打红＝闭合 T-4 发现 1、C VC-310 red、D `rag-parity` 4 red），复原后 sha256 等于基线 |
| QG-REVIEW | 3 | running | `mw-rwp-qg-review` | 合入前质量门禁（Step 1~5，独立复跑 ≥3 条命令，默认怀疑立场） |
| T-4-VERIFY | 3 | pending | — | 独立验证 + 三条反例（`optionalString`→`requireString` / `--project=.` / 删 RAG 行） |

## 3. Evidence Ledger

| 项 | 数量 | 状态 | 备注 |
|---|---|---|---|
| VC-301~305（parity） | 5 | **已采集（PM 复跑✓）** | `[VERIFY] VC-301/302: dir=null parse=ok`；`VC-303: kind=invalid-shape mentions_skill_dir=true`；`VC-304: null_to_root=true`；`VC-305: ts==py 5e9bfc0055eb`（缺省与 `null` 同值）/`2998c51ff849`（显式 `skills/x`），Python 侧为真子进程 `mw_common.load_rag_config`+`rag_fingerprint` |
| VC-306~308/311（`/mw rag`） | 4 | **已采集（PM 复跑✓）** | `parseRagArgs` 三例实测（`list`/`audit --key K`/`bogus`→usage 含 5 个子命令）；`level0/1/2=info/warning/error`；`truncated_lines=31 hint_present=true exact30_intact=true`；`mw_description_has_rag=true`；接线实测 `ui-bridge.ts:1994` → `runMwRagCommand` |
| VC-309/310（doctor 行） | 2 | **已采集（PM 复跑✓）** | `[VERIFY] VC-309`：not-enabled / config-error / enabled-unreachable 三组 `ts=py=true`；`VC-309b: empty_py_row=false empty_ts_row=false configured_py_row=true configured_ts_row=true`；`VC-310: gate_absent=false gate_inert=false gate_exists=true gate_enabled=true rows=0` + `rag_rows=1` |
| VC-312（零回归） | 1 | **已采集（T-4）** | `npm run check` exit 0；`rag-*` 55 passed、`agent-team-loop*` 178 passed、Python 839 passed/9 deselected；fixture 与 `test_autopilot_l0.py` diff 空；golden sha256 `00f85e64…4035` |
| VC-305b（trim parity） | 3 | **已采集（PM 自验✓，待 T-5 复核）** | `[VERIFY] VC-305b: dir="skills/x" cli_entry="cli.py" ts==py=true prefix=a7ac2452cbb3`；`url="http://127.0.0.1:19999/" token_env="RAG_TOKEN" ts==py=true prefix=b30415c5058c`；`blank_dir_ts_kind=invalid-shape blank_dir_py_error=true` |
| VC-308b（真 spawn） | 1 | **已采集（PM 自验✓，待 T-5 复核）** | `[VERIFY] VC-308b: argv0=["rag","list","--project=<tmp>"] argv1_code=1 ok0=true ok1=false` |
| 反例试验 | 4 | 待做（T-4） | A/B/C/D 见 T-4 任务书（D 为 PM 直执门控新增） |
| E-4（未钉分支） | 1 | **已采集（T-4）** | 二服务器（A 可达 mock + B `127.0.0.1:9999` 不可达）+ `roles.review.require` 造 `required_missing=1`：TS==PY 逐字相等，probe 按名排序 |
| R-6（残留差异） | 1 | **已实测（T-5）** | padding `" .mw/rag-roots.json "` 下：TS `pathRootsFile` 未 trim / Python 已 strip；两侧 digest 均 `null`；fingerprint TS `d5b017c6…` ≠ PY `9ed001e4…`；把 TS 该键手动 trim 后重算 = PY 逐字节相等 ⇒ **差异仅来自该键**；无 padding 对照两侧同为 `a3e2ee05…` |

## 4. Hypothesis Queue

- H-1（spec §7）：放宽 `dir` 后 fingerprint 仍逐字节相等 → VC-305 直接证伪；**若不相等，回退到「解析值保持 null、仅调用点落根」而不是改 payload**。
- H-2：`dir: ""` 仍非法 → 若因 `optionalString` 变成合法，VC-303 会红。
- H-3：`/mw rag` 只转发就够用 → 若实测需要结构化结果，记为新遗留（不阻塞本 key）。
- H-4：doctor RAG 行照抄 Python 文本即可一致 → VC-309 三组 fixture 逐字比对证伪。

## 5. Decisions

| ID | 决策 | 理由 |
|---|---|---|
| D-301 | TS 解析层 `skill.dir` 保持 `null`（不归一化成 `.`），调用点 `resolveCliDir` 落控制工作区根 | 归一化会让 TS/Python canonical JSON 不同 → fingerprint 不等 → `config tear (rag)` 误报 |
| D-305 | `runMwCli` 拆出内部 `runMwCliRaw`（暴露 exit code），既有包装行为不变 | `audit` 的 exit 1 = 有 findings（warning）、exit 2 = 用法/配置错误，必须区分 |
| D-306 | `/mw rag` 只转发，白名单 `list/probe/audit/sync/init` 由纯函数校验，未知 sub 不调 CLI | Python 保持解析/校验唯一源；避免两套语义 |
| D-307 | 输出 >30 行截断并附完整命令 | 通知通道会截断长文本；不静默丢信息 |
| D-308 | `/mw doctor` 的 RAG 行**逐字**对齐 `mw.py:_format_rag_doctor_line` | 窗口与终端不得出现两套说法（P-008 家族） |
| D-310 | TS 测试落 `test/suite/rag-window.test.ts`；`[VERIFY]` 用 `process.stdout.write` | 与既有 suite 一致；vitest `silent: "passed-only"` 会吞 `console.log` |
| D-311（T-3B 新增） | TS 渲染 RAG 行的门控镜像 `mw.py:523` 的 `rag.exists or rag.enabled`（导出谓词 `shouldShowRagDoctorRow`），不是「`rag` 键存在」 | `_doctor_rag` 恒返回非空 dict ⇒ 存在性判定会给完全没配 RAG 的项目多打一行，窗口与终端不一致（违反 AC-304 的一致性意图） |
| D-312（T-3C 新增） | TS 对 `mcp.url`/`mcp.token_env`/`skill.dir`/`skill.cli_entry` 取 `.trim()`（`optionalTrimmedString`），镜像 Python `_rag_finalize_*` 的 `.strip()` | T-4 实测：padding 下两侧 fingerprint 不等（同一个配置文件两套哈希 ⇒ 正是 `config tear (rag)` 的误报源）。**注意**：`sources` 里的条目与 role/phase 的 `server`/`source`/`default_server` 在 Python 侧**不** strip，故 TS 也**不**能统一 trim（会造出新的不等） |
| D-313（T-3C 新增） | `path_roots_file` **不** trim（保持原值） | Python 该字段 strip、但 digest 用未 strip 串（`mw_common.py:636-637`）；保持原值可让两侧 digest 都为 `None`。残留差异（该键本身）记为遗留 R-6，不在本 key 改 Python |

## 6. Turn End Records
*(empty)*

## 7. Process Log

- 2026-09-23 12:1x 需求（用户）：把两处收口缺口合成**一个 key** —— (R-1) TS `skill.dir` 与 Python 不一致；
  (R-2) pi 窗口内没有 `/mw rag`、`/mw doctor` 也不显示 RAG 行。（R-2 由用户上一轮提问「这些指令可以在 pi 窗口的
  mw 指令下生效吗」触发；R-1 由 `mw-rag-config-guide` 的独立验证 T-23 发现。）
- 2026-09-23 12:1x spec/design/plan/tasks 落盘并推进到 EXECUTE（`audit_phase.py` PASS）。门禁过程中被拦两次并修正：
  spec 缺 `可复用资产`/`需规避坑点` 两个 feedforward 段（框架常量，非我最初猜的「可证伪假设/可能坑点」）与
  §0 缺「预期收益」——已补齐；design 的 mermaid 因 19 节点超阈值告警 → 拆成两张图，0 error / 0 warning。
- 2026-09-23 12:1x 调研要点：`shared/mw-runner.ts:425` 的 `runMwCli` 丢弃 exit code（D-305 的由来）；
  `mw.py:517` 已产出 `report["rag"]`（本 key 零新增 Python 行为）；TS `ragFingerprint` 自称与 Python 逐字节相等，
  是 D-301 的直接约束。
- 2026-09-23 12:1x 派发 T-1 ∥ T-2（文件不相交：`rag/*.ts`+`rag-parity.test.ts` vs `shared/mw-runner.ts`+`pm/ui-bridge.ts`）。
- 2026-09-23 12:17 T-1/T-2 双双 done 并回读：T-1 报告 fingerprint 三变体 TS==Python（`5e9bfc0055eb` ×2 / `2998c51ff849`）；T-2 报告 `/mw rag` 全绿。
  **PM 自验**：`git diff` 看不到 `rag/**` 与 `rag-*.test.ts`（整目录 untracked，本会话前序 key 未提交）→ 改为直读源码 + 实测：
  `config.ts` `parseSkill` = `optionalString(raw.dir, …)` 且 `RagSkillEntry.dir: string | null`；`optionalString` 走 `requireString` ⇒ `""` 仍非法（D-303 成立）；
  `ragFingerprint` payload **未改**（`skill: { dir, cli_entry, timeout_ms }`）⇒ D-301/D-304 成立；`tools.ts` 有 `resolveCliDir` 且 `cliCall` 已改用它；
  `ui-bridge.ts:1791` description 含 `rag`、`:1994` 分支调用 `runMwRagCommand`、`:1839` runner 可注入 ⇒ AC-303/AC-305 接线成立。
  复跑 `rag-window`+`rag-parity`+`rag-config` = **32 passed**（含 VC-301~308/311 全部 `[VERIFY]` 行原文）。
  另：T-2 报告的两条 biome `useTemplate` info 现已不存在（`npx biome check` 两文件 → `No fixes applied`，无诊断）。
- 2026-09-23 12:18 T-3 派发（T-2 完成后，同一文件串行，避免互相覆盖）。
- 2026-09-23 12:2x T-3 done 并回读：三组 fixture（not-enabled / config-error adapter=v2 / enabled+probe 不可达）TS 串与 `mw.py doctor` 文本行逐字相等（`ts=py=true` ×3）。
  **T-3 自报偏离 1 = 真缺陷（不是可选项）**：TS 门控用「`report.rag` 是否存在」，Python 用 `mw.py:523` 的 `exists or enabled`；
  而 `_doctor_rag` 恒返回非空 dict ⇒ 完全没配 RAG 的项目在窗口里会多一条 `rag: not enabled (skill absent)`，终端不打。
  **PM 直执 T-3B**：新增导出谓词 `shouldShowRagDoctorRow(rag): rag is NonNullable<DoctorJson["rag"]>`（`exists === true || enabled.length > 0`）并改用它；
  把既有 VC-310 的「有行」用例改成 `{exists:true, enabled:[]}`，新增「无配置无行」用例与门控真值表，并新增 **VC-309b 跨语言同门实测**：
  空项目 `empty_py_row=false empty_ts_row=false`、有配置 `configured_py_row=true configured_ts_row=true`。复跑 `rag-window` = **16 passed**；`npx biome check` 2 文件 exit 0；`npx tsgo --noEmit` exit 0。
  **踩坑（已记 P-010）**：用 Python `read_text`/`write_text` 打补丁会把源文件 LF 整体翻成 CRLF（Windows 文本模式），
  结果 biome 想重排整个 `ui-bridge.ts`（报「Formatter would have printed the following content」全文件 diff，1 error）。
  已 `replace(b'\r\n', b'\n')` 复原为 LF 并按 biome 的单行签名要求收尾，再跑即 exit 0。
- 2026-09-23 12:2x T-4 派发（任务书已补：第 4 条反例 D + E-4 未钉分支实验），等待独立验证结论。
- 2026-09-23 12:3x T-4 done（PASS）。三条发现里两条是**该修的缺陷**，一条是**证据强度问题**：
  (1) 反例 B（`--project=.`）不变红 ⇒ `runMwCliRaw` 的 `--project` 拼接无真 spawn 用例钉住（弱证据）；
  (2) Python 对 `mcp.url`/`mcp.token_env`/`skill.dir`/`skill.cli_entry`（+`path_roots_file`）做 `.strip()`，TS 只校验不 strip ⇒ padding 值下 fingerprint 不等；
  (3) 反例 D 的红点与任务书预测不同（红在 VC-310 而非 VC-309b，因 VC-309b 只测谓词）。
  **PM 直执 T-3C**：新增 `optionalTrimmedString` 并用于上述 4 个字段；新增 `test/suite/rag-trim-parity.test.ts`（VC-305b：padding 的 skill/mcp 两组 ts==py 实测 + 空白 `dir` 双侧拒绝）；
  新增 **VC-308b**（stub `MW_PY` 真 spawn，断言 argv 为 `["rag",<sub>,...,"--project=<root>"]` 且 exit 1 保留）闭合发现 1。
  复跑：rag 系列 **14 文件 / 127 passed**；`rag-trim-parity` 单独 4 passed；`npx biome check` 3 文件 exit 0（顺手删掉未使用的 `requireTrimmedString`，免得 `--error-on-warnings` 在 `npm run check` 里翻车）；`npx tsgo --noEmit` exit 0。
  **D-313/遗留 R-6**：`path_roots_file` 故意不 trim —— Python 字段 strip 而 digest 用未 strip 串，保持原值可让两侧 digest 同为 `None`；残留差异交 T-5 实测确认并写进 achieved.md。
- 2026-09-23 12:3x T-5 派发（delta 独立验证，含 R-6 实测与 4 条反例）。
- 2026-09-23 12:4x T-5 done（PASS，73 行报告）。四条反例全红：A `optionalTrimmedString`→`optionalString`（2 red）、
  **B `--project=${projectDir}`→`--project=.` 由新增 VC-308b 打红**（T-4 时此反例全绿，缺口闭合）、C 门控回退（VC-310 red）、D canonical 键改名（`rag-parity` 4 red）；反例改动全部 sha256 复原。
  零回归：rag 14 文件 127 passed、`agent-team-loop*` 178 passed、Python 839 passed/9 deselected、`npm run check` exit 0（biome `Checked 1082 files`）、fixture+`test_autopilot_l0.py` 零 diff、golden `00f85e64…4035`。
  **R-6 实测（第三方）**：padding `path_roots_file` 下 TS≠Python，且把 TS 该键手动 trim 后重算即与 Python 逐字节相等 ⇒ 差异**仅**来自该键（不是别处漂移）；无 padding 对照两侧相同。
- 2026-09-23 12:5x 质检欠债闭合（Q-AC-303 / Q-X-04 / Q-X-09 / Q-X-10）：新增 `rag-window-missing-mw.test.ts`（mock `node:fs` → `ok=false code=-1 hint_has_MW_PY=true`）、`RAG_SUBCOMMANDS == mw.py _RAG_ACTIONS` 断言（`equal=true`）、spec/design 回写（AC-304 门控、D-311~313、VC-305b/308b/309b、覆盖矩阵）、CHANGELOG Added/Fixed 各一条；`rag-window`+`rag-trim-parity`+`rag-window-missing-mw`+`rag-parity`+`rag-config` = 5 文件 44 passed；`npm run check` exit 0；`check_mermaid.py` PASS；`audit_phase.py` VERDICT: PASS。写 achieved.md 后推进 done。
- 2026-09-23 12:4x 推进 `execute -> verify`（audit PASS），派发合入前质量门禁 worker（默认怀疑立场，要求独立复跑 ≥3 条命令并尝试推翻 PM 结论）。
