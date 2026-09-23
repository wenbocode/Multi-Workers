# Quality Gate Report: mw-rag-window-parity

- **时间**: 2026-09-23T12:47:28+08:00
- **触发**: 合入前全量质检（Stage 3 完成后，PM 请求独立 QG）
- **范围**: 全量 AC-301~AC-306 / VC-301~VC-312（+ delta VC-305b/VC-308b/VC-309b）
- **质检者**: 独立 coding worker（默认怀疑立场；对「声称通过」逐条找证据）
- **基准**: spec.md / design.md / plan.md / tasks T-1~T-5 / evidence/verify-run-2026-09-23.md（T-4）/ evidence/verify-run-delta-2026-09-23.md（T-5）
- **唯一写入**: 本报告。仓内源码/测试/文档/配置 0 写入（见 §6 sha256 复核）
- **方法**: `.agents/skills/agentic-task/references/workflow-quality-gate.md` Step 1~5

## 0. 前置门禁

| 检查项 | 结果 | 说明 |
|---|---|---|
| spec.md 存在 AC 编号 | ✅ | `spec.md:48-53` AC-301~AC-306 |
| design.md 存在 VC 编号 | ✅ | `design.md:68-77` VC-301~VC-312 |
| AC→VC 映射覆盖 100% | ✅ | `design.md:79` 覆盖矩阵；AC-301~306 全部有 VC |
| `evidence-requirement.md` 存在 | ⚠️ | **缺失**（任务书已声明该 key 无 L1/L2 充分性标准目录）。因此无 `ac_fingerprint` 可校验，Step 3 的「充分性判定标准」改用 spec §4（证据要求）与 design §5（VC 断言）代替 |
| `evidence/baseline/` 非空 | ⚠️ | **缺失**（同上）。PASS 基线只能取自 T-4/T-5 报告与本次独立复跑，不能取框架基线 |
| 每个 task 有非空 ac_refs/vc_refs | ✅ | `tasks/T-1..T-5` 均非空 |
| 无 open Error Fingerprint | ✅ | 无 task 报告 open 错误；T-4/T-5 结论 PASS |
| 与代码一致性抽查 ≥6 条 | ✅ | 见 §3.4 一致性抽查表（10 条） |

> 前置门禁未导致中止：缺失的 L2 目录按任务书判 ⚠️ 并说明，不视为 ❌。

## 1. Step 2 问题清单生成（机械推导）

- 来源 A（spec AC）：6 条 → Q-AC-301..306
- 来源 B（design VC）：15 条 → Q-VC-301..312 + Q-VC-305b / Q-VC-308b / Q-VC-309b（T-3C/T-3B delta VC）
- 来源 C（design 覆盖矩阵每行）：6 条 → Q-COV-301..306
- 来源 D（交叉，PM 主动推导 + 本 QC 追加）：11 条 → Q-X-01..11

合计 **38 条**。

## 2. 问题清单与核查结果 — AC

| 问题 ID | 描述 | 状态 | 证据引用（file:line / 命令输出） | 备注 |
|---|---|---|---|---|
| Q-AC-301 | TS `skill.dir` 缺省/`null` 合法、`dir:""` 非法、显式值按控制工作区解析、`transport: skill` 缺 `cli_entry` 报 `skill-missing-cli` | ✅ 充分 | `[VERIFY] VC-301: dir=null parse=ok` / `VC-302` 同（`test/suite/rag-window.test.ts:86,94`）；`VC-303: dir="" kind=invalid-shape mentions_skill_dir=true`（`:109`）；`VC-304: null_to_root=true`（`:120`）；`skill-missing-cli` 由既有 `test/suite/rag-config.test.ts:223` 覆盖。实现：`rag/config.ts:94,171-172,277`；`rag/tools.ts:740,754` | `skill-missing-cli` 无本 key 的 `[VERIFY]` 行（既有断言覆盖）；`dir:""` 边界正确（`optionalString`→`requireString`） |
| Q-AC-302 | `dir` 三变体下 TS `ragFingerprint` == Python `rag_fingerprint`，且 `mw rag list --json` 与 TS 的 `skill.dir`/`timeout_ms` 语义一致，golden 不变 | ✅ 充分 | `[VERIFY] VC-305: dir=default parsed=null ts==py prefix=5e9bfc0055eb \| dir=null … 5e9bfc0055eb \| dir=explicit parsed=skills/x ts==py prefix=2998c51ff849`（`rag-parity.test.ts:366-395`）；`VC-305b` 两组 padding `ts==py=true`（`rag-trim-parity.test.ts:145,160`）；VC-027 `golden_byte_match=true fingerprint_match=true`；golden sha `00f85e64…4035` | 本 QC 独立复跑 `mw rag list --json` vs TS：S1/S2/S3 的 `skill.dir` 与 `skill/mcp.timeout_ms` **全部相等**（§4 E-AC302）；payload 未归一化（`rag/config.ts:690-707`） |
| Q-AC-303 | `/mw rag <sub>` 转发控制工作区、exit 0/1/2→info/warning/error、未知名打印用法且不调 CLI、`mw.py` 缺失给 MW_PY 提示 | ⚠️ 不足 | UC-306/307/308/308b 全绿（§4 原文）；本 QC 端到端：未知/空 sub **未 spawn**（哨兵文件缺失）、真实 `mw.py rag list` exit 0、`formatRagOutput(out,-1).level=error` 且含 MW_PY。**缺口**：`findMwPy()===null` 分支（`shared/mw-runner.ts:451-452,508-510`）无任何测试；`/mw`→`runMwRagCommand` 接线（`pm/ui-bridge.ts:2034`）仅代码直读，无 handler 级测试 | 功能实现正确，缺 2 项证据（非缺陷） |
| Q-AC-304 | `/mw doctor` RAG 行三种形态且与终端逐字一致；旧 mw.py 无 `rag` 键时不出现且不崩 | ✅ 充分 | `[VERIFY] VC-309` 三组 ts=py（`rag-window.test.ts:342`）；`VC-309b: empty_py_row=false empty_ts_row=false configured_py_row=true configured_ts_row=true`（`:366`）；`VC-310` 三行（`:378,390,403`）；旧 mw.py 分支由 VC-310 `{}` 用例覆盖。本 QC 5 组 section 直比 → `ALL_EQUAL:true`（§4 E-RENDER） | 实现门控 `exists===true \|\| enabled.length>0`（`pm/ui-bridge.ts:1484`）比字面 AC-304 更严，以镜像 `mw.py:523`；基线文档未同步 → Q-X-09 |
| Q-AC-305 | `/mw` 帮助含 `rag`，参数构造与 doctor RAG 行渲染为导出函数并被测试覆盖 | ✅ 充分 | `[VERIFY] VC-311: mw_description_has_rag=true`（`rag-window.test.ts:237`，注册处 `pm/ui-bridge.ts:1902` 引用同一常量）；`parseRagArgs`/`formatRagOutput` 导出纯函数（`:1850,1866`）；argv 拼接由 VC-308b 真 spawn 钉住 | 无缺口 |
| Q-AC-306 | 零回归 + 所有 `[VERIFY]` 可复现 | ✅ 充分 | 本 QC 独立跑：`npm run check` **EXIT=0**；rag 14 文件 **127 passed**；`agent-team-loop*` 2 文件 **178 passed**；`pytest -q` **839 passed, 9 deselected**；fixture+`test_autopilot_l0.py` `git diff` **空**；golden sha 匹配（§4） | 与 T-4/T-5 数字逐字一致 |

## 3. 问题清单与核查结果 — VC / COV / 交叉

### 3.1 VC（design `design.md:68-77` + delta）

| 问题 ID | 断言 | 状态 | 证据引用（发射位置 / 实测行原文） | 强度备注 |
|---|---|---|---|---|
| Q-VC-301 | 缺省 `dir`→`null` | ✅ | `rag-window.test.ts:86` `[VERIFY] VC-301: dir=null parse=ok` | 强（T-4 反例 A 变红；本轮复跑绿） |
| Q-VC-302 | `dir: null`→`null` | ✅ | `rag-window.test.ts:94` `[VERIFY] VC-302: dir=null parse=ok` | 强 |
| Q-VC-303 | `dir:""`→`invalid-shape` 且指 `skill.dir` | ✅ | `:109` `[VERIFY] VC-303: dir="" kind=invalid-shape mentions_skill_dir=true` | 强 |
| Q-VC-304 | `resolveCliDir(null)=root`；显式值 `path.resolve` | ✅ | `:120` `[VERIFY] VC-304: null_to_root=true explicit=…\skills\x`；实现 `rag/tools.ts:740`，`cliCall:754` | 强 |
| Q-VC-305 | 三变体 fingerprint TS==Python（真子进程） | ✅ | `rag-parity.test.ts:395` `[VERIFY] VC-305: … ts==py …` | 强；空白边界由 VC-305b 补 |
| Q-VC-305b | 4 字段按 Python `.strip()` 且 fingerprint 逐字相等；空白值双侧拒绝 | ✅ | `rag-trim-parity.test.ts:145,160,178` 三条 `[VERIFY] VC-305b`（本轮复跑原文一致） | 强（反例 A 打红 2 例） |
| Q-VC-306 | `parseRagArgs` 已知/未知/空 | ✅ | `rag-window.test.ts:162` `[VERIFY] VC-306: list=… audit=… bogus=usage(all_5=true)` | 强 |
| Q-VC-307 | 未知/空 sub 不调 CLI | ✅ | `:188` `[VERIFY] VC-307: unknown_sub_runner_calls=0 usage_notices=3`；本 QC 注入真 stub 哨兵再证（§4 E-NOSPAWN） | 强（注入桩 + 真 spawn 双证） |
| Q-VC-308 | 0/1/2→info/warning/error；>30 行截断+提示 | ✅ | `:211,227` `level0/1/2=info/warning/error`；`truncated_lines=31 hint_present=true exact30_intact=true` | 强 |
| Q-VC-308b | 真 spawn argv=`[rag,<sub>,...,--project=<root>]` 且 exit 1 保留 | ✅ | `:440` `[VERIFY] VC-308b: argv0=[…] argv1_code=1 ok0=true ok1=false`；实现 `mw-runner.ts:450-453` | 强（反例 B 现红，闭合 T-4 发现 1） |
| Q-VC-309 | `formatRagDoctorLine` == `mw.py doctor` 文本行（三组） | ✅ | `:342` `[VERIFY] VC-309: not-enabled[…][config-error…][enabled-unreachable…]` 三组 ts=py=true | 强；多服务器/required_missing 由 E-RENDER 补（含 `required_missing=2`） |
| Q-VC-309b | 无 RAG 配置项目两侧都不打 `rag:` 行 | ✅ | `:366` `empty_py_row=false empty_ts_row=false configured_py_row=true configured_ts_row=true` | 强（真实 mw.py 文本双侧）；仅测谓词，行渲染由 VC-310 钉 |
| Q-VC-310 | 无 `rag` 不出现行且不抛；有 `rag` 恰好一行 | ✅ | `:378,390,403` 三条 `[VERIFY] VC-310`（`rag_rows=1 line="rag: not enabled (skill unknown)"`） | 强（反例 C/D 分别打红不同断言） |
| Q-VC-311 | `/mw` description 含 `rag` | ✅ | `:237` `[VERIFY] VC-311: mw_description_has_rag=true` | 强（注册处引用同一常量） |
| Q-VC-312 | 零回归 | ✅ | 见 Q-AC-306（本 QC 全部独立复跑） | 强 |

### 3.2 覆盖矩阵行（`design.md:79`）

| 问题 ID | 矩阵行 | 状态 | 证据引用 |
|---|---|---|---|
| Q-COV-301 | AC-301 ← VC-301~304 | ✅ | §3.1 四条全绿 |
| Q-COV-302 | AC-302 ← VC-305 | ✅ | VC-305 + VC-305b + VC-027 + E-AC302 |
| Q-COV-303 | AC-303 ← VC-306~308 | ✅ | VC-306/307/308 + VC-308b + E-NOSPAWN（子句证据缺口见 Q-AC-303） |
| Q-COV-304 | AC-304 ← VC-309/310 | ✅ | VC-309/309b/310 + E-RENDER |
| Q-COV-305 | AC-305 ← VC-311 | ✅ | VC-311 |
| Q-COV-306 | AC-306 ← VC-312 | ✅ | 本 QC 全量复跑 |

### 3.3 交叉问题

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-X-01 | 窗口 RAG 行与终端 `rag:` 行一致 | ✅ | VC-309/309b + §4 E-RENDER（5 组 section 直比 `ALL_EQUAL:true`） | — |
| Q-X-02 | 非 RAG 项目零影响（无行/无工具/无 I/O） | ✅ | VC-309b/310；`loadRagConfig` 无文件→空 enabled（`rag/config.ts:544-546`）；Python 839 + 扩展 178 全绿 | — |
| Q-X-03 | pi 核心未改 | ✅ | `git diff --name-only -- packages/coding-agent/src/core` **空**；dist 未由本 key 重建 | — |
| Q-X-04 | `RAG_SUBCOMMANDS` 与 `mw.py _RAG_ACTIONS` 漂移 | ⚠️ | 当前集合相等（本 QC 实测 `set_equal=True / order_equal=False`；`mw.py:2239-2245` vs `mw-runner.ts:497`），但**无自动一致性断言**（`spec.md:§9` 允许记为遗留） | 漂移只能人工发现 |
| Q-X-05 | `sources`/role `server`/`default_server` 不被误统一 trim | ✅ | Python 原样存（`mw_common.py:639,682,688,762`），TS 同样不 trim（`rag/config.ts:203,483-485,562`）；D-312 取舍成立 | — |
| Q-X-06 | `/mw rag init` 写盘副作用 | ⚠️ | 已声明遗留：窗口内未人工跑过（T-5 §5） | — |
| Q-X-07 | 真实 RAG 服务联调 | ⚠️ | 已声明遗留：仅不可达端口 `127.0.0.1:19999`（T-5 §5） | — |
| Q-X-08 | R-6 `path_roots_file` padding 语义不一致 | ⚠️ | 已声明遗留 + 本 QC 独立复现（§4 E-R6）：TS `d5b017c6…` ≠ PY `9ed001e4…`；仅 trim 该键后 TS==PY；无 padding 时两侧相等 | 差异仅该键，已实证 |
| Q-X-09 | T-3B 门控改动未同步基线文档 | ⚠️ | `spec.md:51` AC-304 / `design.md:27` D-308 / `:75` VC-310 仍写「`report.rag` 存在即插行」，实现为 `exists\|\|enabled`（`pm/ui-bridge.ts:1484`）；T-3B/T-3C 为 PM 直执，无 task 文件，VC-305b/308b/309b 未登记进 design.md | 可追溯性欠债 |
| Q-X-10 | CHANGELOG `[Unreleased]` 无本 key 条目 | ⚠️ | `findstr /C:"mw-rag-window-parity" /C:"skill.dir" /C:"/mw rag"` 两个 CHANGELOG 均无匹配 | AGENTS.md 要求用户可见变更入 Unreleased |
| Q-X-11 | pi TUI 手工操作 | ⚠️ | 已声明遗留：未在 tmux/真 TUI 敲 `/mw rag`、`/mw doctor`（T-5 §5） | — |

### 3.4 一致性抽查（独立挑取的可证伪断言，≥6 条）

| # | 断言 | 依据（file:line / 实测） | 符合？ |
|---|---|---|---|
| 1 | `RagSkillEntry.dir` 可表达 `null` | `rag/config.ts:94` `dir: string \| null`；VC-301/302 编译+通过 | ✅ |
| 2 | `dir:""` 错误文本包含 `skill.dir` | `rag/config.ts:164-169`（`requireString`）→ `"…skill.dir must be a non-empty string"`；VC-303 | ✅ |
| 3 | `RAG_SUBCOMMANDS` 与 `mw.py _RAG_ACTIONS` 同集 | 本 QC `whitelist.py`：`set_equal=True`；`mw-runner.ts:497` vs `mw.py:2239-2245` | ✅（顺序不同，仅集合敏感） |
| 4 | `formatRagDoctorLine` fingerprint 截前 12 位 | `pm/ui-bridge.ts:1470` `.slice(0,12)` vs `mw.py:2297-2316` `[:12]`；E-RENDER 实测 `4e005104436e` 12 字符 | ✅ |
| 5 | 输出截断阈值 = 30 行 | `pm/ui-bridge.ts:1836` `RAG_OUTPUT_MAX_LINES=30`、`:1871`；VC-308 `truncated_lines=31 exact30_intact=true` | ✅ |
| 6 | `/mw` description 含 `rag` 且注册处引用同一常量 | `pm/ui-bridge.ts:1831-1832`、`:1902`；VC-311 | ✅ |
| 7 | `runMwCliRaw` 把 `--project=<projectDir>` 拼入 argv | `shared/mw-runner.ts:453`；VC-308b 真 spawn argv | ✅ |
| 8 | `shouldShowRagDoctorRow` 镜像 `mw.py:523` 的 `exists or enabled` 门 | `pm/ui-bridge.ts:1484-1486`；VC-309b 双侧实测 | ✅（与字面 AC-304/D-308 不一致 → Q-X-09） |
| 9 | `optionalTrimmedString` 恰好用于 Python `.strip()` 的 4 个字段，`path_roots_file` 有意不 trim | `rag/config.ts:181,263,267,277,278` vs `:379`；`mw_common.py:541-542,564-565,635-636`；VC-305b + E-R6 | ✅（除 R-6 键，已声明） |
| 10 | `transport: skill` 缺 `cli_entry` 仍报 `skill-missing-cli` | `rag/config.ts:279`；既有测试 `rag-config.test.ts:223` | ✅ |

## 4. 本 QC 独立复跑（≥3 条关键命令，均为本次实测）

| # | 命令（在 `packages/coding-agent` 或仓根执行） | 原始结果 |
|---|---|---|
| 1 | `node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-window.test.ts test/suite/rag-trim-parity.test.ts test/suite/rag-parity.test.ts test/suite/rag-config.test.ts test/suite/rag-tools.test.ts` | `Test Files 5 passed (5)` / `Tests 52 passed (52)`；`[VERIFY]` 行原文与 T-4/T-5 一致（仅临时路径不同，如 `VC-304 explicit=…\Temp\mw-rag-window-dir-uMP6oC\skills\x`） |
| 2 | 同 #1 扩到 T-5 任务书的 14 个 rag 文件 | `Test Files 14 passed (14)` / `Tests 127 passed (127)` |
| 3 | `… --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-output.test.ts` | `Test Files 2 passed (2)` / `Tests 178 passed (178)` |
| 4 | 仓根 `npm run check` | `Checked 1082 files … No fixes applied.`；pinned-deps/ts-imports/shrinkwrap/install-lock/tsgo/browser-smoke 全过；**EXIT=0** |
| 5 | `cd packages/multi-workers && python -m pytest -q` | `839 passed, 9 deselected in 86.59s` |
| 6 | `npx biome check` 4 源文件 + 2 新测试 | `Checked 6 files in 28ms. No fixes applied.`（0 诊断） |
| 7 | `git diff --stat -- packages/multi-workers/test/fixtures packages/multi-workers/test_autopilot_l0.py`；`git diff --name-only -- packages/coding-agent/src/core` | 两者均**空** |
| 8 | `hashes.py`（temp，逐文件 sha256） | 9 个受控文件哈希与 T-5 §1 基线**逐字相等**（`rag/config.ts 4e6185fe…`、`rag/tools.ts ab031102…`、`mw-runner.ts f061957c…`、`ui-bridge.ts 147d6e9c…`、`rag-window.test.ts 845b8943…`、`rag-trim-parity.test.ts 5164061d…`、`mw.py e38668c5…`、`mw_common.py f2a5369e…`、golden `00f85e646e30…4035`）→ 反例改动确已复原 |
| 9 | `whitelist.py`（temp） | `py _RAG_ACTIONS: ['init','list','probe','audit','sync']`；`ts RAG_SUBCOMMANDS: ['list','probe','audit','sync','init']`；`set_equal: True \| order_equal: False` |
| E-RENDER | `tsx %TEMP%/mw-rwp-qg/render_cmp.mts`（5 组 section：error / not-enabled / 双服务器排序+`required_missing=2` / 空 probe+null fingerprint / 正常） | 5/5 `ts==py=true`，`ALL_EQUAL: true`（例：`rag: enabled=B, A; probe=A=reachable, B=unreachable; fingerprint=4e005104436e; skill=installed; required_missing=2` 两侧逐字相同） |
| E-R6 | `tsx %TEMP%/mw-rwp-qg/r6.mts`（padding `path_roots_file`） | `[padded] TS` `"pathRootsFile":" .mw/rag-roots.json "`、digest `null`、fingerprint `d5b017c6…`；`[padded] PY` 字段 `".mw/rag-roots.json"`、digest `null`、fingerprint `9ed001e4…`；`fingerprint_equal false`；只 trim 该键后 `9ed001e4…` == PY；`[clean] fingerprint_equal true` |
| E-NOSPAWN | `tsx %TEMP%/mw-rwp-qg/nospawn.mts`（默认 runner + `MW_PY` 指向写哨兵的 stub） | `unknown_spawned_stub: false`（未知/空 sub 未调 CLI）；`level_for_code2: error`；`level_for_code-1: error has_mw_py_hint: true` |
| E-REALCLI | `tsx %TEMP%/mw-rwp-qg/real_cli.mts`（真实 `mw.py`） | `real mw.py rag list -> code: 0 ok: true`，输出含 `[mw rag] fingerprint: e527406e5021…`；`list --json` 亦 `code: 0`（与 VC-309 的 `fingerprint=e527406e5021` 前缀一致） |
| E-AC302 | `tsx %TEMP%/mw-rwp-qg/listcmp.mts` | `S1: dir_equal=true skill_timeout_equal=true mcp_timeout_equal=true`；`S2` 同（`dir="skills/x"`）；`S3` 同 → 关闭 AC-302 的 `mw rag list --json` 子句 |

> 实验脚本/fixture 全部写在 `%TEMP%`（仓外）。**本 QC 未跑反例试验**：任务书红线「不改任何源码/测试」禁止临时改文件；但 T-4/T-5 的「sha256 复原」声明已被上表 #8 独立证实（9 文件哈希与声明基线一致），故未复原风险不存在。

## 5. 汇总与结论

- **总问题数**: 38（AC 6 / VC 15 / COV 6 / 交叉 11）
- **通过（充分）**: 30（78.9%）
- **有条件通过（不足）**: 8 —— Q-AC-303、Q-X-04、Q-X-06、Q-X-07、Q-X-08、Q-X-09、Q-X-10、Q-X-11
- **未通过（无证据）**: 0

**质检结论**: ⚠️ **有条件通过（欠债 8 项，0 项 ❌）**

判据：无功能缺陷证据；8 项欠债中 4 项为任务书已声明的遗留（Q-X-06 `init` 写盘、Q-X-07 真实服务、Q-X-08 R-6、Q-X-11 TUI 手工），4 项为本轮新发现的证据/文档/流程欠债（Q-AC-303 的两处未测分支、Q-X-04 无漂移断言、Q-X-09 基线文档未同步、Q-X-10 无 CHANGELOG 条目）。建议合入前补齐 Q-AC-303/Q-X-09/Q-X-10（低成本），其余记为 achieved.md 的验证欠债。

## 5.1 欠债行动计划

| 问题 | 根因 | 所需动作 | 负责 |
|---|---|---|---|
| Q-AC-303 | `mw.py` 缺失分支不可达 + 接线无 handler 级测试 | 加一条单测：注入 `findMwPy` 桩返回 null（或断言 `ragMw` 的 spawnError 文本）→ 断言 `formatRagOutput` 级为 error 且含 `MW_PY`；并把 `/mw rag` 分支纳入 `agent-team-loop.test.ts` 的 handler 调用 | PM/后续 key |
| Q-X-04 | 白名单跨语言一致性无自动断言 | 加一条测试读 `mw.py _RAG_ACTIONS` 的 keys 与 `RAG_SUBCOMMANDS` 比集合（低成本） | 后续 key |
| Q-X-06 | 未人工验证 `/mw rag init` 落盘 | 在 tmux 真 TUI 跑 `/mw rag init`（或至少经 `runMwRagCommand` 真 CLI 跑 `init`）并核对 `.mw/rag-servers.yml` | PM |
| Q-X-07 | 真实 RAG 服务未联调 | 接到真实服务后跑 `probe`/`list_sources`；本 key 不阻塞 | 后续 key |
| Q-X-08 | `path_roots_file` 两侧 strip/digest 语义分裂 | 另开 key 定方向：两侧都不 strip，或 digest 也用 strip 后串（后者改 fingerprint 语义需评估） | 后续 key |
| Q-X-09 | T-3B/T-3C 未同步 spec/design | 更新 `design.md:27` D-308、`:75` VC-310，登记 D-311~D-313/VC-305b/308b/309b，并在 spec.md:51 AC-304 补一句「与 `mw.py:523` 同门」 | PM |
| Q-X-10 | 无 CHANGELOG 条目 | 补 `packages/coding-agent/CHANGELOG.md` `[Unreleased]`（`/mw rag`、`/mw doctor` RAG 行、`skill.dir` parity） | PM |
| Q-X-11 | pi TUI 手工操作未跑 | 合入前 tmux 冒烟 `/mw rag list`、`/mw doctor` | PM |

## 5.2 二次印证结论

- **检查 1（spec 每条约束）**：`spec.md:§5` 逐条——不改 `core/**`/dist：✅（`git diff --name-only -- src/core` 空；dist 无本 key 证据可分离，工作区改动归属其它会话）；不动 `mw.py`/`mw_common.py`：✅（哈希与 T-5 基线一致）；不触碰其它会话文件：✅（写入面=4 源+3 测试+本报告，见 design §6）；不提交：✅（HEAD 仍 `0c7754086`）；工具白名单 coding：✅（tasks `type: coding`）。
- **检查 2（Function Flow 节点→Q）**：`parseRagArgs`→Q-VC-306/307；`ragMw`/`runMwCliRaw`→Q-VC-308b；真实 CLI→§4 E-REALCLI；`formatRagOutput`→Q-VC-308；`parseSkill`/`optionalTrimmedString`→Q-VC-301/302/303/305b；`resolveCliDir`→Q-VC-304；`ragFingerprint`→Q-VC-305；`/mw doctor`+`formatRagDoctorLine`→Q-VC-309/310。**无未映射节点**。
- **检查 3（覆盖矩阵异常路径）**：`design.md:79` 只有 AC↔VC 行、无独立异常路径行 → 无遗漏；异常分支（error / 空 enabled / 多服务器+`required_missing` / 旧 mw.py 无 `rag`）分别由 Q-VC-309/309b/310/E-RENDER 覆盖。
- **检查 4（空 vc_refs）**：无空绑定。但 T-3B/T-3C 为 PM 直执、无 task 文件，`VC-305b/308b/309b` 只存在于测试与证据报告、未登记进 design.md（计入 Q-X-09）。
- 附带发现（process，不计费）：`pm-state.md:§2` 有重复的 `T-4-VERIFY | 3 | pending` 行（笔误）。

## 6. 未执行项与限制声明

- 未由本 QC 复跑反例 A/B/C/D（红线禁止临时改源码）；改以 sha256 复核 T-4/T-5 的复原声明（§4 #8，9 文件全部匹配）。
- 未做真实 RAG 服务联调、未启动 `mw serve` 跑端到端 worker、未在 pi TUI 人工敲 `/mw rag`/`/mw doctor`（与 T-5 §5 声明一致）；本 QC 只验证代码路径、纯函数与真子进程。
- 未验证 `/mw rag init` 的实际落盘结果（只验证了 argv 转发与 exit code）。
- 未审 pi 窄通知通道下的中文换行/宽度。
- Python 只跑了 `packages/multi-workers`；未重跑 `packages/agent`（Windows 已知 89 条环境基线与本 key 无关）。
- `mw.py` 缺失分支在本仓布局下不可达（`findMwPy` 会回落到 repo 相对路径），故只能以代码 + 纯函数证据判定（Q-AC-303）。

### sha256 复核（本报告写入前后一致，证明除报告外零写入）

```
rag/config.ts            4e6185fea53a7186724c3a275a0de578b29203d981e0618e0835af903177bad9
rag/tools.ts             ab031102cb60e0a5f61ccf138b324a25780deb602df6043b2b71463fec2e79a0
shared/mw-runner.ts      f061957cf6d9af648edf1e42ac7ad040cb95fb7521c08a4355c904b02936c6a0
pm/ui-bridge.ts          147d6e9cb2b22acc0bdc22a6640491671e3b008c559260cb30ec7c642384c4ca
rag-window.test.ts       845b8943f9659bfaa9ee026e8e8e18217fbdbe97294a9f2c157f1bc840d31535
rag-trim-parity.test.ts  5164061dfda751aaafbe50e634b88e383ddc2a2ceca60ddca49902630c4a4d6f
mw.py                    e38668c57b27bc8a6f66d21297902c1eb8426bd9831471276399467667170b72
mw_common.py             f2a5369e912ee75ae29f2bea17eadb27d41fa8d08637c9ebd2e71197ad29d4ab
rag-block.golden.md      00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035
```

本报告为本次质检唯一写入；未 commit。


