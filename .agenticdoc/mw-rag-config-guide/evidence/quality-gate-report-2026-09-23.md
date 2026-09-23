# 质检报告 — key `mw-rag-config-guide`

- 日期: 2026-09-23
- 范围: `mw rag init` 模板生成器 + `docs/rag-config-guide.md` 配置手册 + parity 锁
- 质检人: PM（本窗口）；独立验证由 `mw-rag-cfg-t23-verify` 完成（`evidence/verify-run-2026-09-22.md`）
- 结论: **✅ 通过**（20 项充分 / 3 项 ⚠️ / 0 项 ❌；遗留 R-1~R-5）

## 1. AC 判定

| AC | 要求摘要 | 判定 | 证据 |
|---|---|---|---|
| AC-201 | `rag init` 在干净目录生成可解析配置，默认 `enabled: []`，`rag list` exit 0 显示 `enabled: (none)`，零副作用 | 充分 | `[VERIFY] VC-201: created=3 list_exit=0 enabled=(none) servers=1`（3 产物：servers / target `rag:` / roots）；反例 C 证明该断言可证伪 |
| AC-202 | 已存在则拒绝（exit 1）不改字节；`--force` 才覆盖；`--dry-run`/`--print` 零写入 | 充分 | `[VERIFY] VC-202: rerun_exit=1 rerun_untouched=1 force_exit=0 servers_sha_changed=1 target_sha_changed=1`；`[VERIFY] VC-203: dry_exit=0 print_exit=0 tree_equal=1`；T-23 另测 `--force` 时 `target.yml` 其它段/注释原样保留 |
| AC-203 | 零交互 + 可改模板 + 机器层仅显式请求 + roots 模板 | 充分（**修订**） | `[VERIFY] VC-204: subprocess_exit=0 input_hits=0 stdin_hits=0`；`[VERIFY] VC-207: machine_written=1 machine_under_temp_home=1 rerun_exit=1 machine_only_refusal=1`。原「`--with-roots` 写 roots」已按 D-210 修订为**默认写**、`--no-roots` 跳过（spec AC-201/AC-203 已标 `REVISED @ 2026-09-23`） |
| AC-204 | 每个配置文件逐字段注释/示例；字段覆盖服务表 13 + `rag:` 段 6 + roles/phases 4(+2) + `rag-roots.json` | 充分 | `[VERIFY] VC-205: fields=15 mcp_cli_commented=1 skill_url_commented=1 both_active=1`；`[VERIFY] VC-205: documented_rows=25 missing=0 extra=0 example_yaml_keys=34 unaccepted=0`；`VC-205-accept: load_error=0 enabled=1 servers=1 role_keys=6 phase_keys=4` |
| AC-205 | 手册含四类可复制示例 + 命令/退出码 + 五层判据 + 失败 signature + 坑 | 充分 | 手册 519 行/31.8 KB；T-23 **逐字复制四类示例**到临时项目，`load_rag_config` 全部 `error=None`、`rag list` 全部 exit 0（§6 表）|
| AC-206 | 手册模板块 == `mw rag init --print` 输出（字节级） | 充分 | `[VERIFY] VC-206: sections=3 servers_bytes=3808 target_bytes=1643 roots_bytes=724`；反例 A（改模板一字符）与反例 B（改手册字段名）分别打红 VC-206 / VC-205 并 sha256 复原 |
| AC-207 | 零回归 + `npm run check` + fixtures/golden 零 diff + `[VERIFY]` 可复现 | 充分 | `python -m pytest -q` = **839 passed / 9 deselected**；`npm run check` exit 0（biome 1080 files, `No fixes applied`）；`git diff --stat -- test/fixtures test_autopilot_l0.py` 空输出；14 条 `[VERIFY]` 在默认编码与 `PYTHONIOENCODING=utf-8` 下**逐字相同** |

## 2. VC 判定（VC-201 ~ VC-210）

| VC | 判定 | 备注 |
|---|---|---|
| VC-201 干净目录可用 | 充分 | 实跑 + 反例 C 证伪 |
| VC-202 拒绝/覆盖 | 充分 | 字节级对比 |
| VC-203 纯读 | 充分 | 目录快照相等 |
| VC-204 零交互 | 充分 | `stdin=DEVNULL` 子进程 + 源码切片零 `input(` |
| VC-205 字段覆盖（实现侧 + 文档侧） | 充分 | 双向集合相等（missing/extra=0）+ 反例 B |
| VC-206 手册-实现 parity | 充分 | 字节相等 + 反例 A |
| VC-207 机器层 | 充分 | 临时 `MW_RAG_SERVERS_HOME`，未碰真实 HOME |
| VC-208 roots 默认可用 | 充分 | `[VERIFY] VC-208: roots_written=1 digest_len=64 citations=1 missing=0 unverified=0 audit_exit=0`（端到端：真实文件 + `engine::` 引用 → audit 干净）+ `VC-208-noROOTS: active_path_roots=0 digest_is_none=1` |
| VC-209 报错文本诚实性 | ⚠️ | 只锁 3 条错误串（`unknown rag server` / `unknown key(s)` / `transport must be one of`）逐字存在于源码；其余错误串靠 T-23 的 17 条散文抽查覆盖，无自动化锁 |
| VC-210 零回归 | 充分 | 见 AC-207 |

其他 ⚠️：

- **手册散文无自动化锁**：模板块有字节 parity，但散文段落只能靠人工核对。本轮 T-22 交付后又发现 2 处不符（`rag-unavailable` 的 `kind` 枚举漏 `tool`/`capability`；`skill.dir` 的 `null` 默认在 TS 侧不成立）+ 1 处测试注释基数错（13 → 15），已全部修正，并把「散文准确性抽查 ≥8 条」写入 T-23 任务书由独立 worker 执行（17 条断言、2 条不符、均带 `file:line`）。结构性缓解措施（例如把字段/报错表也做成派生检查）尚未做。
- **跑通的是配置面，不是线上**：真实 RAG 服务联调、`mw serve` 重启后的 worker 运行期（注入/trace/`rag-required-missing`）不在本 key 范围（由 `packages/coding-agent/test/suite/rag-*.test.ts` 覆盖）。

## 3. 独立验证（T-23，第三方视角）

- 交付 `evidence/verify-run-2026-09-22.md`（本 key 唯一允许它写的文件）；基线 17 passed（两种编码环境）/ 839 passed / `npm run check` exit 0 全部独立复现。
- **三条反例全部按预期变红并 100% 复原**：
  - A 改 `rag_templates.py:64` 一字符 → `VC-206` 红（`manual block 'servers' drifted`），sha256 复原 `17EE0FEA…2861`；
  - B 改手册 `capabilities.chat` → `VC-205` 红（`manual is missing field rows`），复原 `B8B0B4CD…ED56`；
  - C 改默认 `enabled: []` → `VC-201` 红（`'enabled: (none)' not found`），复原 `17EE0FEA…2861`。
- 手册可执行性：四类示例逐字复制 → 全部被 `load_rag_config` / `rag list` 接受（比任务书要求的两类更多）。
- 它独立发现 2 处散文不符 + 1 处测试注释缺陷 + `design.md` 里残留的 `--with-roots`（均见 §4）。

## 4. PM 直执的修正（本 key 内，均留证）

| ID | 问题 | 处置 |
|---|---|---|
| T-21B | 模板默认让 `path_roots_file` 指向尚不存在的文件（悬空引用 → 每条引用 `exists=false`） | 该字段改为注释 + 说明（随后被 D-210 取代） |
| T-21C（D-210） | 「不配 roots」的默认状态会让审计把每条引用记 `unverified` 并 exit 1，等于默认必失败 | 默认写出 `.mw/rag-roots.json`（`_README` + `engine: "."` = 项目根）并激活字段；`--with-roots` → `--no-roots`；新增端到端 VC-208 断言 `missing=0 unverified=0 audit_exit=0` |
| T-22B | 手册散文 2 处与实现不符（`via=mcp|c...` 截断；§3.4 未知 role 误写 `unverified`） | 逐条按 `mw.py` 行为修正 |
| T-23B | 手册 §7 `kind` 枚举漏 `tool`/`capability`；§3.1 `skill.dir` 默认值在 TS 侧不成立；测试注释 13→15；`design.md` 残留 `--with-roots`；spec AC-201/203 未同步 | 全部修正；`skill.dir` 两侧差异记为**遗留 R-1**（未改 TS）；spec 标 `REVISED @ 2026-09-23` |
| D-211 | `test_rag_init.py` 的 `subprocess.run(text=True)` 在本机 `PYTHONIOENCODING=utf-8` 下按 GBK 解码子进程输出 → `UnicodeDecodeError` 假红 | 3 处调用点显式 `encoding="utf-8", errors="replace"`；两种编码环境各 17 passed |

## 5. 遗留（不在本 key 范围）

- **R-1**：`skill.dir` 跨语言不一致——Python 接受 `null`/缺省（= 项目根），TS `rag/config.ts:262` `requireString` 要求非空。建议 TS 改用 `optionalString`（与「`null` 删除字段」的合并契约一致），需在 `packages/coding-agent` 侧改动 + 测试。
- **R-2**：pi 窗口内没有 `/mw rag ...` 子命令，`/mw doctor` 也不渲染 RAG 行（`mw.py doctor --json` 已含 `report.rag`）。若要做，按 `/mw target` 的薄封装模式；需新 key。
- **R-3**：真实 RAG 服务联调（本机 `127.0.0.1:8100/mcp/` 实测存活，返回标准 `-32600 Missing session ID`，无认证挑战——但未带 token 走完整工具调用）。
- **R-4**：`--machine` 在真实 HOME 的行为未验（刻意只在临时 `MW_RAG_SERVERS_HOME` 下测）。
- **R-5**：手册散文层面的漂移没有结构性防护（只有模板块字节锁 + 字段表集合锁 + 3 条报错串）；本轮靠人工与独立抽查发现。

## 6. 判定

**✅ 通过。** AC-201~AC-207 全部达到，VC 证据 20 项充分、2 项 ⚠️（VC-209 覆盖窄、散文无锁）、0 项 ❌；独立验证的三条反例证明核心锁（手册 parity / 字段集合 / 默认零影响）真能变红；两条独立发现的散文不符与一处跨语言不一致已如实记录并按范围处置（修正或转遗留）。
