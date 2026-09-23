# PM State: mw-rag-config-guide

## 1. Snapshot
- Key: mw-rag-config-guide
- Phase: DONE
- Next Action: 已完成（DONE）；遗留 R-1~R-5 见 achieved.md，等用户决定是否开新 key
- Started: 2026-09-23 11:14
- Updated: 2026-09-23 12:02
- Completed: 2026-09-23 12:02

## 2. Task Status

| Task | Stage | Status | Worker | 备注 |
|---|---|---|---|---|
| T-21-RAG-INIT | 1 | **done（PM 已复核）** | `mw-rag-cfg-t21-init` | `rag_templates.py` + `mw.py rag init` + `test_rag_init.py`（11 测试） |
| T-21B-ROOTS-TRAP | 1 | **done（PM 直执）** | — | 模板默认不再留**悬空** `path_roots_file` 引用（见下）；新增 `VC-208-default` 测试 |
| T-21C-ROOTS-DEFAULT | 1 | **done（PM 直执）** | — | 默认写出 `.mw/rag-roots.json`（`_README` + `engine: "."`）并激活字段；`--with-roots` → `--no-roots`（见 D-210） |
| T-22-RAG-MANUAL | 2 | **done（PM 已复核）** | `mw-rag-cfg-t22-manual` | `docs/rag-config-guide.md`（30 KB，9 节）+ `test_rag_docs.py`（5 测试）+ README 指向 + 两包 CHANGELOG |
| T-22B-PROSE-FIX | 2 | **done（PM 直执）** | — | 手册散文两处与实现不符（`via=mcp|c...` 截断、§3.4 未知 role 写成 `unverified`）已修 |
| T-23-VERIFY | 3 | **done（PASS）** | `mw-rag-cfg-t23-verify` | 独立验证 PASS：三条反例全红 + sha256 复原；发现 2 处散文不符 + 1 处测试注释 |
| T-23B-DOC-ACCURACY | 3 | **done（PM 直执）** | — | 修手册 §7 kind 枚举 / §3.1 skill.dir / 测试注释；design.md 清 `--with-roots`；spec AC-201/203 标 REVISED |
| 质检报告 | 3 | **done（PM）** | — | `evidence/quality-gate-report-2026-09-23.md`：20 充分 / 3 ⚠️ / 0 ❌ |

## 3. Evidence Ledger

| 项 | 数量 | 状态 | 备注 |
|---|---|---|---|
| 证据行（T-21） | 7 VC | **已采集** | `[VERIFY] VC-201: created=2 list_exit=0 enabled=(none) servers=1`；`VC-202: rerun_exit=1 rerun_untouched=1 force_exit=0 servers_sha_changed=1 target_sha_changed=1`；`VC-203: dry_exit=0 print_exit=0 tree_equal=1`；`VC-204: subprocess_exit=0 input_hits=0 stdin_hits=0`；`VC-205: fields=15 mcp_cli_commented=1 skill_url_commented=1 both_active=1`；`VC-207: machine_written=1 machine_under_temp_home=1 rerun_exit=1 machine_only_refusal=1`；`VC-208: roots_written=1 digest_len=64` |
| 证据行（T-21B） | 1 VC | **已采集** | `[VERIFY] VC-208-default: active_path_roots=0 digest_is_none=1` |
| 证据行（T-22） | 3 VC | **已采集** | `[VERIFY] VC-205: documented_rows=25 missing=0 extra=0 example_yaml_keys=34 unaccepted=0`；`VC-205-accept: load_error=0 enabled=1 servers=1 role_keys=6 phase_keys=4`；`VC-206: sections=3 servers_bytes=3808 target_bytes=1643 roots_bytes=724`；`VC-209: phrases=3 verified_in_source=3 quoted_in_manual=3` |
| 手册可执行性 | 4 类示例 | **已采集** | T-22 在临时项目真跑 init/list/probe/sync/audit（`enabled: overcode`、`probe: reachable`、audit exit 0） |
| 反例试验 | 3 条 | 待做（T-23） | 见 T-23 任务书 |

## 4. Hypothesis Queue

- H-1：模板默认 `enabled: []` 会不会让用户误以为「命令没生效」？→ 缓解：`--enable` 参数 + next steps 打印 + 手册 ① 节三步；
  若 T-23 的可执行性抽查仍显示困惑，只补显著提示，不改默认值（默认启用占位 URL 的代价更大）。
- H-2：往 `target.yml` 末尾追加 `rag:` 段，在「文件末尾本就是嵌套块」的场景下是否仍是合法 YAML？→ 要求 T-21 用含
  `dual:` 块的真实形态断言追加后 `load_target_config` 仍能解析。

## 5. Decisions

| ID | 决策 | 理由 |
|---|---|---|
| D-201 | 模板文本唯一来源 = 新模块 `rag_templates.py`；手册引用 `--print` 输出，不手抄 | 避免 P-008（文档静默过期）；一份文本一个来源 |
| D-202 | 默认写项目层两处；机器层用 `--machine`/`--only-machine` 显式请求 | 不意外修改用户 HOME |
| D-203 | 模板默认 `enabled: []`，`--enable` 可一步启用 | 占位 URL 不应让每个 worker 都探活；安全默认 + 一步可用 |
| D-204 | servers 文件不存在才写；`rag:` 段只在无该键时**文本级追加**；`--force` 才覆盖；写入原子替换 | `target.yml` 是多会话共享文件，YAML round-trip 会毁注释 |
| D-205 | 退出码 0 达成 / 1 拒绝或失败 / 2 用法错；`--dry-run`/`--print` 零写入且 exit 0 | 与 `mw rag` 子命令族语义一致 |
| D-206 | 零交互：无 `input()`/`sys.stdin`，缺省值来自示例常量 | 用户要求「没有输入的按示例写成模板」；CI/worker 场景必须不挂 |
| D-207 | 手册章节骨架固定（① 上手 … ⑨ FAQ），字段表 4 列（是什么/取值与默认/举例/写错的后果） | 用户要求逐字段注释 + 可复制粘贴 |
| D-208 | init 无副作用：不碰 `_workers.parallel`/`_index.parallel`/`goal.md`/`.pi/`，不探活 | 配置生成必须可反复安全调用 |
| D-209 | 模板里**每一个处于激活状态的字段都必须真的有效** | 悬空引用会让每一条引用都 `exists=false`/`local_path` 为空，用户会把「roots 文件缺失」误判成「RAG 没效果」——这正是本次要消灭的静默失效 |
| D-210 | 落实 D-209 的方式改为**默认写出并激活**：`mw rag init` 默认写 `.mw/rag-roots.json`（`_README` + `"engine": "."` = 项目根），`path_roots_file` 默认激活；要跳过用 `--no-roots`（此时字段自动变注释） | 实测「不配置 roots」会让审计把每条引用记为 `unverified` 并 exit 1（README 退出码表），即默认必失败；而 `engine: "."` 在单仓场景**开箱即可用**（端到端实测 `citations=1 missing=0 unverified=0 audit_exit=0`）。空 `{}` 映射反而更糟（全部 `missing`，冤枉引用）|
| D-211 | 测试里所有 `subprocess.run(text=True)` 必须显式 `encoding="utf-8"` | 本机 `PYTHONIOENCODING=utf-8` 时父进程按 GBK 解码子进程 UTF-8 输出 → `UnicodeDecodeError`（T-22 独立发现，PM 修 3 处调用点）|

## 6. Turn End Records
*(empty)*

## 7. Process Log

- 2026-09-23 11:14 需求（用户）：(1) RAG/MCP 配置的详细手册，每个配置文件都有可直接复制粘贴修改即用的示例，
  **每个字段都要有注释说明**（例如 `sources` 是干什么的）；(2) 一条命令快速创建，无输入时按示例写成模板让用户改。
- 2026-09-23 11:14 spec/design/plan/tasks 落盘并按门禁推进到 EXECUTE（`audit_phase.py` → `VERDICT: PASS`）。
  调研证据：`evidence/research/spec-rag-config-guide-2026-09-22.md`（服务表 11 字段 + `rag:` 段键集，逐条给 `mw_common.py` 行号）、
  `evidence/research/design-rag-config-guide-2026-09-22.md`（否掉交互式 init / YAML round-trip / 默认启用 / 默认写 HOME 四个方案）。
- 2026-09-23 11:14 复核结论：曾疑 README 的 `enabled` 缺省语义写错（控制台 mojibake 导致误读），复核后
  `README.md:270` 实为「空或缺省 = 全关」，与两侧实现一致 → 本 key **不含** README 语义更正。
- 2026-09-23 11:15 派发 T-21（`mw-rag-cfg-t21-init`，coding 型，模型走路由默认）。
- 2026-09-23 11:4x T-21 回读并**独立复核**：自己跑 `test_rag_init.py -q -s` = 11 passed；在临时目录真跑
  `rag init` → 逐字读了生成的两份模板（注释质量达标：`sources` 说明了引用第 2 段、`token_env` 说明了"只填变量名"、
  `transport` 说明了 both 的降级边界）；`mw rag list` exit 0 且 `enabled: (none)`；重跑 exit 1。
  另核对了一处**可能的文档错误**：模板注释称 roles 还能设 `chat_budget`/`time_budget_s` —— 查 `mw_common.py:365`
  `_RAG_ROLE_KEYS` 确实比 `_RAG_PHASE_KEYS` 多这两个键，注释正确。
- 2026-09-23 11:4x **PM 直执 T-21B（发现并修掉一个用户会踩的静默陷阱）**：T-21 的模板默认把
  `path_roots_file: .mw/rag-roots.json` 写成**激活**状态，但该文件只有 `--with-roots` 才存在。实测：`--enable` 后
  `path_roots_file` 有值而 `path_roots_digest = None` → 引用无法在磁盘上核对（`exists=false`、`local_path` 为空），
  用户会把「roots 文件缺失」当成「RAG 没效果」。已改为：默认输出**注释行**并写明原因，`--with-roots` 才激活；
  新增测试 `VC-208-default: active_path_roots=0 digest_is_none=1`（12 passed）。确立 D-209：
  **模板里所有激活字段必须真的有效**。
- 2026-09-23 11:4x 零回归复核：`python -m pytest -q` = **834 passed, 9 deselected**（T-21 报 833 + 我新增 1）；
  仓根 `npm run check` exit 0；临时目录已清理，未 commit。
- 2026-09-23 12:0x 用户四点反馈处理：(1) 模板保持英文 —— 不改；(2) 不写全局机器层 —— 不跑 `--machine`；
  (3) 解释 `adapter` 语义并实测错填后果（`v2` → `mw rag list/probe` exit 1、`doctor` 报
  `rag: ERROR - adapter must be 'overcode-v1'`、已派发任务 spawn 被 `config torn (rag)` 拒）；(4) 修注释断行 +
  补独立的 `.mw/rag-roots.json` 模板（= T-21C / D-210）。
- 2026-09-23 12:0x T-22 完成并回读：手册 30 KB / 9 节 / 逐字段 25 行 4 列 / 四类可复制示例 / 退出码表 / 五层判据 /
  失败 signature / 已知坑；它**独立发现**了我并发改模板导致的手册 parity 漂移（`VC-206` 变红）并自行按实跑 CLI 对齐，
  还报告了 `test_rag_init.py` 的 `PYTHONIOENCODING` 脆弱性（→ D-211，PM 已修 3 处 subprocess 调用点）。
- 2026-09-23 12:1x PM 复核手册全文，发现并修两处**散文与实现不符**（T-22B）：§6 的 `via=mcp|c...` 截断（应为
  `via=mcp|cli ms=<N> results=<N>`）、§3.4 把「未知 role」写成 `unverified`（实现是 `missing`，会让 audit exit 1）。
  这正是模板块有字节锁、散文没有锁的体现 → 已把「散文准确性抽查（≥8 条可证伪断言）」写进 T-23 任务书。
- 2026-09-23 12:2x T-23 **PASS**：基线独立复现（17 passed 两种编码 / 839 passed / check exit 0）；三条反例
  全部按预期变红并 sha256 复原（A→VC-206、B→VC-205、C→VC-201）；手册四类示例逐字复制后全部被接受；
  它独立发现：手册 §7 `rag-unavailable` 的 kind 枚举漏 `tool`/`capability`、§3.1 `skill.dir` 的 `null` 默认在 TS 侧
  不成立（`rag/config.ts:262` requireString）、测试注释 13→15、`design.md` 残留 `--with-roots`。
- 2026-09-23 12:3x PM 直执 T-23B：四处全部修正（散文以实现为准；TS/Python 差异如实标注为遗留 R-1）；spec
  AC-201/AC-203 同步为「默认写 roots + `--no-roots`」并标 `REVISED @ 2026-09-23`；`check_mermaid.py` PASS。
  复核：`test_rag_init.py`+`test_rag_docs.py` = 17 passed；`pytest -q` = 839 passed / 9 deselected；`npm run check` exit 0。
- 2026-09-23 12:3x 质检报告 + `achieved.md` 落盘，推进 DONE。附带发现：本机 `127.0.0.1:8100/mcp/` 存活
  （返回标准 `-32600 Missing session ID`，无认证挑战）→ 用户的 OverCode rag-mcp 疑似正在运行，可直接接入。
- 2026-09-23 12:1x 复核通过后派发 T-23（独立验证，coding 型）：三条反例 + 手册可执行性抽查 + 散文抽查 +
  `PYTHONIOENCODING=utf-8` 复跑。当时基线：`test_rag_init.py`+`test_rag_docs.py` = **17 passed**（两种编码环境均绿）、
  `python -m pytest -q` = **839 passed, 9 deselected**。
