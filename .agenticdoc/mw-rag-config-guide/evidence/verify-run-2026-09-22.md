# T-23 独立验证报告（第三方视角）

- Key: `mw-rag-config-guide`
- Task: T-23（验证 T-21 `mw rag init` 模板生成器 + T-22 `docs/rag-config-guide.md` 手册与 `test_rag_docs.py` parity 锁）
- Worker: `mw-rag-cfg-t23-verify`
- 日期: 2026-09-22（本机时区）
- 仓库: `H:/git/Multi-Workers`，HEAD `0c775408609c0be3a55ab73cf23aa89d641b53d6`（`0c7754086 feat(multi-workers,coding-agent): bound autopilot advance retries...`）
- Python: 3.14.3（Windows / PowerShell）
- 唯一写入文件: 本报告（反例试验期间临时改过 2 个源文件，均已按 sha256 复原，见 §3）

## 结论

**通过（PASS）**：

- 目标测试 `test_rag_init.py` + `test_rag_docs.py` 两次运行（默认编码 / `PYTHONIOENCODING=utf-8`）均 **17 passed**；全套件 `python -m pytest -q` **839 passed / 9 deselected**；仓根 `npm run check` **exit 0**。
- 三条反例全部按预期变红（A→VC-206、B→VC-205、C→VC-201），全部原样复原且 sha256 一致（`rag_templates.py` 与 `docs/rag-config-guide.md` 均回到验证前的哈希）。
- 手册三类模板块与 `mw rag init --print` 字节 parity 成立；从手册逐字复制的 mcp-only / both 示例在临时项目可被 `load_rag_config` 与 `mw rag list` 无 error 接受。
- 发现 **2 处手册散文与实现不符**（均为「不够完整/跨语言不一致」，非功能性错误），已按红线只记不改，详见 §4：`rag-unavailable` 的 `kind` 枚举漏 `tool`；`skill.dir` 的 `null` 默认在 TS worker 侧不被接受。

---

## §0 复现命令表

所有命令在 `H:\git\Multi-Workers` 下执行；临时根 `TMPBASE=$env:TEMP\mw-t23-verify`（基础项目 `project/`；手册示例 `a/ b/ c/ d/`；反例 e `e/`；不可达 `un/`；null-dir `sk/`），所有 CLI 运行均设 `MW_RAG_SERVERS_HOME=$env:TEMP\mw-t23-verify\home`，**未触碰真实 HOME**。

| # | 命令 | 结果 / exit |
|---|---|---|
| 1 | `cd packages/multi-workers; python -m pytest test_rag_init.py test_rag_docs.py -q -s` | exit 0，17 passed，[VERIFY] 见 §2 |
| 2 | `$env:PYTHONIOENCODING="utf-8"; python -m pytest test_rag_init.py test_rag_docs.py -q -s` | exit 0，17 passed，[VERIFY] 与 #1 逐字相同 |
| 3 | `cd packages/multi-workers; python -m pytest -q` | exit 0，**839 passed, 9 deselected** in 83.17s |
| 4 | `cd H:\git\Multi-Workers; npm run check` | **exit 0**（biome `Checked 1080 files. No fixes applied.`；pinned-deps/ts-imports/shrinkwrap/install-lock/tsgo/browser-smoke 全过） |
| 5 | `git diff --stat` / `git status --porcelain` | 见 §5；运行 npm check 前后逐行 `Compare-Object` 为空（无改动） |
| 6 | e2e：`MW_RAG_SERVERS_HOME=… home; python mw.py rag init --project $TMPBASE\project` | exit 0，写 3 个文件（含 `.mw/rag-roots.json`） |
| 7 | e2e：`python mw.py rag list --project $TMPBASE\project` | exit 0，`enabled: (none)`，`path_roots_file = .mw/rag-roots.json [project]` |
| 8 | e2e：再次 `rag init`（同项目） | exit 1，3 条 `refusing to write … already exists`，`nothing written.` |
| 9 | e2e：`python mw.py rag list --project $TMPBASE\project --json` | exit 0，`enabled: []`，`default_server: null`，`path_roots_digest` 64 hex |
| 10 | e2e：`python mw.py rag probe --project $TMPBASE\project` | exit 0，`no enabled servers` |
| 11 | e2e：`python mw.py rag audit --project $TMPBASE\project` | exit 0，`calls=0 citations=0 missing=0 unverified=0 required_missing=0` |
| 12 | 默认 roots 文件自检 `Get-Content $TMPBASE\project\.mw\rag-roots.json` | 存在；`"engine": "."` |
| 13 | 手册复制粘贴：`rag list --project $TMPBASE\{a,b,c,d}`（mcp-only / skill-only / both / 双服务） | 均 exit 0，无 error；`load_rag_config` error=None |
| 14 | `load_rag_config` 直调（临时脚本 `load_check.py`）对 a/b/c/d | 均 `error= None`，enabled 分别 `['overcode']/['engine-cli']/['overcode']/['overcode','engine-cli']` |
| 15 | 不可达探活：`rag probe --project $TMPBASE\un`（`127.0.0.1:8199`） | **exit 0**，`dead: unreachable (URLError … WinError 10061)` |
| 16 | 缺失引用审计：`rag audit --project $TMPBASE\a`（`ghost::` 与不存在的 `engine::` 各一条） | **exit 1**，`missing=2 unverified=0`，报文见 §4 断言 9 |
| 17 | `rag sync --project $TMPBASE\a` | exit 0，`installed …\a\.pi\skills\mw-rag.md`（文件存在） |
| 18 | `--force` 段保真：`rag init --force --server renamed` on `$TMPBASE\e`（target 含 `version: 1`/注释/`other:`） | exit 0；非 `rag` 段原样保留（见 §4 #16） |

[VERIFY] 原文（#1 与 #2 两次运行逐字一致）：

```
[VERIFY] VC-201-enable: enabled=['example'] default=example
[VERIFY] VC-203-print: segments=3 servers_key=1 rag_key=1
[VERIFY] VC-201: created=3 list_exit=0 enabled=(none) servers=1
[VERIFY] VC-202: rerun_exit=1 rerun_untouched=1 force_exit=0 servers_sha_changed=1 target_sha_changed=1
[VERIFY] VC-203: dry_exit=0 print_exit=0 tree_equal=1 print_has_servers=1 print_has_rag=1
[VERIFY] VC-204: subprocess_exit=0 input_hits=0 stdin_hits=0
[VERIFY] VC-205: fields=15 mcp_cli_commented=1 skill_url_commented=1 both_active=1
[VERIFY] VC-207: machine_written=1 machine_under_temp_home=1 rerun_exit=1 machine_only_refusal=1
[VERIFY] VC-208: roots_written=1 digest_len=64 citations=1 missing=0 unverified=0 audit_exit=0
[VERIFY] VC-208-noROOTS: active_path_roots=0 digest_is_none=1
[VERIFY] VC-205: documented_rows=25 missing=0 extra=0 example_yaml_keys=34 unaccepted=0
[VERIFY] VC-205-accept: load_error=0 enabled=1 servers=1 role_keys=6 phase_keys=4
[VERIFY] VC-206: sections=3 servers_bytes=3808 target_bytes=1643 roots_bytes=724
[VERIFY] VC-209: phrases=3 verified_in_source=3 quoted_in_manual=3
```

---

## §1 VC 汇总表（VC-201~VC-210）

| VC | 断言摘要 | 结果 | 证据强度 |
|---|---|---|---|
| VC-201 | 干净目录 init 后 2（+roots=3）产物存在；`rag list` exit 0 且 `enabled: (none)`；模板可被 `load_rag_config` 解析 | PASS | 强（实跑；反例 C 证明该断言可证伪） |
| VC-202 | 重跑 exit 1 且字节不变；`--force` exit 0 且 servers/target sha256 改变 | PASS | 强 |
| VC-203 | `--dry-run` / `--print` 前后目录快照字节相等；`--print` 3 段可解析且不含写盘提示 | PASS | 强 |
| VC-204 | `stdin=DEVNULL` 下 exit 0；`_cmd_rag_init` 切片与 `rag_templates.py` 内 `input(`/`sys.stdin` 零命中 | PASS | 强（实跑 + 源码切片扫描） |
| VC-205 | 模板字段覆盖（15 名）+ 三段 transport 激活/注释；手册字段表 == 校验器字段集（missing/extra=0）；手册示例 YAML 键均被接受；全部字段真解析 | PASS | 强（反例 B 证明可证伪） |
| VC-206 | 手册 3 个 fenced 块 == `mw rag init --print` 3 段（EOL/行尾空白归一后字节相等） | PASS | 强（反例 A 证明可证伪） |
| VC-207 | `--machine` 写入临时 HOME 且内容 == 模板；重跑 exit 1；别的空项目也被已有机器层挡住 | PASS | 强 |
| VC-208 | 默认 roots 写出、`engine="."`、`path_roots_digest` 非空、审计 1 citation 0 missing/unverified；`--no-roots` 不写文件且字段保持注释（digest=None） | PASS | 强 |
| VC-209 | 手册引用的 3 条报错串逐字存在于 `mw_common.py`（`unknown rag server` / `unknown key(s)` / `transport must be one of`） | PASS | 中（仅锁 3 条；其余错误串由 §4 抽查覆盖） |
| VC-210 | 全套件无新增失败（839 passed）；`npm run check` exit 0；fixtures/golden 与 `test_autopilot_l0.py` 零 diff | PASS | 强 |

---

## §2 逐 VC 明细

发射位置格式：`<测试 file:line>` / `<实现 file:line>`。

| VC | 断言摘要 | 发射位置 | 实测行原文 | 证据强度 |
|---|---|---|---|---|
| VC-201 | init 后 `rag list` 显示 `enabled: (none)`，3 产物可解析 | test `test_rag_init.py:125`（verify 150）；impl `mw.py:2088`（`_cmd_rag_init`）/ `mw.py:2172-2180`（roots 计划） | `[VERIFY] VC-201: created=3 list_exit=0 enabled=(none) servers=1` | 强 |
| VC-202 | 重跑 exit 1 字节不动；`--force` 重写 | test `test_rag_init.py:160`（verify 177）；impl `mw.py:2142-2148`（refuse / force overwrite）/ `mw.py:2200`（refusals exit 1） | `[VERIFY] VC-202: rerun_exit=1 rerun_untouched=1 force_exit=0 servers_sha_changed=1 target_sha_changed=1` | 强 |
| VC-203 | `--dry-run`/`--print` 纯读；3 段可解析 | test `test_rag_init.py:188`（verify 202）+ `:373`（verify 389）；impl `mw.py:2132`（--print）/ `mw.py:2194`（--dry-run） | `[VERIFY] VC-203: dry_exit=0 print_exit=0 tree_equal=1 print_has_servers=1 print_has_rag=1` + `[VERIFY] VC-203-print: segments=3 servers_key=1 rag_key=1` | 强 |
| VC-204 | 零交互 | test `test_rag_init.py:213`（verify 223）；impl `mw.py:2088-2234`（`_init_source_slice`）、`rag_templates.py` | `[VERIFY] VC-204: subprocess_exit=0 input_hits=0 stdin_hits=0` | 强 |
| VC-205（impl 侧） | 模板含 15 字段名；mcp 模板注释 skill/mcp 反之 | test `test_rag_init.py:232`（verify 255）；impl `rag_templates.py:166` / `:82` / `:227` | `[VERIFY] VC-205: fields=15 mcp_cli_commented=1 skill_url_commented=1 both_active=1` | 强 |
| VC-205（doc 侧） | 手册字段表 == 校验器字段集；示例 YAML 键均被接受 | test `test_rag_docs.py:190`（verify 204）/ `:213`（verify 274）；impl `mw_common.py:356-367` | `[VERIFY] VC-205: documented_rows=25 missing=0 extra=0 example_yaml_keys=34 unaccepted=0` / `[VERIFY] VC-205-accept: load_error=0 enabled=1 servers=1 role_keys=6 phase_keys=4` | 强（反例 B） |
| VC-206 | 手册 3 模板块 == `--print` 3 段 | test `test_rag_docs.py:157`（verify 180）；impl `mw.py:2077`（分段打印）/ `rag_templates.py` | `[VERIFY] VC-206: sections=3 servers_bytes=3808 target_bytes=1643 roots_bytes=724` | 强（反例 A） |
| VC-207 | `--machine` 临时 HOME 写入 == 模板；重跑 exit 1 | test `test_rag_init.py:265`（verify 286）；impl `mw.py:2017`（`_rag_machine_write_path`）/ `mw.py:2169-2170` | `[VERIFY] VC-207: machine_written=1 machine_under_temp_home=1 rerun_exit=1 machine_only_refusal=1` | 强 |
| VC-208 | 默认 roots 可解析且可核对引用；`--no-roots` 字段保持注释 | test `test_rag_init.py:296`（verify 336）/ `:346`（verify 365）；impl `rag_templates.py:82`（`_path_roots_block`）/ `mw.py:1576`（`_rag_load_path_roots`） | `[VERIFY] VC-208: roots_written=1 digest_len=64 citations=1 missing=0 unverified=0 audit_exit=0` + `[VERIFY] VC-208-noROOTS: active_path_roots=0 digest_is_none=1` | 强 |
| VC-209 | 手册引用的报错串真实存在 | test `test_rag_docs.py:296`（verify 303）；impl `mw_common.py:408` / `:478` / `:604` | `[VERIFY] VC-209: phrases=3 verified_in_source=3 quoted_in_manual=3` | 中（只锁 3 串） |
| VC-210 | 零回归：全套件 + `npm run check` + fixtures/golden 零 diff | 无对应 `[VERIFY]`；命令见 §0 #3/#4/#5，明细见 §5 | `839 passed, 9 deselected`；`npm run check` exit 0 | 强 |

补充：`ERR` 用例也是本 key 的合约（`test_rag_init.py` 尾部）：`--only-machine` 不写项目文件、`--machine` 与 `--only-machine` 互斥 exit 1、`--enable` 写 `enabled/default_server` —— 均随 17 passed 一起通过，但上游 `[VERIFY]` 只覆盖 `VC-201-enable`（`enabled=['example'] default=example`）。

---

## §3 反例试验记录（3 条）

基本信息（试验前）：

| 文件 | 试验前 sha256 |
|---|---|
| `packages/multi-workers/rag_templates.py` | `17EE0FEA48E83E5CD8EEAF0B952FC2FAB1A16D1C5DB85E45EB06BD2F4A592861` |
| `packages/multi-workers/docs/rag-config-guide.md` | `B8B0B4CD6BF66FA88CAE39B7BD10256CC2FCEA35EF05DC7178698E1B8310ED56` |
| `packages/multi-workers/mw_common.py`（未改） | `F2A5369E912EE75AE29F2BEA17EADB27D41FA8D08637C9EBD2E71197AD29D4AB` |

### 反例 A — 改模板一个字符 ⇒ VC-206 必须红

- 改了什么：`rag_templates.py:64`（`_transport_block` 注释行）`"    # values: mcp | skill | both   default: mcp",` → `… default: mcpp",`（其他一个字）。
- 看到什么红：`python -m pytest test_rag_docs.py -q` → `1 failed, 4 passed`（exit 1）；红的就是 `test_rag_docs.py:157 test_vc206_manual_matches_print_output`，断言 `manual block 'servers' drifted from \`mw rag init --print\``，diff 显示 `default: mcp`（手册）vs `default: mcpp`（print）。
- 还原方式：把该字符改回 `mcp`。
- sha256 是否复原：是（`17EE0FEA…2861`，与试验前完全一致）。

### 反例 B — 改手册字段名 ⇒ VC-205 必须红

- 改了什么：`docs/rag-config-guide.md:70`（§3.1 表格首列）`| \`capabilities.chat\` |` → `| \`capabilities.chats\` |`。
- 看到什么红：`python -m pytest test_rag_docs.py -q` → `1 failed, 4 passed`（exit 1）；红的是 `test_rag_docs.py:190 test_vc205_field_tables_match_validator`，报文 `AssertionError: Items in the first set but not the second: 'capabilities.chat' : manual is missing field rows: ['capabilities.chat']`（`capabilities.chats` 同时落在 extra 集）。
- 还原方式：改回 `capabilities.chat`。
- sha256 是否复原：是（`B8B0B4CD…ED56`）。

### 反例 C — 改默认 `enabled` ⇒ VC-201 必须红

- 改了什么：`rag_templates.py:245`（`render_target_rag_template`）`f"  enabled: [{server}]" if enabled else "  enabled: []"` 的 else 分支 → `"  enabled: [example]"`。
- 看到什么红：`python -m pytest test_rag_init.py -q` → `1 failed, 11 passed`（exit 1）；红的是 `test_rag_init.py:125 test_vc201_clean_project_creates_a_usable_config`，`AssertionError: 'enabled: (none)' not found in '[mw rag] enabled: example\n… server example [enabled]…'`（即默认模板把占位服务打开了）。附带：此改法也会同时打红 VC-206（手册 target 块仍是 `enabled: []`）——未单独跑，已由 A 证明同一 parity 断言可证伪。
- 还原方式：else 分支改回 `"  enabled: []"`。
- sha256 是否复原：是（`17EE0FEA…2861`）。

三条反例均在还原后重跑 `test_rag_init.py test_rag_docs.py -q` → **17 passed**（再次确认无残留）。全部 sha256 自检均与试验前一致。

---

## §4 散文准确性抽查（≥8 条可证伪断言）

方法：从手册中自选 ≥8 条可证伪断言，逐条对照实现（`file:line`）或实跑。PM 已修的两处（§6 `via=mcp|c…` 截断、§3.4 未知 role 误写 `unverified`）本次复核**均已修正**：手册 line 336 已是完整 `via=mcp|cli ms=<N> results=<N>`，line 112-113 已写 `missing`。

| # | 断言（手册） | 依据（file:line / 命令） | 结论 |
|---|---|---|---|
| 1 | §3.2 `enabled` 空或缺省 = 全关（不是全开）（line 83） | `mw_common.py:760-762`（`enabled_raw is None → []`）+ `_rag_finalize_target` | 符合 |
| 2 | §3.3 `chat_budget`/`time_budget_s` 只有 `roles` 接受；写进 `phases` 报 `unknown key(s) chat_budget (valid: server, source, require, rewrite)`（line 98-99） | `mw_common.py:366`（`_RAG_PHASE_KEYS`）、`:681-685`（`extra`→`unknown key(s)`） | 符合 |
| 3 | §3.3 `rewrite` 缺省时「研究类角色/阶段 + 服务能力」推导（line 97） | `mw_common.py:856-872`（`RAG_RESEARCH_ROLES={spec,design,research,rag-research}`、`RAG_RESEARCH_PHASES={spec,design}`、且 `caps.rewrite`） | 符合 |
| 4 | §7 `rag-unavailable … kind=connect\|timeout\|protocol\|circuit ms=N`（line 346） | `adapter.ts:19`（kind 枚举含 `tool`）；`tools.ts:697-700`（“no usable transport” 抛 `kind:"tool"`）；`tools.ts:611`（catch 里用 `tagged.kind` 发 `rag-unavailable`）；`mcp-client.ts:251-252`（服务端 `isError=true` 抛 `kind:"tool"`）；`test/suite/rag-evidence.test.ts:603` 断言 `rag-unavailable server=A tool=rag_search kind=tool` | **不符**（枚举漏 `tool`；“无可用传输”/服务端工具报错实际会发 `kind=tool`） |
| 5 | §3.1 `skill.dir` “路径或 `null`；默认 `null`（项目根）”（line 75） | Python：`mw_common.py:551-553` 接受 `null`（实跑 `sk` 项目：`skill.dir = -`，`rag list` exit 0）；TS：`rag/config.ts:261-262` `requireString(raw.dir, …)` 要求非空字符串（无默认注入） | **不符**（同一写法在 `mw rag list` 过、在 worker `loadRagConfig` 会 `invalid-shape` 失败） |
| 6 | §6 调用层 `rag_call … tool=… via=mcp\|cli ms=<N> results=<N>`（line 336） | `rag/evidence.ts:50-53`（成功行；另有可选 `mcp_tool=<M>`） | 符合 |
| 7 | §7 `rag-budget-exceeded … reason=count\|cumulative\|wall used=N budget=N`（line 350） | `evidence.ts:74-77`；`tools.ts:503`(cumulative)/`:515`(wall)/`:529`(count) | 符合 |
| 8 | §7 `circuit` = 连续 3 次 connect/timeout/protocol 后打开（line 346） | `rag/budget.ts:54`（`BREAKER_KINDS={connect,timeout,protocol}`）、`:57`（`BREAKER_THRESHOLD=3`）、`:245-252` | 符合 |
| 9 | §3.4 未知 role / 文件不存在 → 记为 `missing`（让 audit exit 1）；报错 `unknown role 'x' (available roles: …)` / `file missing`（line 112-113） | `mw.py:1620-1622`、`:1655-1663`；实跑 `rag audit --project a` → exit 1，`citations=2 missing=2 unverified=0`，原文 `missing probe/note[rag-research/-] … -> unknown role 'ghost' (available roles: engine)` 与 `… -> file missing` | 符合 |
| 10 | §5 `sync` 把 skill 写到 `<project>/.pi/skills/mw-rag.md`；未启用时删（line 304） | `mw.py:1097`（`_RAG_SKILL_INSTALL_RELATIVE`）、`:1108-1110`；实跑 `installed …\a\.pi\skills\mw-rag.md` 且文件存在 | 符合 |
| 11 | §5 `probe` 「不可达仍 exit 0」（line 299 / §1） | `_cmd_rag_probe`；实跑 `127.0.0.1:8199` → `dead: unreachable (URLError … WinError 10061)`，**exit 0** | 符合 |
| 12 | §6 注册层 6 工具名 + 描述无 `[unreachable at session start]` + `rag_chat` 仅 `rag-research`（line 333-335） | `rag/tools.ts:64-74`（`RAG_BASE_TOOL_NAMES` 六项 + `RAG_CHAT_TOOL_NAME`）、`:240`（marker） | 符合 |
| 13 | §8 `config torn (rag): task.md fingerprint=… != current …`（line 362） | `launcher.py:764-770`（`check_rag_tear`） | 符合 |
| 14 | §2 项目层 `null` 删除字段；`list` 打印 `[machine]`/`[project]` 来源（line 44-47） | `mw_common.py:490-492`（explicit delete）；实跑 `list` 输出 `path_roots_file = .mw/rag-roots.json [project]` | 符合 |
| 15 | §3.2 `phases` 键大小写敏感（`design` ≠ `DESIGN`），不匹配不报错（line 86 / §8） | `mw_common.py:757`（按字面键存 spec）+ `_rag_phase_spec` 精确查表；无非匹配警告路径 | 符合 |
| 16 | §5 `--force`：`rag:` 段文本级整段替换（不会 YAML round-trip 毁注释/其它段）（line 314） | 实跑 `e` 项目（target 含 `version: 1` / `# keep me` / `other: key: value`）：`rag init --force --server renamed` exit 0，输出中 `version: 1`、`# keep me`、`other:` 均原样保留，只有 `rag:` 块被换掉 | 符合 |
| 17（附加） | 非手册：`test_rag_init.py:37` 注释写 “The 13 field paths”，但 `SERVER_FIELD_NAMES` 实为 15 项（[VERIFY] fields=15） | `test_rag_init.py:37-44` | **不符**（仅测试注释基数错，不影响断言） |

不符项目的影响面：

- #4：仅在服务端返回 `isError=true` / “无可用传输”时多发一个 `kind=tool` 的 `rag-unavailable` 行；按手册判读会漏看这类行。修法：手册 §7 枚举加 `tool`（或写成 `kind=<connect|timeout|protocol|tool|circuit>` 并说明 `tool` 的含义）。
- #5：按手册写 `skill` 块并省略/写 `null` 的 `dir`，`mw rag list` 不会报，但 worker 侧 TS 加载器会拒（`invalid-shape`）。修法：ts 侧给 `dir` 默认 `controlRoot`，或手册把 `dir` 列为 `skill` 块必填。

---

## §5 零回归与改动面

### 改动面

- `git status --porcelain` 共 72 行；其中 T-21/T-22 交付物（`packages/multi-workers/rag_templates.py`、`packages/multi-workers/docs/`、`test_rag_init.py`、`test_rag_docs.py`、`test/fixtures/rag/` 等）与 `.agenticdoc/mw-rag-config-guide/` 均为 **未跟踪（`??`）**，因此不出现在 `git diff --stat` 里。
- `git diff --stat`（tracked 部分）共 26 文件：`.agenticdoc/*`（其他 key 的并行更新）、`packages/coding-agent/*`（agent-team-loop TS 改动）、`packages/multi-workers/{mw.py,mw_common.py,README.md,CHANGELOG.md,launcher.py,autopilot/dispatch.py,dist/extensions/agent-team-loop.js}` 等——均为本会话之外的其它 key/会话的未提交改动，本 worker 未动。
- 零回归核对：`git diff --stat -- packages/multi-workers/test/fixtures packages/multi-workers/test_autopilot_l0.py` → **空输出**（fixtures/golden 与 `test_autopilot_l0.py` 零 diff）。
- `npm run check` 前后分别存 `git status --porcelain` 与 `git diff --stat`，`Compare-Object` 均为空 → biome `--write` 未落任何修改。

### 本 worker 的写入

| 文件 | 说明 |
|---|---|
| `.agenticdoc/mw-rag-config-guide/evidence/verify-run-2026-09-22.md` | 唯一交付物 |
| （临时回改）`rag_templates.py` / `docs/rag-config-guide.md` | 仅反例 A/B/C 试验期间，已按 sha256 复原（见 §3） |
| `%TEMP%\mw-t23-verify\**` | 临时项目/HOME，在仓外，符合「不碰真实 HOME」 |

未 commit。

---

## §6 手册可执行性抽查（复制粘贴即用）

从手册 §4 逐字复制了**四类全部**示例（不只两类的下限），写进临时项目（`$env:TEMP\mw-t23-verify\{a,b,c,d}`），均在 `MW_RAG_SERVERS_HOME=$TEMP\home` 下运行。

| 手册节 | 项目 | 复制的片段 | 实跑结果 |
|---|---|---|---|
| §4.1 (a) MCP-only（line 160-185） | `a` | `rag-servers.yml` + `target.yml` | `rag list` exit 0：`enabled: overcode`，`transport = mcp [project]`，`path_roots_file = .mw/rag-roots.json [project]` |
| §4.2 (b) CLI/skill-only（line 189-205） | `b` | 两个片段 | `rag list` exit 0：`enabled: engine-cli`，`transport = skill [project]`，`skill.dir = skills/engine [project]` |
| §4.3 (c) both（line 210-245） | `c` | 两个片段 | `rag list` exit 0：`transport = both [project]`，`mcp.url` 与 `skill.cli_entry` 同时存在 |
| §4.4 (d) 双服务 + 角色/阶段（line 248-290） | `d` | 两个片段 | `rag list` exit 0：`enabled: overcode, engine-cli`，`review.require=true` / `design.require=true` 解析无错 |

额外直调 `load_rag_config`（临时脚本，非仓库内）：

```
 a error= None enabled= ['overcode']
 b error= None enabled= ['engine-cli']
 c error= None enabled= ['overcode']
 d error= None enabled= ['overcode', 'engine-cli']
LOAD_EXIT=0
```

说明：

- (a)/(c)/(d) 的示例带 `path_roots_file: .mw/rag-roots.json`，手册自身也写了该文件需真实存在（§4.1 说明、§3.1 `path_roots_file` 行）。因此按手册“先 `mw rag init` 生成模板再改字段”的指引，我在 `a`/`c` 先跑 `mw rag init` 生成 roots，在 `d` 拷贝 `init` 输出。这不算“额外步骤”，而是手册明写的使用方式。
- (b) 无 `path_roots_file`（`path_roots_file = -`）；(d) `engine-cli` 无 `capabilities`，均在 TS 侧也有默认（`config.ts:263-268`），符合手册“默认 false”。
- 结论：四类示例均可“复制粘贴即用”（Python 校验面），未发现手册示例语法错。

---

## §7 未覆盖与限制

### 未做 / 未覆盖

1. **真实 RAG 服务联调**：手册示例用占位 URL，未发 `rag_*` 工具调用（未验证协议/归一化/降级行为）。注：`rag probe --project a` 报告 `overcode: reachable`（说明本机有进程在 `localhost:8100` 监听，可能属其它会话）；为验证“不可达仍 exit 0”另建了 `127.0.0.1:8199` 的 `un` 项目。
2. **`mw serve` 重启后的端到端 worker 跑**：`<!-- mw-rag: v1 -->` 注入、worker `rag_call` trace、`rag-required-missing` 等运行期行为未测（T-23 只验配置面；这些由已有 `packages/coding-agent/test/suite/rag-*.test.ts` 覆盖）。
3. **手册中文排版细节**：错别字、标点、表格对齐未逐字校。
4. **`--machine` 在真实 HOME 上的行为**：刻意只在临时 `MW_RAG_SERVERS_HOME` 下测（避免碰真实 HOME）；`$HOME`/`%USERPROFILE%` 回退分支未验。
5. **TS 侧 `skill.dir=null` 的失败结论是静态代码推得**，未实跑 `loadRagConfig`（`packages/multi-workers/dist/extensions/agent-team-loop.js` 是其它会话的产物、不是干净导入目标）；验证凭 `rag/config.ts:261-262` 与 Python 实跑对照。
6. **`audit --out`、`--key` 过滤、`doctor` 的 RAG 段**：未一一实跑（不在本任务 VC 范围内）。

### 失败项归属

本任务下所有测试与实跑均绿，**无失败项**。以下是需要区分的归属：

| 项 | 归属 | 说明 |
|---|---|---|
| `npm run check` / `pytest` 全绿，无 Windows 基线失败 | — | 本次未触发已知 Windows 基线（未跑 e2e）。 |
| `git status` 中 26 个 tracked 修改文件 + 多个 `??`（包含 `.agenticdoc/_index*`、agent-team-loop TS、`mw.py` 修改等） | **其它 key / 会话** | 均在本 worker 开始前已存在；本 worker 未改这些文件（npm check 前后 `Compare-Object` 为空）。 |
| `localhost:8100` 可达 | **其它进程 / 会话** | 非本任务创建；未调用。 |
| `design.md:43` VC-208 仍写 `--with-roots`（T-21B/T-21C 已删该 flag，改为默认写 roots） | **本 key 的设计文档沉余** | 与 T-23 任务书 §「当前实现状态」一致；属文档未同步，非代码缺陷；本 worker 只读未改。 |
| §4 #4/#5 两处手册散文不符 | **本 key T-22 文档缺陷（非阻塞）** | 已给 `file:line`，按红线未改。 |

### 结论

T-21（模板生成器）+ T-22（手册 + parity 锁）按实跑证据通过。两条散文不符（`kind` 枚举漏 `tool`；`skill.dir` 的 `null` 默认在 TS 侧不被接受）建议在后续增量中修（改手册或改 TS 默认），不阻塞本次验收。
