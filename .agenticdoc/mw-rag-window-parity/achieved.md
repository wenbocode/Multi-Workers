# Achieved: mw-rag-window-parity

- key: `mw-rag-window-parity`
- 结论: **交付完成**（AC-301~AC-306 全部有实测证据）；质量门禁裁决 **⚠️ 有条件通过（8 项欠债、0 ❌）**，
  其中 4 项已在同一会话内闭合（Q-AC-303 / Q-X-04 / Q-X-09 / Q-X-10），余 4 项作为遗留声明（见 §5）。
- 合并需求: 用户要求把两处收口缺口合成**一个 key** —— (R-1) TS `skill.dir` 与 Python 解析不一致；
  (R-2) pi 窗口内没有 `/mw rag`、`/mw doctor` 也不显示 RAG 行。

## 1. 交付物（改动面）

| 文件 | 内容 |
|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/rag/config.ts` | `skill.dir` 改用 `optionalString`（缺省/`null` → `null`，`""` 仍非法）；`RagSkillEntry.dir: string \| null`；新增 `optionalTrimmedString` 用于 `mcp.url`/`mcp.token_env`/`skill.dir`/`skill.cli_entry`（镜像 Python `.strip()`）；`ragFingerprint` payload 与字段顺序**未动** |
| `.../rag/tools.ts` | 新增导出纯函数 `resolveCliDir(controlRoot, dir)`（`null` → 控制工作区根），`cliCall` 改用它 |
| `.../shared/mw-runner.ts` | 内部 `runMwCliRaw`（保留 exit code）+ 既有 `runMwCli` 薄包装（行为不变）；`RAG_SUBCOMMANDS`、`ragMw`；`DoctorJson.rag?` |
| `.../pm/ui-bridge.ts` | `MW_COMMAND_DESCRIPTION`（含 `rag`）、`parseRagArgs`、`formatRagOutput`（0/1/2 → info/warning/error，>30 行截断 + 完整命令提示）、`runMwRagCommand`（runner 可注入）、`/mw` 的 `sub === "rag"` 分支、`shouldShowRagDoctorRow`（门控镜像 `mw.py:523`）、`formatRagDoctorLine`（逐字对齐 `mw.py:_format_rag_doctor_line`）、`formatDoctorReport` 插一行 |
| 测试 | `test/suite/rag-window.test.ts`（18）、`rag-trim-parity.test.ts`（4）、`rag-window-missing-mw.test.ts`（1）、`rag-parity.test.ts` 扩展（`dir` 三变体） |
| 文档 | `packages/coding-agent/CHANGELOG.md` `[Unreleased]` 的 `### Added` / `### Fixed` 各一条 |

**Python 零改动**（`mw.py`/`mw_common.py` 未动），fixture/golden 零 diff。

## 2. 系统行为变化（用户可感）

- `/mw rag <list|probe|audit|sync|init> [args]` 可用（此前会落到通用 usage 行）：转发到 `mw.py rag <sub> --project=<控制工作区>`；
  exit 0/1/2 → info/warning/error（`audit` 的 exit 1 = 有 findings，不再被当成失败）；未知/空子命令只打印用法且**不调 CLI**。
- `/mw doctor` 多一行 RAG 状态行，与终端 `mw.py doctor` 的 `rag: ` 行**逐字一致**；两者同一门控
  （`rag.exists or rag.enabled`），完全没配 RAG 的项目两侧都不打行。
- 配置面：`skill.dir` 缺省/`null` 现在被 worker 侧加载器接受（= 控制工作区根），不再出现「`mw rag list` 通过但 fetch 侧加载失败」；
  padding 值（`" skills/x "`）两侧解析一致，fingerprint 不再分裂。

## 3. 命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-window-missing-mw.test.ts test/suite/rag-window.test.ts \
  test/suite/rag-trim-parity.test.ts test/suite/rag-parity.test.ts test/suite/rag-config.test.ts   # 5 files / 44 passed
node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-*.test.ts                          # 14 files / 127+ passed
cd packages/multi-workers && python -m pytest -q                                                   # 839 passed, 9 deselected
cd H:/git/Multi-Workers && npm run check                                                           # exit 0
```

## 4. 证据摘要（全部为实测，含第三方复核）

| AC | 关键实测 |
|---|---|
| AC-301 | `[VERIFY] VC-301/302: dir=null parse=ok`；`VC-303: kind=invalid-shape mentions_skill_dir=true`；`VC-304: null_to_root=true`；`VC-305b: blank_dir_ts_kind=invalid-shape blank_dir_py_error=true` |
| AC-302 | `[VERIFY] VC-305: dir=default/null parsed=null ts==py prefix=5e9bfc0055eb`；`dir=explicit parsed=skills/x ts==py prefix=2998c51ff849`；`VC-305b: dir="skills/x" cli_entry="cli.py" ts==py=true prefix=a7ac2452cbb3`、`url=… token_env="RAG_TOKEN" ts==py=true prefix=b30415c5058c`（Python 均为真子进程 `mw_common.load_rag_config`+`rag_fingerprint`） |
| AC-303 | `VC-306`（三例返回值）、`VC-307: unknown_sub_runner_calls=0 usage_notices=3`、`VC-308`（三档 level + 截断 31 行/hint）、**`VC-308b: argv0=["rag","list","--project=<root>"] argv1_code=1 ok0=true ok1=false`（真 spawn）**、`Q-AC-303: ok=false code=-1 hint_has_MW_PY=true`、`Q-X-04: py=audit,init,list,probe,sync ts=… equal=true` |
| AC-304 | `VC-309`（not-enabled / config-error / enabled-unreachable 三组 `ts=py=true`）、`VC-309b: empty_py_row=false empty_ts_row=false configured_py_row=true configured_ts_row=true`、`VC-310: gate_absent=false gate_inert=false gate_exists=true gate_enabled=true rows=0`；T-4 另做双服务器 probe 排序 + `required_missing=2` 直比 → 全等 |
| AC-305 | `VC-311: mw_description_has_rag=true`；接线实测 `pm/ui-bridge.ts:1994`（`sub === "rag"` → `runMwRagCommand`） |
| AC-306 | `npm run check` exit 0（biome `Checked 1083 files`）；rag 14 文件 127 passed；`agent-team-loop*` 178 passed；Python 839 passed/9 deselected；`test/fixtures`+`test_autopilot_l0.py` diff 空；golden sha256 `00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035` |

**反例（T-4 三条 + T-5 四条，全部实测变红后 sha256 复原）**：
T-4 — A `optionalString`→`requireString`（VC-301/302 红）；C 删 RAG 行（VC-310 红）；D 门控回退（VC-310 红）；
**T-4 反例 B `--project=.` 当时全绿 ⇒ 证据强度被降级**（该缺口由 T-5 补测试后闭合）。
T-5 — A trim 回退（`rag-trim-parity` 2 红）；**B `--project=.` → VC-308b 红**；C 门控回退（VC-310 红）；
D canonical 键 `path_roots_file`→`path_roots_files`（`rag-parity` 4 红）。

## 5. 遗留（声明，未修）

| ID | 内容 | 证据/原因 |
|---|---|---|
| R-6 | `path_roots_file` 两侧 padding 语义不一致 | 实测（T-5 + 质检独立复现）：padding `" .mw/rag-roots.json "` 下 TS 未 trim / Python 已 strip，两侧 digest 均 `null`，fingerprint TS `d5b017c6…` ≠ PY `9ed001e4…`，**把 TS 该键 trim 后即逐字节相等 ⇒ 差异仅来自该键**；无 padding 对照两侧同为 `a3e2ee05…`。修需改 Python（本 key 声明 Python 零改动）或另开 key 评估 fingerprint 语义 |
| R-7 | `/mw` 命令处理器 → `runMwRagCommand` 的接线只有代码直读 + description/纯函数测试，无 pi 命令级测试 | 需 pi command harness；函数本体（`runMwRagCommand`）与 5 个子命令转发已由 VC-306~308b 钉住 |
| R-8 | 缺 `evidence-requirement.md` / `evidence/baseline/`（框架 QG Step 1 的 L2 目录） | 本 key 沿用前序 key 的轻量证据结构（`evidence/research/` + `evidence/verify-run-*.md`），质检按 ⚠️ 记 |
| R-9 | 真实 RAG 服务未联调（8100 上的 rag-mcp 未被本 key 调用）；pi TUI 内未人工按过 `/mw rag`/`/mw doctor`；`/mw rag init` 的写盘副作用未在窗口验证 | 本 key 的验收面是「配置面一致性 + 窗口转发/渲染代码路径」，均为 L1 可复现证据 |

## 6. 会话内闭合的质检欠债

| 欠债 | 闭合方式 |
|---|---|
| Q-AC-303（`findMwPy()===null` 无测试） | 新增 `rag-window-missing-mw.test.ts`（mock `node:fs`）→ `ok=false code=-1 hint_has_MW_PY=true` |
| Q-X-04（白名单漂移无断言） | `rag-window.test.ts` 新增断言 `RAG_SUBCOMMANDS` == `mw.py _RAG_ACTIONS` → `equal=true` |
| Q-X-09（T-3B/T-3C 未回写 spec/design） | `spec.md` AC-304 门控改写；`design.md` 增 D-311/D-312/D-313 + VC-305b/VC-308b/VC-309b、VC-310 与覆盖矩阵同步；`check_mermaid.py` PASS |
| Q-X-10（CHANGELOG 无本 key 条目） | `packages/coding-agent/CHANGELOG.md` `[Unreleased]` 增 Added/Fixed 各一条（CRLF 保持，语法不动） |
