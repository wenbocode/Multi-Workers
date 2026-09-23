# verify-run-2026-09-23 — mw-rag-window-parity T-4 独立验证

> 结论：**PASS（附 3 项发现，无阻塞）**。VC-301~VC-312 全部有实测行；反例 A/C/D 均变红（A 红 VC-301/302、C/D 红 VC-310），反例 B（`--project=.`）**不变红**——`runMwCliRaw` 的 `--project=` 拼接无测试钉住（报告 §3/§4）。E-4 补充实验实测 TS==Python 逐字相等（含 probe 多服务器排序与 `required_missing=1`）。另发现一项既有 parity 边角不符：Python 对 `skill.dir`/`cli_entry` 做 `.strip()`，TS 不做，导致空白填充值下 fingerprint 不等（§4，非本 key 引入，未修）。

- key: `mw-rag-window-parity` / task `T-4-VERIFY`
- 验证者: 独立 coding worker（第三方视角）
- 基准 commit: `0c7754086`（工作区含多会话未提交改动，见 §5）
- 允许写的唯一文件: 本报告。反例实验临时改源码，均已 sha256 复原（§3）。

## §0 复现命令表（全部在仓根或指定目录执行）

| # | 命令 | 目的 | 结果 |
|---|---|---|---|
| 0 | `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-window.test.ts` | VC-301~311 主套件 | 1 file / **16 passed** |
| 1 | `node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-config.test.ts test/suite/rag-parity.test.ts test/suite/rag-tools.test.ts test/suite/rag-required.test.ts test/suite/rag-role-defaults.test.ts test/suite/rag-evidence.test.ts` | parity/tools/required 回归 | 6 files / **55 passed**（含 VC-305） |
| 2 | `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-output.test.ts` | 扩展回归 | 2 files / **178 passed** |
| 3 | `cd packages/multi-workers && python -m pytest -q` | Python 零回归 | **839 passed, 9 deselected** |
| 4 | 仓根 `npm run check` | biome+pinned-deps+ts-imports+shrinkwrap+tsgo+browser-smoke | **EXIT=0** |
| 5 | `git diff --stat -- packages/multi-workers/test/fixtures packages/multi-workers/test_autopilot_l0.py` | fixture/golden 零 diff | **空** |
| 6 | `node -e` sha256 golden | golden 字节锚点 | `00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035`（= spec 的 `00f85e64…4035`） |
| 7 | `git status --porcelain` / `git diff --stat` | 改动面归属 | 见 §5 |
| E4 | `node node_modules/tsx/dist/cli.mjs %TEMP%/mw-rwp-e4/e4.mts` | 补充实验 E-4（真 fixture + mock MCP） | TS==PY（§4.1） |
| WS | `node node_modules/tsx/dist/cli.mjs %TEMP%/mw-rwp-e4/whitespace.mts` | 空白 parity 抽查 | fingerprint **不等**（§4.2） |

> 说明：`tsx` 脚本写在 `%TEMP%`（仓外），仅在 fixture 里运行 `mw.py`/`loadRagConfig`，不改仓内文件。
> 反例命令见 §3。

## §1 VC 汇总表（VC-301~VC-312）

| VC | 断言摘要 | 发射位置 | 实测行原文（截断） | 证据强度 |
|---|---|---|---|---|
| VC-301 | 缺省 `skill.dir` → `null` 且解析成功 | `rag/config.ts:266`（`optionalString`） | `[VERIFY] VC-301: dir=null parse=ok` | 强（反例 A 变红） |
| VC-302 | `dir: null` → `null` | `rag/config.ts:266-267` | `[VERIFY] VC-302: dir=null parse=ok` | 强（反例 A 变红） |
| VC-303 | `dir: ""` → `invalid-shape` 且指 `skill.dir` | `rag/config.ts:164-169`（`requireString`） | `[VERIFY] VC-303: dir="" kind=invalid-shape mentions_skill_dir=true` | 强 |
| VC-304 | `resolveCliDir(null)=root`；显式值 `path.resolve` | `rag/tools.ts:740`、`cliCall:754` | `[VERIFY] VC-304: null_to_root=true explicit=…\Temp\mw-rag-window-dir-S745dh\skills\x` | 强 |
| VC-305 | 三变体 TS fingerprint == Python（真子进程） | `rag/config.ts:676-700` | `[VERIFY] VC-305: dir=default parsed=null ts==py prefix=5e9bfc0055eb \| dir=null … 5e9bfc0055eb \| dir=explicit parsed=skills/x ts==py prefix=2998c51ff849` | 强（但空白边界不符，§4.2） |
| VC-306 | `parseRagArgs` 已知/未知/空 sub | `pm/ui-bridge.ts:1850` | `[VERIFY] VC-306: list={"sub":"list","rest":[]} audit={"sub":"audit","rest":["--key","K"]} bogus=usage(all_5=true)` | 强 |
| VC-307 | 未知/空 sub 不调 CLI | `pm/ui-bridge.ts:1879-1896` | `[VERIFY] VC-307: unknown_sub_runner_calls=0 usage_notices=3` | 强（注入 runner 计数桩） |
| VC-308 | 0/1/2→info/warning/error；>30 行截断+提示 | `pm/ui-bridge.ts:1866-1873` | `[VERIFY] VC-308: level0=info level1=warning level2=error` / `truncated_lines=31 hint_present=true exact30_intact=true` | 强 |
| VC-309 | `formatRagDoctorLine` == `mw.py doctor` 文本 `rag: ` 行（三组） | `pm/ui-bridge.ts:1460-1475` | `[VERIFY] VC-309: not-enabled[ts=py=true]"rag: not enabled (skill absent)" \| config-error[ts=py=true]"rag: ERROR - …" \| enabled-unreachable[ts=py=true]"rag: enabled=S; probe=S=unreachable; fingerprint=e527406e5021; skill=absent"` | 强（单服务器）；**多服务器/required_missing 原未盖，E-4 已补**（§4.1） |
| VC-310 | 无 `rag` 不出现行且不抛；有 `rag` 恰好一行 | `pm/ui-bridge.ts:1568` | `[VERIFY] VC-310: no_rag_row=true lines=4` / `gate_absent=false gate_inert=false gate_exists=true gate_enabled=true rows=0` / `rag_rows=1 line="rag: not enabled (skill unknown)"` | 强（反例 C、D 均变红） |
| VC-311 | `/mw` description 含 `rag` | `pm/ui-bridge.ts:1831-1832`、注册 `:1902` | `[VERIFY] VC-311: mw_description_has_rag=true` | 强（导出常量 + 注册处引用同一常量） |
| VC-312 | `npm run check` exit 0；TS/Python 无新增失败；fixture/golden 零 diff | 见 §0 / §5 | `npm run check` **EXIT=0**；`839 passed, 9 deselected`；`git diff` **空** | 强 |

补充（T-3B 新增，不属于 VC-301~312 编号）：

| 条件 | 断言 | 发射位置 | 实测行 | 证据强度 |
|---|---|---|---|---|
| VC-309b | 无 RAG 配置项目两侧都不打 `rag:` 行（门控镜像 `mw.py:523`） | `pm/ui-bridge.ts:1484`、`:1568` | `[VERIFY] VC-309b: empty_py_row=false empty_ts_row=false configured_py_row=true configured_ts_row=true` | 强（谓词直接单测）；注意反例 D 时 VC-309b **不红**，红的是 VC-310（§3-D） |

## §2 逐 VC 明细

**VC-301 / VC-302** — 发射位置 `rag/config.ts:266-268`（`parseSkill` 用 `optionalString(raw.dir, …)`；`RagSkillEntry.dir: string | null` 在 `:94`；payload `:692` 保留 `null`）。实测（`rag-window` 同一次运行）：
```
[VERIFY] VC-301: dir=null parse=ok
[VERIFY] VC-302: dir=null parse=ok
```
证据强度：强。反例 A（把 `optionalString` 改回 `requireString`）使两者同时红，证明断言非装饰（§3-A）。

**VC-303** — `rag/config.ts:164-169` `requireString` 对 `trim()===""` 报 `invalid-shape`，字段名 `server 'S'.skill.dir`。实测：`[VERIFY] VC-303: dir="" kind=invalid-shape mentions_skill_dir=true`。强度：强（反例 A 未影响它，说明它与 `optionalString` 的行为边界确实分开；若把 `""` 当缺省，该测试必红）。

**VC-304** — `rag/tools.ts:740` `resolveCliDir`，`cliCall:754` 已改用它。实测：`[VERIFY] VC-304: null_to_root=true explicit=C:\Users\WENBOZ~1\AppData\Local\Temp\mw-rag-window-dir-S745dh\skills\x`。强度：强（纯函数两断言）。

**VC-305** — `rag/config.ts:676-700` `ragFingerprint` payload 含 `skill.dir` 原值（未归一化）。自 `rag-parity.test.ts` 真子进程取 Python 串。实测：
```
[VERIFY] VC-305: dir=default parsed=null ts==py prefix=5e9bfc0055eb | dir=null parsed=null ts==py prefix=5e9bfc0055eb | dir=explicit parsed=skills/x ts==py prefix=2998c51ff849
```
强度：强（三变体真子进程比对）；**但有边角缺口**：`dir`/`cli_entry` 带首尾空白时 TS≠Python（§4.2）。

**VC-306** — `pm/ui-bridge.ts:1850` `parseRagArgs`（白名单来自 `mw-runner.ts:497`）。实测：`[VERIFY] VC-306: list={"sub":"list","rest":[]} audit={"sub":"audit","rest":["--key","K"]} bogus=usage(all_5=true)`。强度：强。

**VC-307** — `pm/ui-bridge.ts:1879-1896` `runMwRagCommand`：`usage` 分支在调 runner 前 return；`runner` 注入计数桩。实测：`[VERIFY] VC-307: unknown_sub_runner_calls=0 usage_notices=3`（另有已知 sub 转发用例 `calls=[['/proj',['audit','--key','K']]]`）。强度：强。

**VC-308** — `pm/ui-bridge.ts:1866-1873`（`RAG_OUTPUT_MAX_LINES = 30` 在 `:1836`；提示常量 `RAG_FULL_OUTPUT_HINT` 在 `:1841`）。实测：`[VERIFY] VC-308: level0=info level1=warning level2=error` 与 `[VERIFY] VC-308: truncated_lines=31 hint_present=true exact30_intact=true`。强度：强。

**VC-309** — `pm/ui-bridge.ts:1460-1475`：error 优先 → 空 enabled → `enabled=…; probe=<排序>; fingerprint=<前12>; skill=…[; required_missing=N]`，与 `mw.py:2297-2316` 对齐。实测（三组真实 `mw.py doctor --json`/文本）：
```
[VERIFY] VC-309: not-enabled[ts=py=true]"rag: not enabled (skill absent)" | config-error[ts=py=true]"rag: ERROR - rag server 'S': adapter must be 'overcode-v1'" | enabled-unreachable[ts=py=true]"rag: enabled=S; probe=S=unreachable; fingerprint=e527406e5021; skill=absent"
```
强度：强（逐字相等，真子进程）。**缺口**：原三组都是单服务器且 `required_missing=0`；probe 多服务器排序拼接与 `required_missing=N` 追加未被任何 T-3 用例覆盖（T-3 自报属实），由 E-4 补齐后为逐字相等（§4.1）。

**VC-310** — `pm/ui-bridge.ts:1568` 插入行 + `:1484` 门控谓词。实测：
```
[VERIFY] VC-310: no_rag_row=true lines=4
[VERIFY] VC-310: gate_absent=false gate_inert=false gate_exists=true gate_enabled=true rows=0
[VERIFY] VC-310: rag_rows=1 line="rag: not enabled (skill unknown)"
```
强度：强。反例 C（删行）与反例 D（`shouldShowRagDoctorRow`→`report.rag`）分别打红不同断言（§3-C/D）。

**VC-311** — `pm/ui-bridge.ts:1831-1832` `MW_COMMAND_DESCRIPTION` 含 `rag`，`registerCommand("mw", {description: MW_COMMAND_DESCRIPTION})` 在 `:1902`。实测：`[VERIFY] VC-311: mw_description_has_rag=true`。强度：强（断言的是注册处引用的同一常量，不是副本）。

**VC-312** — 零回归：`npm run check` EXIT=0；`rag-window` 16、`rag-*` 6 文件 55、`agent-team-loop*` 2 文件 178、Python 839 passed/9 deselected；`test/fixtures`+`test_autopilot_l0.py` diff 空；golden sha256 `00f85e646e30…4035`（与 spec 锁定的 `00f85e64…4035` 一致）。强度：强。

**VC-309b（T-3B 补充）** — `pm/ui-bridge.ts:1484` `shouldShowRagDoctorRow`（镜像 `mw.py:523` 的 `exists or enabled`）+ `:1568` 使用。实测：`[VERIFY] VC-309b: empty_py_row=false empty_ts_row=false configured_py_row=true configured_ts_row=true`。强度：强（谓词与真实 `mw.py doctor` 文本行双侧比对）。但：该用例断言的是谓词本身，**不经过 `formatDoctorReport`**，所以反例 D 时它不红（§3-D）。

**未覆盖的 VC**：无。VC-301~VC-312 全部有行；VC-309 的两个分支缺口已由 E-4 补齐。

## §3 反例试验记录

统一流程：`node %TEMP%/mw-rwp-exp/swap.cjs backup <file>` → 改 → 跑测 → `restore` → 重算 sha256。备份目录 `%TEMP%/mw-rwp-exp/backup/`（仓外）。

| 反例 | 改了什么（改前 → 改后） | 看到什么红 | 还原 + sha256 自检 |
|---|---|---|---|
| **A** | `rag/config.ts:266` `optionalString(raw.dir, …)` → `requireString(raw.dir, …)` | `rag-window`：**2 failed / 14 passed**；红：`VC-301`、`VC-302`（其余含 VC-303 绿） | restore ✓ sha `7d24c0511ab4f093cab0dd49d88591302112de0f4c634b9141cca76e17373932` = 基线 |
| **B** | `shared/mw-runner.ts:453` `--project=${projectDir}` → `--project=.` | ❌ **不变红**：`rag-window` + `agent-team-loop.test.ts` = **2 files / 186 passed**，0 fail | restore ✓ sha `f061957cf6d9af648edf1e42ac7ad040cb95fb7521c08a4355c904b02936c6a0` = 基线 |
| **C** | `pm/ui-bridge.ts:1568` 删除整行 `if (shouldShowRagDoctorRow(report.rag)) lines.push(…)` | `rag-window`：**1 failed / 15 passed**；红：`VC-310 > a report with a configured rag shows exactly one rag row`（期望 `rag_rows=1`，实得 0） | restore ✓ sha `147d6e9cb2b22acc0bdc22a6640491671e3b008c559260cb30ec7c642384c4ca` = 基线 |
| **D** | `pm/ui-bridge.ts:1568` `if (shouldShowRagDoctorRow(report.rag))` → `if (report.rag)` | `rag-window`：**1 failed / 15 passed**；红：`VC-310 > a project without RAG config shows no row, matching the Python gate`。⚠ **非任务书预测的 VC-309b**（见下） | restore ✓ sha 同基线 `147d6e9c…c4ca` |

复原自检：四者复原后逐文件 sha256 均与基线相等（上表）；`mw.py`/`mw_common.py` 全程未动（`e38668c5…6b72` / `f2a5369e…d4ab` 前后一致）。

### 反例结论

- A/C/D 变红，对应断言非装饰：VC-301/302（parity 放宽必需）、VC-310（行必须被渲染）、VC-310 无配置门控（必须与 Python 同门）。
- **B 不变红（发现 1）**：把 `runMwCliRaw` 的 `--project=<control root>` 换成 `--project=.`，186 个相关用例全绿。“以控制工作区为 `--project` 调用 `mw.py rag`”（AC-303）在 TS 侧**没有任何真 spawn 用例钉住**：`agent-team-loop.test.ts:4325/4392/4485` 用的是注入 runner（只断言 `projectDir` 被传入调用方，不断言 `mw-runner.ts` 拼进 argv 的值）；`rag-window` 的 VC-309 helper 自己拼 `--project=`。该行代码本身正确（直读 `mw-runner.ts:453`），但**证据强度降为“未覆盖/弱”**：建议后续补一条真 spawn（或导出 `runMwCliRaw` 断言 argv）用例。
- **D 的红点与任务书预期不同（发现 2）**：任务书说 D 应打红 VC-309b，实测 VC-309b 仍绿、红的是 VC-310。原因：VC-309b 只调 `shouldShowRagDoctorRow` 谓词本身（未被 D 改动），而直接跑 `formatDoctorReport` 的是 VC-310。结论：**门控正确性由 VC-310 钉住，VC-309b 钉的是谓词**——两者互补，无遗漏（但任务书对红点的预测有误，如此记）。

## §4 一致性抽查与补充实验 E-4

### §4.1 E-4：多服务器 probe 排序 + `required_missing>0`（必做）

T-3 自报两个分支无用例钉住，已自建真 fixture 验证：

- 项目：`.mw/rag-servers.yml` 两个 mcp 服务器——`A` 指向同一脚本内的 mock MCP HTTP 服务器（`127.0.0.1:<随机端口>/mcp`，回应 initialize / list_sources，故 **reachable**），`B` 指向 `http://127.0.0.1:9999/mcp`（无监听，**unreachable**，`WinError 10061`）。
- `.agenticdoc/target.yml`：`rag.enabled: [B, A]`（故意 B 在前，逼出排序）、`roles.review.require: true`、`review.server: A`。
- `required_missing`：`.agenticdoc/K/workers/w-review/task.md`（`type: review`）+ 一条 `done` 的 `_workers.parallel` 行，无任何可验证引用 → `required_missing=1`。
- 命令：`node node_modules/tsx/dist/cli.mjs %TEMP%/mw-rwp-e4/e4.mts`（`spawn` 异步以保留 mock server 事件循环；首跑用 `spawnSync` 把同一进程事件循环阻塞，A 被误判 timeout，已修正）。

实测（同一 fixture，`mw.py doctor --json` 的 `report.rag` 喂给 TS；文本版取 `rag: ` 行）：
```
rag JSON probe 顺序(插入序): B,A    required_missing: 1
TS: "rag: enabled=B, A; probe=A=reachable, B=unreachable; fingerprint=4e005104436e; skill=absent; required_missing=1"
PY: "rag: enabled=B, A; probe=A=reachable, B=unreachable; fingerprint=4e005104436e; skill=absent; required_missing=1"
EQUAL: true    HAS_REQUIRED_SUFFIX: true
```
结论：**逐字相等**。`enabled` 按 target 原序（`B, A`）、probe 按 name 排序拼接（JSON 插入序 `B,A` → 渲染 `A,B`）、`fingerprint` 截前 12 位、`required_missing=1` 正确追加。T-3 两个自报缺口至此被实测钉住，**未发现不一致，未改代码**。

### §4.2 一致性抽查（≥6 条可证伪断言）

| # | 断言（可证伪） | 依据（file:line / 命令） | 符合？ |
|---|---|---|---|
| 1 | `RagSkillEntry.dir` 可表达 `null` | `rag/config.ts:94` `dir: string \| null`；`rag-window` 编译+用例通过 | 符合 |
| 2 | `RAG_SUBCOMMANDS` 与 `mw.py _RAG_ACTIONS` 同集 | `shared/mw-runner.ts:497` `["list","probe","audit","sync","init"]` vs `mw.py:2239-2245` keys `init/list/probe/audit/sync` | 符合（集合相等；仅顺序不同） |
| 3 | `formatRagDoctorLine` fingerprint 截断 12 位 | `pm/ui-bridge.ts:1470` `.slice(0, 12)` vs `mw.py:2297-2316` `[:12]`；E-4 实测 `4e005104436e`（12 字符） | 符合 |
| 4 | 输出截断阈值 = 30 行 | `pm/ui-bridge.ts:1836` `RAG_OUTPUT_MAX_LINES = 30`；`:1871` `lines.length <= …`；VC-308 `truncated_lines=31 exact30_intact=true` | 符合 |
| 5 | `/mw` 注册 description 含 `rag` 且注册处引用同一常量 | `pm/ui-bridge.ts:1831-1832` 定义、`:1902` `description: MW_COMMAND_DESCRIPTION`；VC-311 | 符合 |
| 6 | `runMwCliRaw` 将 `--project=<projectDir>` 拼入 argv | `shared/mw-runner.ts:453` 直读正确 | **代码符合，但未被测试钉住**（§3-B；反例 B 全绿） |
| 7 | `shouldShowRagDoctorRow` 镜像 `mw.py:523` 门（`exists or enabled`） | `pm/ui-bridge.ts:1484` vs `mw.py:523`；VC-309b 双侧实测 | 符合（`exists` 为 bool 时；TS 用 `=== true` 更严，`mw.py` 恒发 bool） |
| 8 | `skill.dir`/`cli_entry` 空白处理两侧同义 | `mw_common.py:564` `directory.strip()` / `:565` `cli_entry.strip()`（`_rag_finalize_skill`） vs `rag/config.ts:164-172`（只校验 `trim()`，**不回写 strip**）；命令 `node … whitespace.mts` | **不符**（见下） |
| 9 | `ragMw` 保留原始 exit code（1 ≠ 失败） | `shared/mw-runner.ts:507-510` `ok: raw.code === 0`，code 原样返回；VC-308 映射 | 符合 |

**不符项 #8（发现 3，既有边角，未修）**：
```
TS   dir= "  skills/x  "  cli_entry= "  cli.py  "  fingerprint= e20f65c80d1d98fd47314f8229dd17d702debbdb5e5b410aa5ff56561e8a5343
PY   dir= "skills/x"     cli_entry= "cli.py"     fingerprint= a7ac2452cbb3fba6161c236c067fc72505e7424e7d696252237af9ce625961e8
FINGERPRINT_EQUAL: false
```
影响：当 YAML 用引号包裹带首尾空白的 `skill.dir`/`skill.cli_entry`（如 `dir: " x "`）时，TS `ragFingerprint` ≠ Python `rag_fingerprint`，可能让 `config tear (rag)` 误报/漏报。Python 侧还 strip `mcp.url`/`mcp.token_env`（`mw_common.py:541-542`），TS `parseMcp` 同样不回写 strip，风险面更大。**归属**：本 key 未引入也未修复（T-1 之前的 `requireString` 也不 strip）；VC-305 的三变体不含空白。未改代码，建议另开 key 把两侧改为同一 `strip()` 语义（或两侧都不 strip）。

## §5 零回归与改动面

### 5.1 零回归

| 套件 | 结果 | 归属 |
|---|---|---|
| `rag-window.test.ts` | 16 passed | 本 key（T-1/T-2/T-3） |
| `rag-config/parity/tools/required/role-defaults/evidence` | 55 passed | 本 key（含前序 RAG key） |
| `agent-team-loop.test.ts` + `-output` | 178 passed | 本 key + 其它会话 |
| Python `pytest -q` | 839 passed, 9 deselected | 混合（RAG + 其它） |
| `npm run check` | EXIT=0 | 全局 |
| `test/fixtures/**` + `test_autopilot_l0.py` | `git diff --stat` 空 | — |
| golden `rag-block.golden.md` | sha256 `00f85e646e30…4035`（= spec 锁定值） | — |

Windows 环境：本次未遇到与已知 89 条基线不同的失败；Python 839 passed / 9 deselected 与“无新增失败”一致。

### 5.2 改动面归属（`git status --porcelain`）

- **本 key 产物**：`packages/coding-agent/src/extensions/agent-team-loop/rag/**`（T-1 改的 `config.ts`/`tools.ts`，整个 `rag/` 目录 untracked）、`shared/mw-runner.ts`、`pm/ui-bridge.ts`（T-2/T-3）、`test/suite/rag-window.test.ts`（new）。其中 `mw-runner.ts`/`ui-bridge.ts` 是 tracked 文件，工作区里还叠加了更早未提交的 RAG/其它会话改动，**无 git baseline 可以分离**；`rag/` 与 `rag-*.test.ts` 均为 untracked（前序 key 新增），所以 `git diff` 看不到本 key 的改动，只能靠直读源码 + 实测。
- **其它会话/前序 key 改动（本 key 未动）**：`packages/multi-workers/{mw.py,mw_common.py,launcher.py,autopilot/dispatch.py,README.md,CHANGELOG.md,dist/extensions/agent-team-loop.js}`、`test_autopilot_dispatch.py`、`test_dispatch_models.py`、`packages/coding-agent/src/extensions/agent-team-loop/{index.ts,pm/pm-orchestrator.ts,pm/task-dispatcher.ts,shared/dispatch-models.ts,shared/target-config.ts,worker/worker-mode.ts,shared/implementation-gate.ts}`、`test/extensions/agent-team-loop.test.ts`、`.agenticdoc/` 其它 key、仓根 `AGENTS.md` 等。
- 本报告（`.agenticdoc/mw-rag-window-parity/evidence/verify-run-2026-09-23.md`）为本任务唯一新增文件。
- 复核 sha256（实验后）：`rag/config.ts` `7d24c051…`、`rag/tools.ts` `ab031102…`、`shared/mw-runner.ts` `f061957c…`、`pm/ui-bridge.ts` `147d6e9c…`、`rag-window.test.ts` `4fba6673…`、`mw.py` `e38668c5…`、`mw_common.py` `f2a5369e…`——与实验前一致。未 commit。

## §6 未覆盖与限制

本次**未做/未验证**（如实声明）：

- **真实 RAG 服务联调**：probe 仅用本脚本 mock MCP（`127.0.0.1:<随机端口>`）与不可达端口 `9999`；未对接真实 RAG 服务、未验真实 `list_sources`/能力校正。
- **`mw serve` 重启后的端到端 worker 跑**：未启动 `mw` 服务，未验证 worker 真正调用 RAG + 引用注入。
- **pi TUI 里人工敲 `/mw rag`**：未在 tmux/真 TUI 中人工操作；只验证了纯函数与接线（`pm/ui-bridge.ts:2034` 分支）。
- **中文排版**：未审 RAG 行/帮助文本在 pi 窄通知通道下的换行/宽度表现（`RAG_FULL_OUTPUT_HINT` 固定单行）。
- **Windows 已知基线**：未重跑 `packages/agent` 套件（与本次改动无关）；Python 只跑了 `packages/multi-workers`。
- **反例 B 的补钉**：未新增测试（本任务只允许写报告）；建议后续 key 补一条真 spawn 断言 `runMwCliRaw` 的 `--project`。
- **空白 parity 修复**：未改代码（§4.2 发现 3）；需另开 key。
- 本 key 未改任何 fixture/golden/`mw.py`/`mw_common.py`；所有反例临时改动已 sha256 复原（§3）。

限制：VC-309 三组 fixture 与 E-4 均由外部命令实跑 `mw.py`，依赖本机 Python + PyYAML（不可用时用例 `skipIf` 跳过；本次实测可用）。

